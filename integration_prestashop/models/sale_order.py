# See LICENSE file for full copyright and licensing details.

import logging

from odoo import models


_logger = logging.getLogger()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _prestashop_cancel_order(self, *args, **kw):
        # from _perform_method_by_name calling
        _logger.info('SaleOrder _prestashop_cancel_order()')

        status = self.integration_id.sub_status_cancel_id
        self.sub_status_id = status.id

    def _prestashop_shipped_order(self, *args, **kw):
        # from _perform_method_by_name calling
        _logger.info('SaleOrder _prestashop_shipped_order()')

        status = self.integration_id.sub_status_shipped_id
        self.sub_status_id = status.id

    def _prestashop_paid_order(self, *args, **kw):
        # from _perform_method_by_name calling
        _logger.info('SaleOrder _prestashop_paid_order()')

        status = self.integration_id.sub_status_paid_id
        self.sub_status_id = status.id

    def _prepare_vals_for_sale_order_status(self):
        res = super()._prepare_vals_for_sale_order_status()

        if self.integration_id.is_prestashop():
            user_code = '0'

            if self.integration_id.force_user_on_order_status_change:
                external_user = self.env.user.to_external_record(
                    self.integration_id,
                    raise_error=False,
                )
                if external_user:
                    user_code = external_user.code

            res['user_id'] = user_code

        return res

    def _adjust_integration_external_data(self, external_data: dict) -> dict:
        # Perform the common logic in the super() method
        res = super(SaleOrder, self)._adjust_integration_external_data(external_data)

        if not self.integration_id.is_prestashop():
            return res

        if 'payment_transactions' not in external_data:
            txns = self.integration_id.adapter\
                .fetch_order_transactions(self.external_order_ref)

            external_data['payment_transactions'] = txns

        return external_data
