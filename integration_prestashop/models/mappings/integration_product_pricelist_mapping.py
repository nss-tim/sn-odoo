# See LICENSE file for full copyright and licensing details.

from odoo import models, _

from odoo.addons.integration.exceptions import ErrorStore as es


class IntegrationProductPricelistMapping(models.Model):
    _inherit = 'integration.product.pricelist.mapping'

    def import_special_prices_mapping(self):
        self.ensure_one()
        if not self.integration_id.is_integration_prestashop:
            raise es.UserError(_('This function is not available for this integration.'))

        external = self.external_pricelist_id
        job_kwargs = external._job_kwargs_import_special_prices(self.pricelist_id)

        context = {
            'company_id': self.integration_id.company_id.id,
            'job_integration_id': self.integration_id.id,
            'job_integration_job_type': 'pricelist',
        }
        external.with_context(**context) \
            .with_delay(**job_kwargs).import_special_prices_external()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('%s: Import Special Prices') % external.name,
                'message': _('%s: Queue Jobs "Import Special Prices" were created') % external.name,
                'type': 'success',
                'sticky': False,
            },
        }
