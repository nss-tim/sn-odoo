#  See LICENSE file for full copyright and licensing details.

import logging
from time import sleep
from functools import wraps

from requests import Session
from requests.exceptions import ConnectionError as RequestsConnectionError

from .webservice import PrestaShopAPIClient
from .base_model import BaseModel
from .category import Category
from .product import Product
from .combination import Combination
from .image import Image
from .product_tag import ProductTag


try:
    # Prefer import from integration_queue_job if available
    from odoo.addons.integration_queue_job.exception import RetryableJobError
except ImportError:
    # Fallback if queue_job is not installed
    from odoo.addons.queue_job.exception import RetryableJobError


_logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _process_request(method, *args, _attempt=1, **kwargs):
    try:
        result = method(*args, **kwargs)
    except RequestsConnectionError as ex:
        # Try to re-executing the `request method` on the fly just in case of
        # an unstable connection. And only after that throw the `RetryableJobError`.
        if _attempt <= MAX_RETRIES:
            sleep((_attempt + 1) * 2)
            _logger.info(f'Prestashop ConnectionError. Next attempt ({_attempt + 1}): {args}; {kwargs};')
            return _process_request(method, *args, _attempt=_attempt + 1, **kwargs)

        _logger.error(ex)
        raise RetryableJobError(str(ex), seconds=10)

    return result


def catch_exception(method):
    @wraps(method)
    def _catch_exception(*args, **kwargs):
        return _process_request(method, *args, **kwargs)
    return _catch_exception


class Client(PrestaShopAPIClient):

    default_language_id = None
    id_group_shop = None
    data_block_size = None
    shop_ids = []

    classes = {
        'category': Category,
        'product': Product,
        'combination': Combination,
        'image': Image,
        'product_tag': ProductTag,
    }

    def __init__(self, store_url, api_key):
        session = Session()
        add_headers = self._get_add_headers()
        session.headers.update(add_headers)
        super(Client, self).__init__(store_url=store_url, api_key=api_key, session=session)

        # Patch the `_execute` method
        method = self._execute
        self._execute = catch_exception(method)

    def _get_add_headers(self):
        headers = {
            'User-Agent': 'VentorTech-Odoo-Prestashop-Connector-PRO/1.X',
        }
        return headers

    def add(self, resource, content=None, files=None, options=None):
        _logger.debug(
            'PrestaShop API ADD request: resource=%s, content=%s, files=%s, options=%s',
            resource,
            content,
            files,
            options,
        )
        return super(Client, self).add(resource, content, files, options)

    def edit(self, resource, content, options=None):
        _logger.debug(
            'PrestaShop API EDIT request: resource=%s, content=%s, options=%s',
            resource,
            content,
            options,
        )
        return super(Client, self).edit(resource, content, options)

    def get(self, resource, resource_id=None, options=None):
        _logger.debug(
            'PrestaShop API GET request: resource=%s, resource_id=%s, options=%s',
            resource,
            resource_id,
            options,
        )
        return super(Client, self).get(resource, resource_id, options)

    def delete(self, resource, resource_ids):
        _logger.debug(
            'PrestaShop API DELETE request: resource=%s, resource_ids=%s',
            resource,
            resource_ids,
        )
        return super(Client, self).delete(resource, resource_ids)

    def search(self, resource, options=None):
        _logger.debug(
            'PrestaShop API SEARCH request: resource=%s, options=%s',
            resource,
            options,
        )
        return super(Client, self).search(resource, options)

    def model(self, name):
        cls = self.classes.get(name)
        if not cls:
            cls = BaseModel

        instance = cls(
            self,
            id_group_shop=self.id_group_shop,
            shop_ids=self.shop_ids,
            default_language_id=self.default_language_id,
            data_block_size=self.data_block_size,
        )
        instance._name = name  # TODO: bad

        return instance
