# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, _
from odoo.exceptions import UserError

from odoo.addons.integration.exceptions import ErrorStore as es


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    feature_line_ids = fields.One2many(
        comodel_name='product.template.feature.line',
        string='Product Features',
        inverse_name='product_tmpl_id',
    )

    combination_default_id = fields.Many2one(
        comodel_name='product.product',
        string='Default Combination',
        help='A combination that will be marked as standard in Prestashop.',
    )

    optional_product_ids = fields.Many2many(
        comodel_name='product.template',
        relation='product_optional_rel',
        column1='src_id',
        column2='dest_id',
        string='Optional Products',
        check_company=True,
    )

    def get_categories(self, integration_id: int):
        integration = self.env['sale.integration'].browse(integration_id)

        if integration.is_prestashop():
            categories = list()

            for category in self.integration_category_ids:
                categories_list = category.parse_parent_external_recursively(integration)
                categories.extend(categories_list)

            return list(set(categories))

        return super(ProductTemplate, self).get_categories(integration_id)

    def get_optional_products_external_ids(self, integration_id):
        self.ensure_one()
        related_products = []
        errors = []
        e101_ids = []
        e102_ids = []

        integration = self.env['sale.integration'].browse(integration_id)

        for optional_product in self.optional_product_ids:
            if not optional_product.active or optional_product.exclude_from_synchronization:
                continue

            optional_product_record = optional_product.to_external_record(
                integration,
                raise_error=False,
            )
            if not optional_product_record:
                if self.id in optional_product.optional_product_ids.ids:
                    e101_ids.append(optional_product)
                else:
                    e102_ids.append(optional_product)
                continue

            try:
                related_products.append(optional_product.to_external(integration))
            except (es.NotMappedToExternal, es.UserError) as e:
                errors.append(str(e))

        error_message = ''

        if e101_ids:
            error_message += es.format_message('E101', parent_product=self, optional_products=e101_ids)
        if e102_ids:
            if e101_ids:
                error_message += '\n\n' + '-' * 100
            error_message += es.format_message('E102', parent_product=self, optional_products=e102_ids)

        if error_message:
            es.raise_error(err_msg=error_message)

        return related_products

    def get_in_stock_delivery_message(self, integration_id: int):
        integration = self.env['sale.integration'].browse(integration_id)

        # Delivery time is not set to "Specific delivery time to this product"
        if integration.delivery_time != 'specific':
            translations = integration.build_external_language_translations(integration, '')
            return {'language': translations['language']}

        if not integration.product_delivery_in_stock:
            raise UserError(
                _(
                    'The "In-stock Delivery Duration Field" field is not specified in the Sale Integration settings. '
                    'Please navigate to: E-Commerce Integrations → %s → Products tab, '
                    'and configure the "In-stock Delivery Duration Field" field.'
                ) % integration.name
            )

        translations = integration.build_external_language_translations(integration, 'message_template_in_stock')
        days = int(getattr(self, integration.product_delivery_in_stock.name))

        # PrestaShop expects an empty value when delivery days is 0.
        if days == 0:
            translations = integration.build_external_language_translations(integration, '')
            return {'language': translations['language']}

        message = {
            'language': {key: value.format(days) for key, value in translations['language'].items()}
        }

        return message

    def get_out_of_stock_delivery_message(self, integration_id: int):
        integration = self.env['sale.integration'].browse(integration_id)

        # Delivery time is not set to "Specific delivery time to this product"
        if integration.delivery_time != 'specific':
            translations = integration.build_external_language_translations(integration, '')
            return {'language': translations['language']}

        if not integration.product_delivery_out_of_stock:
            raise UserError(
                _(
                    'The "Out-of-stock Delivery Duration Field" field is not specified in the '
                    'E-Commerce Store settings. '
                    'Please navigate to: E-Commerce Integrations → Stores → %s → Products tab, '
                    'and configure the "Out-of-stock Delivery Duration Field" field.'
                ) % integration.name
            )

        translations = integration.build_external_language_translations(integration, 'message_template_out_of_stock')
        days = int(getattr(self, integration.product_delivery_out_of_stock.name))

        # PrestaShop expects an empty value when delivery days is 0.
        if days == 0:
            translations = integration.build_external_language_translations(integration, '')
            return {'language': translations['language']}

        message = {
            'language': {key: value.format(days) for key, value in translations['language'].items()}
        }

        return message

    def get_product_features(self, integration_id: int):
        integration = self.env['sale.integration'].browse(integration_id)

        return [
            {
                'id': feature_line.feature_id.to_external_or_export(integration),
                'id_feature_value': feature_line.feature_value_id.to_external_or_export(integration)
            }
            for feature_line in self.feature_line_ids
        ]

    def copy(self, default=None):
        records = super().copy(default=default)

        for template, original_template in zip(records, self):
            template.feature_line_ids = [
                (0, 0, {
                    'feature_id': feature_line.feature_id.id,
                    'feature_value_id': feature_line.feature_value_id.id,
                })
                for feature_line in original_template.feature_line_ids
            ]

        return records
