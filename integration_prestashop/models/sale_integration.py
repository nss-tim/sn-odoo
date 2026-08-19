#  See LICENSE file for full copyright and licensing details.
import json
import re
import pytz

from datetime import datetime
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.integration.tools import expose_for_testing, make_list_if_not, IS_FALSE
from odoo.addons.integration.exceptions import ErrorStore as es

from ..prestashop_api import PrestaShopApiClient, PRESTASHOP


class SaleIntegration(models.Model):
    _inherit = 'sale.integration'

    type_api = fields.Selection(
        selection_add=[(PRESTASHOP, 'PrestaShop')],
        ondelete={
            PRESTASHOP: 'cascade',
        },
    )

    delivery_time = fields.Selection(
        string='Delivery Time',
        selection=[
            ('none', 'None'),
            ('default', 'Default delivery time'),
            ('specific', 'Specific delivery time to this product')
        ],
        required=True,
        default='none',
        help=(
            'Configure the "Delivery Time" for products to sync with PrestaShop. '
            'Ensure you specify the "In-stock Delivery Days" and "Out-of-stock Delivery Days" '
            'if you opt for a "Specific delivery time for this product".'
        ),
    )

    product_delivery_in_stock = fields.Many2one(
        string='In-stock Delivery Duration Field',
        comodel_name='ir.model.fields',
        help=(
            'Specify the field from the Product template (accepting only float or integer values) '
            'to determine the "In-stock Delivery Days" for syncing with '
            'PrestaShop\'s corresponding setting.'
        ),
        domain='[("model_id.model", "=", "product.template"),'
               ' ("ttype", "in", ("float", "integer")) ]',
    )

    message_template_in_stock = fields.Char(
        string='In-stock Delivery Message Template',
        translate=True,
        default='Delivery in {} days',
        help=(
            'Define a message template for the "Delivery time of in-stock products" '
            'to be displayed in PrestaShop for products available in stock.'
        ),
    )

    product_delivery_out_of_stock = fields.Many2one(
        string='Out-of-stock Delivery Duration Field',
        comodel_name='ir.model.fields',
        help=(
            'Specify the Product template field (accepting only float or integer values) '
            'that holds the "Out-of-stock Delivery Days" for syncing with '
            'PrestaShop\'s equivalent attribute.'
        ),
        domain='[("model_id.model", "=", "product.template"),'
               ' ("ttype", "in", ("float", "integer")) ]',
    )

    message_template_out_of_stock = fields.Char(
        string='Out-of-stock Delivery Message Template',
        translate=True,
        default='Delivery in {} days',
        help=(
            'Define a message template for the "Delivery time of out-of-stock products with '
            'allowed orders" to communicate delivery expectations on PrestaShop for products that '
            'are out of stock.'
        ),
    )

    subscribed_to_newsletter_id = fields.Many2one(
        string='Newsletter Subscribed Field',
        comodel_name='ir.model.fields',
        help=(
            'Specify the boolean field on the Customer record where the subscription status '
            'for newsletters will be reflected. This field corresponds to the "Newsletter '
            'Subscribed" status from PrestaShop.'
        ),
        domain='[("model_id.model", "=", "res.partner"), ("ttype", "=", "boolean")]',
        default=lambda self: self._get_field_for_set_default('subscribed_to_newsletter_presta'),
    )

    newsletter_registration_date_id = fields.Many2one(
        string='Newsletter Registration Field',
        comodel_name='ir.model.fields',
        help=(
            'Specify the datetime field on the Customer record to log the date and time when '
            'the customer subscribed to the newsletter. This syncs with the '
            '"Newsletter Registration Date" from PrestaShop.'
        ),
        domain='[("model_id.model", "=", "res.partner"), ("ttype", "=", "datetime")]',
        default=lambda self: self._get_field_for_set_default('newsletter_registration_date_presta'),
    )

    customer_registration_date_id = fields.Many2one(
        string='Registration Date Field',
        comodel_name='ir.model.fields',
        help=(
            'Select the datetime field on the Customer record to record the original registration '
            'date of the customer, aligning with the "Registration Date" field from PrestaShop.'
        ),
        domain='[("model_id.model", "=", "res.partner"), ("ttype", "=", "datetime")]',
        default=lambda self: self._get_field_for_set_default('customer_registration_date_presta'),
    )

    additional_address_information = fields.Many2one(
        string='Additional Address Info Field',
        comodel_name='ir.model.fields',
        help=(
            'Choose the character or text field on the Customer record for storing any '
            'supplementary address details. This field will contain additional information '
            'from the corresponding e-commerce system field.'
        ),
        domain='[("model_id.model", "=", "res.partner"), ("ttype", "in", ("char", "text"))]',
    )

    import_inactive_categories = fields.Boolean(
        string='Sync Inactive Categories',
        help=(
            'Select this option to include inactive categories from e-commerce system '
            'in the import process, allowing them to be managed within Odoo.'
        ),
    )

    force_user_on_order_status_change = fields.Boolean(
        string='Record Employee on Status Change',
        help=(
            'If enabled, when sending order status updates to Prestashop in order history we will record the name '
            'of the employee who changed this status. Connector will try to find the corresponding user from employee '
            'mappings to Odoo user. Take care to make all the possible mappings for all your Odoo users.'
        ),
    )

    default_customer_group_field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Default Customer Group Field',
        ondelete='set null',
        domain='[("model_id.model", "=", "res.partner"), ("ttype", "in", ("char", "text"))]',
        help=(
            'Select the field in the Partner (res.partner) model where the default customer '
            'group from PrestaShop will be saved.'
        ),
    )

    shared_stock = fields.Boolean(
        string='Shared Stock',
        help='If enabled - connector should use id_shop = 0 during stock export.'
    )

    customer_group_mapping_ids = fields.One2many(
        string='Customer Group → Sales Team Mapping',
        comodel_name='integration.customer.group.mapping',
        inverse_name='integration_id',
    )

    pricelist_mapping_ids = fields.Many2many(
        comodel_name='integration.product.pricelist.mapping',
        string='Pricelist Mappings',
        compute='_compute_pricelist_mapping_ids',
        readonly=False,
        default=lambda self: self._get_default_pricelist_mapping_ids(),
        help='Manage the mapping between Odoo pricelists and external pricelists from your e-commerce system.'
    )

    def is_prestashop(self):
        self.ensure_one()
        return self.type_api == PRESTASHOP

    def to_dictionary(self):
        result = super(SaleIntegration, self).to_dictionary()

        if self.is_integration_prestashop:
            result.update(
                datetime_format=self.datetime_format,
            )

        return result

    def _set_default_template_reference_id(self):
        if self.is_prestashop():
            self.template_reference_id = self.env.ref(
                'integration_prestashop.prestashop_ecommerce_field_template_reference').id
            return bool(self.template_reference_id)
        return super()._set_default_template_reference_id()

    def _set_default_product_reference_id(self):
        if self.is_prestashop():
            self.product_reference_id = self.env.ref(
                'integration_prestashop.prestashop_ecommerce_field_reference').id
            return bool(self.product_reference_id)
        return super()._set_default_product_reference_id()

    def _set_default_template_barcode_id(self):
        if self.is_prestashop():
            self.template_barcode_id = self.env.ref(
                'integration_prestashop.prestashop_ecommerce_field_template_barcode').id
            return bool(self.template_barcode_id)
        return super()._set_default_template_barcode_id()

    def _set_default_product_barcode_id(self):
        if self.is_prestashop():
            self.product_barcode_id = self.env.ref(
                'integration_prestashop.prestashop_ecommerce_field_barcode').id
            return bool(self.product_barcode_id)
        return super()._set_default_product_barcode_id()

    def _get_integration_auth_action(self, add_default_context: bool = True) -> dict:
        if self.is_integration_prestashop:
            action = self.sudo().env.ref(
                'integration_prestashop.action_view_prestashop_integration_authentication').read()[0]

            if add_default_context:
                action['context'] = {
                    'default_integration_id': self.id,
                    'default_url': self.get_settings_value('url'),
                    'default_key': self.get_settings_value('key'),
                    'default_admin_url': self.get_settings_value('admin_url'),
                    'default_access_granted': self.get_settings_value('access_granted'),
                }

            return action

        return super()._get_integration_auth_action()

    def _get_default_pricelist_mapping_ids(self):
        mappings = self.env['integration.product.pricelist.mapping'].search([
            ('integration_id', '=', self.id),
        ])
        return mappings.ids

    def is_carrier_tracking_required(self):
        if self.is_prestashop():
            return True
        return super(SaleIntegration, self).is_carrier_tracking_required()

    def export_sale_order_status(self, order):
        res = super(SaleIntegration, self).export_sale_order_status(order)

        if not res or not self.is_prestashop():
            return res

        order_sub_status = order.sub_status_id.id
        integration_paid_status = self.sub_status_paid_id.id

        if order_sub_status and integration_paid_status and order_sub_status == integration_paid_status:
            txns = self.adapter.fetch_order_transactions(order.external_order_ref)

            for txn in txns:
                txn['internal_status'] = 'done'

            order._apply_values_from_external({'payment_transactions': txns})

            external_payments = order.external_payment_ids
            external_payments.filtered(lambda x: x.is_ecommerce_ok).mark_done()
            external_payments.filtered(lambda x: not x.is_done).mark_skipped()

        return res

    def _get_field_for_set_default(self, field_name):
        return self.env['ir.model.fields'].sudo().search([
            ('model_id.model', '=', 'res.partner'),
            ('name', '=', field_name),
        ], limit=1)

    @api.depends('last_receive_orders_datetime')
    def _compute_last_receive_orders_datetime_str(self):
        for integration in self:
            if integration.is_prestashop():
                settings_timezone = integration.get_settings_value('PS_TIMEZONE', '')
                if settings_timezone:
                    timezone = pytz.timezone(settings_timezone)
                    value = integration.last_receive_orders_datetime\
                        .astimezone(timezone).strftime(integration.datetime_format)

                    integration.last_receive_orders_datetime_str = value
                    continue

            super(SaleIntegration, integration)._compute_last_receive_orders_datetime_str()

    @api.depends('orders_cut_off_datetime')
    def _compute_orders_cut_off_datetime_str(self):
        for integration in self:
            if integration.is_prestashop():
                settings_timezone = integration.get_settings_value('PS_TIMEZONE', '')
                if settings_timezone:
                    timezone = pytz.timezone(settings_timezone)
                    value = integration.orders_cut_off_datetime \
                        .astimezone(timezone).strftime(integration.datetime_format)

                    integration.orders_cut_off_datetime_str = value
                    continue

            super(SaleIntegration, integration)._compute_orders_cut_off_datetime_str()

    @api.depends('pricelist_mapping_ids')
    def _compute_pricelist_mapping_ids(self):
        for integration in self:
            if integration.is_prestashop():
                integration.pricelist_mapping_ids = [(6, 0, integration._get_default_pricelist_mapping_ids())]

    def get_class(self):
        self.ensure_one()
        if self.is_prestashop():
            return PrestaShopApiClient

        return super().get_class()

    def action_active(self):
        self.ensure_one()
        result = super().action_active()

        if self.is_prestashop():
            adapter = self.adapter
            ps_timezone = adapter.get_configuration('PS_TIMEZONE')
            ps_weight_unit = adapter.get_configuration('PS_WEIGHT_UNIT')

            self.set_settings_value('PS_TIMEZONE', ps_timezone)
            self.set_settings_value('weight_uom', ps_weight_unit)

        return result

    def action_import_related_products(self):
        """Dispatch background batch jobs to sync optional_product_ids
        from PS accessories.

        Uses existing product template mappings — no PS API call during
        button click. Unmapped products and unmapped accessories are
        silently ignored.
        """
        ProductTemplateMapping = self.env['integration.product.template.mapping']
        mappings = ProductTemplateMapping.search([
            ('integration_id', '=', self.id),
            ('template_id', '!=', False),
            ('external_template_id', '!=', False),
        ])

        if not mappings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Synchronize Related Products'),
                    'message': _(
                        'No mapped products found. '
                        'Please import and map products first.'
                    ),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        external_codes = mappings.mapped('external_template_id.code')
        block = 1
        limit = self.get_external_block_limit()
        description_ = f'{self.name}: Synchronize Related Products [batch %s]'

        context = {
            'job_integration_id': self.id,
            'job_integration_job_type': 'product',
        }
        self = self.with_context(**context)

        while external_codes:
            self.with_delay(
                priority=5,
                description=(description_ % block),
            ).run_sync_related_products_batch(external_codes[:limit])
            block += 1
            external_codes = external_codes[limit:]

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Synchronize Related Products'),
                'message': _(
                    'Queue Jobs "Synchronize Related Products" are created'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def run_sync_related_products_batch(self, external_codes):
        """Worker job: fetch PS accessories for a batch of products and
        assign optional_product_ids.

        Raises es.UserError if any accessories in the batch are not yet mapped
        to Odoo products, listing all unmapped products so the user can fix
        them in one go before retrying.
        """
        self = self.with_context(company_id=self.company_id.id)
        adapter = self._build_adapter()
        ps_products = adapter.get_products_for_related_products_sync(
            external_codes
        )

        ProductTemplate = self.env['product.template']

        # First pass: resolve all accessories and collect any unmapped codes.
        # We build the full update map before writing anything so that a
        # partial batch never results in silent data loss.
        updates = {}
        unmapped_codes = set()
        for ps_product in ps_products:
            template = ProductTemplate.from_external(
                self, ps_product['id'], raise_error=False
            )
            if not template:
                continue
            optional_products, unmapped_template_codes = self._resolve_ps_accessories(
                ps_product,
            )
            updates[template] = optional_products
            unmapped_codes.update(unmapped_template_codes)

        if unmapped_codes:
            es.raise_error(err_code='E111', support_contact=False, unmapped_codes=unmapped_codes)

        # Second pass: all accessories resolved — write optional_product_ids.
        lines = []
        for template, optional_products in updates.items():
            template.optional_product_ids = [(6, 0, optional_products.ids)]
            lines.append(
                f'{template.name}: {len(optional_products)} optional product(s)'
            )

        if not lines:
            return 'No products were updated (no accessories found in this batch).'

        return 'Updated %d product(s):\n%s' % (
            len(lines),
            '\n'.join(f'- {line}' for line in lines),
        )

    def _resolve_ps_accessories(self, ps_product_data, raise_error=False):
        """
        Resolve PS optional product IDs (accessories) to Odoo product.template records.

        params: ps_product_data: dict containing an 'associations' key with PS accessory data.
        return: tuple of (recordset of product.template, list of unmapped external ids)
        """
        unmapped_codes = []
        accessories = ps_product_data.get(
            'associations', {}
        ).get('accessories', {}).get('product', [])
        external_ids = [x['id'] for x in make_list_if_not(accessories)]

        ProductTemplate = self.env['product.template']
        result = ProductTemplate
        for ext_id in external_ids:
            if ext_id and ext_id != IS_FALSE:
                template = ProductTemplate.from_external(self, ext_id, False)
                if template:
                    result |= template
                else:
                    unmapped_codes.append(ext_id)

        if raise_error and unmapped_codes:
            es.raise_error(err_code='E111', support_contact=False, unmapped_codes=unmapped_codes)

        return result, unmapped_codes

    def initial_import_features(self, remove_existing_records=False):
        external_features = self.integrationApiImportFeatures(remove_existing_records=remove_existing_records)
        self.integrationApiImportFeatureValues(remove_existing_records=remove_existing_records)

        return external_features

    @expose_for_testing('Import Features (PrestaShop Only)')
    def integrationApiImportFeatures(self, remove_existing_records=False):
        external_records, adapter_external_data = self._import_external(
            'integration.product.feature.external',
            'get_features',
            remove_existing_records=remove_existing_records,
        )
        external_records._map_external(adapter_external_data)
        return external_records

    @expose_for_testing('Import Feature Values (PrestaShop Only)')
    def integrationApiImportFeatureValues(self, remove_existing_records=False):
        external_records, adapter_external_data = self._import_external(
            'integration.product.feature.value.external',
            'get_feature_values',
            remove_existing_records=remove_existing_records,
        )
        external_records._map_external(adapter_external_data)
        return external_records

    def export_feature(self, feature: 'models.Model'):
        self.ensure_one()
        adapter = self.adapter

        feature_data = feature.to_export_format(self)
        code = adapter.export_feature(feature_data)

        feature.create_mapping(self, code, extra_vals={'name': feature.name})

        return code

    def export_feature_value(self, feature_value: 'models.Model'):
        self.ensure_one()
        adapter = self.adapter

        feature_value_data = feature_value.to_export_format(self)
        feature_value_code = adapter.export_feature_value(feature_value_data)

        feature_value_mapping = feature_value.create_mapping(
            self,
            feature_value_code,
            extra_vals={'name': feature_value.name},
        )
        external_feature = self.env['integration.product.feature.external'].search([
            ('code', '=', feature_value_data['feature_id']),
            ('integration_id', '=', self.id),
        ])

        external_feature_value = feature_value_mapping.external_feature_value_id
        external_feature_value.external_feature_id = external_feature.id

        return feature_value_code

    @expose_for_testing('Import Employees (PrestaShop Only)')
    def integrationApiImportEmployees(self, remove_existing_records=False):
        external_records, adapter_external_data = self._import_external(
            'integration.res.users.external',
            'get_users',
            remove_existing_records=remove_existing_records,
        )
        external_records._map_external(adapter_external_data)
        return external_records

    @expose_for_testing('Import Pricelists (PrestaShop Only)')
    def integrationApiImportPricelists(self, remove_existing_records=False):
        external_records, adapter_external_data = self._import_external(
            'integration.product.pricelist.external',
            'get_pricelists',
            remove_existing_records=remove_existing_records,
        )
        external_records._map_external(adapter_external_data)
        return external_records

    @expose_for_testing('Import Product Tags (PrestaShop Only)')
    def integrationApiImportTagsPrestaShop(self, **kwargs):
        if not self.is_integration_prestashop:
            raise NotImplementedError

        tags = self.adapter.get_product_tags()

        Tag = self.env['external.integration.tag']
        imported_tags = Tag.browse()

        for tag in tags:
            imported_tag = Tag._get_or_create_external_tag(
                tag['name'],
                'product',
                self.id,
                external_language_code=tag['id_lang'],
            )
            imported_tags |= imported_tag

        return imported_tags

    def _ensure_settings(self):
        if self.is_prestashop():
            self._ensure_not_null_setting(['url', 'admin_url', 'key'])

        return super()._ensure_settings()

    def _retrieve_webhook_routes(self):
        if self.is_prestashop():
            routes = {
                'orders': [
                    ('Order Created', 'actionValidateOrder'),
                    ('Order Status Updated', 'actionOrderHistoryAddAfter'),
                ],
                'products': [
                    ('Product Updated', 'actionProductUpdate'),
                    # We won't use 'actionProductSave', because he returns not full data
                    # ('Product Created', 'actionProductSave'),
                ],
            }
            return routes
        return super(SaleIntegration, self)._retrieve_webhook_routes()

    def _convert_external_tax(self, tax_id):
        if not self.is_prestashop():
            return super(SaleIntegration, self)._convert_external_tax(tax_id)

        if not isinstance(tax_id, str):
            raise es.ValidationError(_(
                'Invalid tax ID format: Prestashop integration expects product "taxes_id" as a string, '
                'but received a value of type "%s".' % type(tax_id).__name__
            ))

        external_tax_group = self.env['integration.account.tax.group.external'].search([
            ('integration_id', '=', self.id),
            ('code', '=', tax_id),
        ], limit=1)

        external_tax = external_tax_group.default_external_tax_id

        if not external_tax:
            tax_name = external_tax_group.name or tax_id

            raise es.ValidationError(_(
                'It is not possible to import a product into Odoo because there is no default External Tax defined '
                'for the Tax Group "%s".\n\n'
                'Note: The tax group mapping is required in two scenarios:\n'
                '  - The "Product Tax Group" field mapping is active (to assign taxes to products), or\n'
                '  - The "Price Including Tax" option is enabled in the integration settings '
                '(to calculate net prices from tax-inclusive PrestaShop prices).\n\n'
                'To resolve this, click the "Quick Configuration" button in the integration settings "%s" '
                'to define the External Tax for this tax group. Alternatively, disable "Price Including Tax" '
                'in the integration settings if PrestaShop prices do not include taxes.'
            ) % (tax_name, self.name))

        odoo_tax = self.env['account.tax'].from_external(
            self,
            external_tax.code,
        )

        return odoo_tax

    def get_parent_delivery_methods(self, not_mapped_id):
        return self. adapter.get_parent_delivery_methods(not_mapped_id)

    def _fetch_external_carrier(self, carrier_data):
        if self.is_prestashop():
            return self.adapter.get_single_carrier(carrier_data['id'])

        return super(SaleIntegration, self)._fetch_external_carrier(carrier_data)

    def _set_zero_time_zone(self, external_date, to_string=False):
        if self.is_prestashop():
            settings_timezone = self.get_settings_value('PS_TIMEZONE', '')

            if settings_timezone:
                res = super(SaleIntegration, self)._set_zero_time_zone(external_date)
                timezone = pytz.timezone(settings_timezone)
                utc_data = timezone.localize(res).astimezone(pytz.utc)

                if to_string:
                    return datetime.strftime(utc_data, self.datetime_format)
                return utc_data.replace(tzinfo=None)

        return super(SaleIntegration, self)._set_zero_time_zone(external_date, to_string)

    def _get_error_webhook_message(self, error):
        if not self.is_prestashop():
            return super(SaleIntegration, self)._get_error_webhook_message(error)

        if error.args[0] in ['Method Not Allowed', 'Unauthorized']:
            url = 'https://addons.prestashop.com/en/third-party-data-integrations-crm-erp/' \
                  '48921-webhooks-integration.html'
            href_to_module = f'<a href="{url}" target="_blank">' + _('Webhook Integration') + '<a/>'
            message = _(
                'By default, Prestashop does not have webhooks functionality. '
                'Webhooks can be added only via 3rd party modules. We at VentorTech '
                'investigated available solutions on the Prestashop addons market '
                'and found that this %s module is suitable for '
                'this. Also, we communicated with the developers of this module and '
                'asked them to include in their plugin a few changes that are needed '
                'for our connector. So in order to use webhooks functionality with '
                'Prestashop, you need: '
                '<br/> (1) to purchase and install specified module '
                '<br/> (2) In Prestashop admin in the menu '
                '"Advanced Parameters → Webservice" for your API Key add '
                'permissions for "webhooks" resource.'
            ) % href_to_module
            return message

        return _('Prestashop Webhook Error: %s') % error.args[0]

    def _get_weight_integration_fields(self):
        if not self.is_prestashop():
            return super(SaleIntegration, self)._get_weight_integration_fields()

        return [
            'integration_prestashop.prestashop_ecommerce_field_template_weight',
            'integration_prestashop.prestashop_ecommerce_field_variant_weight',
        ]

    @expose_for_testing('Import Customer Groups (PrestaShop Only)')
    def integrationApiImportCustomerGroups(self, remove_existing_records=False):
        """
        Import customer groups from PrestaShop.
        """
        if not self.is_prestashop():
            return False

        groups = self.adapter.get_customer_groups()

        ctx = dict(default_integration_id=self.id)
        ExternalCustomerGroup = self.env['integration.customer.group.external'].with_context(**ctx)
        new_groups = ExternalCustomerGroup

        # Remove existing groups if requested
        if remove_existing_records:
            existing_groups = ExternalCustomerGroup.search([('integration_id', '=', self.id)])
            if existing_groups:
                existing_groups.unlink()

        for group in groups:
            external_id = group['external_id']
            name = group['name']
            record = ExternalCustomerGroup.create_or_update(external_id, name)
            record.create_or_update_mapping()

            new_groups |= record

        # Delete groups that don't exist in PrestaShop (only if not removing all existing records)
        if not remove_existing_records:
            external_groups = ExternalCustomerGroup.search([
                ('integration_id', '=', self.id),
            ])
            (external_groups - new_groups).unlink()

        return new_groups

    def _validate_shop_id(self, shop_id):
        """
        Validate if the shop ID matches the configured shop IDs.
        Returns True if validation passes, False otherwise.
        """
        self.ensure_one()

        if not self.is_integration_prestashop:
            return True

        shop_ids = self.get_settings_value('shop_ids')
        if not shop_ids:
            return True  # If no shop IDs configured, process all shops

        configured_shop_ids = [shop_id.strip() for shop_id in shop_ids.split(',')]
        return shop_id in configured_shop_ids

    def is_importable_order_status(self, statuses: list[str]) -> bool:
        if not self.is_integration_prestashop:
            return super().is_importable_order_status(statuses)

        if not statuses or not statuses[0]:
            raise es.ValidationError(
                _('Invalid order status: empty or missing status provided. Please provide a valid order status ID.')
            )

        try:
            status_int = int(statuses[0])
        except ValueError as e:
            raise es.ValidationError(
                _(
                    'Invalid order status: "%s". Order status must be a valid integer. '
                    'Please provide a numeric status ID.'
                ) % statuses[0]
            ) from e

        allowed_statuses = self.get_importable_order_statuses()

        return status_int in allowed_statuses

    def get_importable_order_statuses(self) -> list[int]:
        if not self.is_integration_prestashop:
            return super().get_importable_order_statuses()

        statuses_dict = self.get_settings_value('receive_orders_filter') or {}
        filter_value = str(statuses_dict.get('filter[current_state]', '[]')).replace('<put state id here>', '')

        # regex to validate the format: "[]", "[1]" or "[12|3|45|679]"
        if not re.fullmatch(r'\[(?:\d+(?:\|\d+)*)?\]', filter_value):
            raise es.ValidationError(
                _(
                    'Invalid receive_orders_filter format: "%s". Expected format: "[1]", "[1|2|3]", or "[]".'
                ) % filter_value
            )

        status_string = filter_value[1:-1].strip()
        status_list = [int(s) for s in status_string.split('|') if s.strip()] if status_string else []

        return status_list

    def is_importable_product(self, product_data: dict) -> bool:
        """Check if a product from webhook data passes the PrestaShop import filter.

        The filter is a JSON dict where keys are product fields and values use
        PrestaShop filter syntax: either a plain value or pipe-separated values
        in brackets.

        Examples of import_products_filter setting::

            {"active": "1"}           — only active products
            {"active": "0"}           — only inactive products
            {"active": "[0|1]"}       — both active and inactive

        Args:
            product_data: Raw product data from the webhook POST body.

        Returns:
            True if the product passes the filter (or no filter is set),
            False otherwise.
        """
        if not self.is_integration_prestashop:
            return super().is_importable_product(product_data)

        raw_filter = self.get_settings_value('import_products_filter') or '{}'
        filter_dict = json.loads(raw_filter)

        for key, filter_value in filter_dict.items():
            product_value = str(product_data.get(key, ''))

            # Handle "[val1|val2|...]" bracket-pipe format
            bracket_match = re.fullmatch(r'\[(.+)\]', filter_value)
            if bracket_match:
                allowed_values = [v.strip() for v in bracket_match.group(1).split('|') if v.strip()]
            else:
                allowed_values = [filter_value.strip()]

            if allowed_values and product_value not in allowed_values:
                return False

        return True

    def run_import_special_prices(self):
        mappings = self.pricelist_mapping_ids.filtered(lambda x: x.pricelist_id)

        for record in mappings:
            record.import_special_prices_mapping()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Special Prices'),
                'message': 'Queue Jobs "Import Special Prices" were created',
                'type': 'success',
                'sticky': False,
            },
        }

    def run_export_special_prices(self):
        mappings = self.pricelist_mapping_ids.filtered(lambda x: x.pricelist_id)
        pricelist_ids = mappings.mapped('pricelist_id')

        if not pricelist_ids:
            raise UserError(_('No pricelists are mapped. Please configure pricelist mappings first.'))

        job_kwargs = self._job_kwargs_prepare_specific_prices(pricelist_ids)

        self \
            .with_context(company_id=self.company_id.id) \
            .with_delay(**job_kwargs) \
            .export_pricelists_multi(pricelist_ids=pricelist_ids.ids)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Export Special Prices'),
                'message': 'Queue Job "Export Special Prices" was created',
                'type': 'success',
                'sticky': False,
            },
        }

    def fetch_pricelist_from_external(self):
        self.integrationApiImportPricelists()

        self = self.with_context(active_id=self.id)
        self.pricelist_mapping_ids = [(6, 0, self._get_default_pricelist_mapping_ids())]

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _is_specific_price_duplicate_validation_enabled(self):
        return True

    def _find_duplicated_specific_prices(self, prices):
        grouped = defaultdict(list)

        for price in prices:
            # Key used to detect duplicate specific priceses
            key = (
                price.get('external_group_id') or '0',
                float(price.get('min_quantity') or 0.0),
                price.get('date_start') or False,
                price.get('date_end') or False,
                float(price.get('reduction') or 0.0),
                price.get('reduction_type') or '',
                float(price.get('price') or 0.0),
                bool(price.get('reduction_tax_included')),
            )
            grouped[key].append(price)

        return {k: v for k, v in grouped.items() if len(v) > 1}

    def _format_specific_price_conditions(self, key):
        (group, qty, date_start, date_end, reduction, reduction_type, price, tax_included) = key
        parts = []

        if price and price > 0:
            parts.append(_('price %s') % price)
        elif reduction:
            if reduction_type == 'percentage':
                parts.append(_('%s%% discount') % (reduction * 100))
            else:
                parts.append(_('discount %s') % reduction)

        if qty:
            parts.append(_('min qty %s') % qty)

        if date_start or date_end:
            parts.append(
                _('valid %(start)s → %(end)s') % {
                    'start': date_start or '-',
                    'end': date_end or '-',
                }
            )
        else:
            parts.append(_('valid always'))

        if group and group != '0':
            parts.append(_('group %s') % group)

        return ' | '.join(parts)

    def _format_duplicated_specific_prices_message(self, duplicates: dict, record: models.Model) -> str:
        def _describe_rule(v):
            item_id = v.get('_item_id')
            item = self.env['product.pricelist.item'].browse(item_id)

            if not item.exists():
                return f'Rule {item_id}'

            if item.applied_on == '1_product':
                return _('Rule %(id)s — applies to product "%(name)s"') % {
                    'id': item.id,
                    'name': item.product_tmpl_id.display_name,
                }

            if item.applied_on == '2_product_category':
                return _('Rule %(id)s — applies to category "%(name)s"') % {
                    'id': item.id,
                    'name': item.categ_id.display_name,
                }

            if item.applied_on == '3_global':
                return _('Rule %(id)s — global rule (applies to all products)') % {
                    'id': item.id,
                }

            return _('Rule %(id)s') % {'id': item.id}

        def _get_pricelist_name(vals):
            for v in vals:
                item_id = v.get('_item_id')
                item = self.env['product.pricelist.item'].browse(item_id)
                if item.exists() and item.pricelist_id:
                    return item.pricelist_id.name
            return _('Unknown Pricelist')

        if record._name == 'product.product':
            target = _('variant "%s"') % record.display_name
        else:
            target = _('product "%s"') % record.display_name

        conflict_blocks = []
        pricelist_name = None

        for idx, (key, vals) in enumerate(duplicates.items(), start=1):
            if not pricelist_name:
                pricelist_name = _get_pricelist_name(vals)

            rules = [_describe_rule(v) for v in vals]
            conditions = self._format_specific_price_conditions(key)

            block = [_('Conflict %(num)s:') % {'num': idx}]
            block += [f'  • {r}' for r in rules]
            block.append(f'  {_("Conditions")}: {conditions}')

            conflict_blocks.append('\n'.join(block))

        return _(
            'Cannot export special prices for %(target)s to PrestaShop.\n\n'
            'Pricelist "%(pricelist)s" contains conflicting rules that produce identical special prices.\n\n'
            '%(conflicts)s\n\n'
            'PrestaShop does not allow multiple specific prices with identical conditions.\n\n'
            'How to fix: open pricelist "%(pricelist)s" and remove one rule from each conflicting group.'
        ) % {
            'target': target,
            'pricelist': pricelist_name or _('Unknown'),
            'conflicts': '\n\n'.join(conflict_blocks),
        }

    def trigger_update_pricelist_items_to_external(self):
        self.ensure_one()

        if not self.is_prestashop():
            return super().trigger_update_pricelist_items_to_external()

        pricelist_ids = (
            self.integration_pricelist_id |
            self.integration_sale_pricelist_id |
            self.pricelist_mapping_ids.mapped('pricelist_id')
        ).filtered('active')

        return pricelist_ids.trigger_update_items_to_external_prestashop(
            integration_id=self.id
        )

    def _job_kwargs_prepare_specific_prices(self, pricelist_ids):
        ids = '-'.join(map(str, pricelist_ids.ids))
        names = ', '.join(pricelist_ids.mapped('name'))
        return {
            'priority': 14,
            'identity_key': f'prepare_prices_from_pricelists-{self.id}_{ids}',
            'description': (
                f'{self.name}: Export. Prepare Specific Prices from Pricelists ({names})'
            ),
        }
