#  See LICENSE file for full copyright and licensing details.

import json
import logging
from werkzeug.wrappers import Response

from odoo import _
from odoo.http import Controller, route, request
from odoo.addons.integration.controllers.integration_webhook import IntegrationWebhook
from odoo.addons.integration.controllers.utils import build_environment, validate_integration

from ..prestashop_api import PRESTASHOP


_logger = logging.getLogger(__name__)


class PrestashopWebhook(Controller, IntegrationWebhook):

    _kwargs = {
        'type': 'jsonrpc',
        'auth': 'none',
        'methods': ['POST'],
        'csrf': False,
    }

    """
    headers = {
        X-Forwarded-Host: ventor-dev-integration-webhooks-test-15.odoo.com
        X-Forwarded-For: 141.95.36.76
        X-Forwarded-Proto: https
        X-Real-Ip: 141.95.36.76
        Connection: close
        Content-Length: 11369
        User-Agent: Httpful/0.2.20 (cURL/7.64.0 PHP/7.3.27-9+0~20210227.82+debian10~1.gbpa4a3d6
                    (Linux) Apache/2.4.38 (Debian) Mozilla/5.0 (X11; Linux x86_64)
                    AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36)
        Content-Type: application/json
        Accept: */*; q=0.5, text/plain; q=0.8, text/html;level=3;
        X-Secure-Key: GHDGBKC15DIDXMXFXZHYUWXBPAEOGEAT
        X-Hook: actionProductUpdate
    }
    """

    SHOP_NAME = 'X-Forwarded-Host'  # This header skipped in redefined method `get_shop_domain`
    TOPIC_NAME = 'X-Hook'

    @property
    def integration_type(self):
        return PRESTASHOP

    def _verify_shop_domain(self, integration):
        # PrestaShop sends no header with the shop URL, so there is nothing meaningful
        # to validate here. Security is enforced via X-Secure-Key instead.
        return True, '%s webhook shop domain check skipped.' % integration.name

    def _get_post_data(self):
        """
        Parse JSON data from the request.
        """
        try:
            raw_data = request.httprequest.data
            data = json.loads(raw_data)

            if 'order' in data:
                return data.get('order', dict())
            elif 'product' in data:
                return data.get('product', dict())
            else:
                raise ValueError(_('Unknown webhook data'))
        except json.JSONDecodeError:
            raise ValueError(_('Invalid JSON data'))
        except Exception as e:
            raise ValueError(_('Error while parsing JSON data: %s') % e)

    def _prepare_pipeline_data(self, *args, **kwargs):
        post_data = self._get_post_data()
        vals = {
            'payment_method': post_data['payment'],
            'integration_workflow_states': [post_data['current_state']],
            'date_order': post_data.get('date_add'),
        }
        return vals

    def _check_webhook_digital_sign(self, integration):
        return True  # TODO

    def _get_essential_headers(self):
        return [
            self.TOPIC_NAME,
            'X-Secure-Key',
        ]

    def _get_events_mapping(self):
        return {
            'actionValidateOrder': '_process_create_order',
            'actionOrderHistoryAddAfter': '_process_update_status_order',
            'actionProductUpdate': '_process_update_product',
            # We won't use 'actionProductSave', because he returns not full data
            # 'actionProductSave': '_process_create_product',
        }

    # Handle orders
    @route(
        [
            f'/integration/<string:dbname>/{PRESTASHOP}/<int:integration_id>/orders',
            f'/<string:dbname>/integration/{PRESTASHOP}/<int:integration_id>/orders',
        ],
        **_kwargs,
    )
    @build_environment
    @validate_integration
    def prestashop_receive_orders(self, *args, **kw):
        """
        Expected methods:
            actionValidateOrder
            actionOrderHistoryAddAfter
        """
        _logger.info('Call prestashop webhook controller: prestashop_receive_orders()')
        integration = request.env['sale.integration'].browse(kw['integration_id'])
        post_data = self._get_post_data()

        # Validate shop ID
        webhook_shop_id = str(post_data.get('id_shop', ''))
        if not webhook_shop_id:
            _logger.warning('No shop ID found in webhook data')
            return False

        if not integration._validate_shop_id(webhook_shop_id):
            _logger.warning('Webhook skipped: shop ID validation failed')
            return Response('Webhook skipped: shop ID validation failed')

        external_order_id = self._get_value_from_post_data('id')
        return self._process_event(integration, external_order_id)

    # Handle products
    @route(
        [
            f'/integration/<string:dbname>/{PRESTASHOP}/<int:integration_id>/products',
            f'/<string:dbname>/integration/{PRESTASHOP}/<int:integration_id>/products',
        ],
        **_kwargs,
    )
    @build_environment
    @validate_integration
    def prestashop_receive_products(self, *args, **kw):
        """
        Expected methods:
            actionProductUpdate
        """
        _logger.info('Call prestashop webhook controller: prestashop_receive_products()')
        integration = request.env['sale.integration'].browse(kw['integration_id'])

        # The following check is disabled because we’re not filtering product webhooks by id_shop_default
        # while PrestaShop multistore mode is enabled.
        # Validate shop ID
        # webhook_shop_id = str(post_data.get('id_shop_default', ''))
        # if not webhook_shop_id:
        #     _logger.warning('No shop ID found in webhook data')
        #     return False

        # if not integration._validate_shop_id(webhook_shop_id):
        #     _logger.warning('Webhook skipped: shop ID validation failed')
        #     return Response('Webhook skipped: shop ID validation failed')

        external_product_id = self._get_value_from_post_data('id')

        # Get product name; required in Odoo to create a product
        name = self._get_product_name(integration)
        if not name:
            _logger.warning(f'Webhook skipped: name is empty for product {external_product_id}.')
            return Response(f'Webhook skipped: name is empty for product {external_product_id}.')

        # If the product is simple (not a combination), reference is required
        reference = self._get_value_from_post_data('reference')
        product_type = self._get_value_from_post_data('product_type')
        if not reference and product_type in ['', 'virtual']:
            _logger.warning(f'Webhook skipped: reference is empty for product {external_product_id}.')
            return Response(f'Webhook skipped: reference is empty for product {external_product_id}.')

        return self._process_event(integration, external_product_id)

    def _get_product_name(self, integration):
        integration_lang = integration.integration_lang_id

        lang_mapping = request.env['integration.res.lang.mapping'].search([
            ('language_id', '=', integration_lang.id),
            ('integration_id', '=', integration.id),
        ], limit=1)
        if lang_mapping:
            language_code = lang_mapping.external_language_id.code
        else:
            language_code = integration.get_adapter_lang_code()

        return self._get_value_from_post_data('name').get(language_code, '')
