# See LICENSE file for full copyright and licensing details.

from odoo import models


class ECommerceProductCategory(models.Model):
    _inherit = 'ecommerce.product.category'

    def to_export_format(self, integration: 'models.Model'):
        res = super(ECommerceProductCategory, self).to_export_format(integration)

        if integration.is_prestashop():
            if not res['parent_id']:
                root_category = self.env['integration.ecommerce.product.category.external'].search([
                    ('is_root_category', '=', True),
                    ('integration_id', '=', integration.id),
                ], limit=1)

                res['parent_id'] = root_category.code

        return res

    def parse_parent_external_recursively(self, integration):
        external_category = self.to_external_record_or_export(integration)
        return external_category._get_parent_recursively()

    def export_with_integration_to_record(self, integration):
        self.ensure_one()
        integration.export_category(self)
        return self.to_external_record(integration)
