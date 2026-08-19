# See LICENSE file for full copyright and licensing details.

from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def to_export_format(self, integration: 'models.Model'):
        result = super().to_export_format(integration)

        if integration.is_integration_prestashop:
            result['is_default'] = (self.product_tmpl_id.combination_default_id.id == self.id)

        return result
