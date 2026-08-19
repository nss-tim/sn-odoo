# See LICENSE file for full copyright and licensing details.

from odoo import models


class ExternalOrderTransaction(models.Model):
    _inherit = 'external.order.transaction'

    def _compute_is_ecommerce_ok(self):
        for rec in self:
            if rec.integration_id and rec.integration_id.is_prestashop():
                rec.is_ecommerce_ok = (rec.external_status == 'success' and rec.transaction)
            else:
                super(ExternalOrderTransaction, rec)._compute_is_ecommerce_ok()
