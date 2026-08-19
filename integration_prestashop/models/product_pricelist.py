# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, _
from odoo.exceptions import UserError


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def trigger_force_export_prestashop(self):
        price_mapping_ids = self.env['integration.product.pricelist.mapping'].search([
            ('pricelist_id', 'in', self.ids),
            ('integration_id.state', '=', 'active'),
            ('integration_id.type_api', '=', 'prestashop'),
        ])
        if not price_mapping_ids:
            raise UserError(self._integration_not_mapped_error())

        for integration in price_mapping_ids.mapped('integration_id'):
            map_ids = price_mapping_ids.filtered(lambda x: x.integration_id == integration)
            pricelist_ids = map_ids.mapped('pricelist_id')

            job_kwargs = integration._job_kwargs_prepare_specific_prices(pricelist_ids)

            context = {
                'company_id': integration.company_id.id,
                'job_integration_id': integration.id,
                'job_integration_job_type': 'pricelist',
            }
            integration \
                .with_context(**context) \
                .with_delay(**job_kwargs) \
                .export_pricelists_multi(pricelist_ids=pricelist_ids.ids)

        return self._return_display_notification()

    def trigger_update_items_to_external_prestashop(self, integration_id=False):
        domain = [
            ('pricelist_id', 'in', self.ids),
            ('integration_id.state', '=', 'active'),
            ('integration_id.type_api', '=', 'prestashop'),
        ]
        if integration_id:
            domain.append(('integration_id', '=', integration_id))

        price_mapping_ids = self.env['integration.product.pricelist.mapping'].search(domain)

        if not price_mapping_ids:
            message = self._integration_not_mapped_error()
            if integration_id:
                return message
            raise UserError(message)

        message_list = list()
        value = fields.Datetime.now()

        for integration in price_mapping_ids.mapped('integration_id'):
            force_sync_pricelist = False
            map_ids = price_mapping_ids.filtered(lambda x: x.integration_id == integration)
            active_pricelist_ids = map_ids.mapped('pricelist_id').filtered('active').ids

            item_ids = self._prepare_prestashop_pricelist_item_ids(
                integration=integration,
                active_pricelist_ids=active_pricelist_ids,
            )

            if not item_ids:
                force_sync_pricelist = self._prepare_prestashop_force_sync_pricelist(integration)

            integration.update_last_update_pricelist_items_to_now(value)

            if not item_ids and not force_sync_pricelist:
                continue

            pricelist_ids = item_ids.mapped('pricelist_id')
            job_kwargs = integration._job_kwargs_prepare_specific_prices(pricelist_ids)

            context = {
                'company_id': integration.company_id.id,
                'job_integration_id': integration.id,
                'job_integration_job_type': 'pricelist',
            }
            job = integration \
                .with_context(**context) \
                .with_delay(**job_kwargs) \
                .export_pricelists_multi(item_ids=item_ids.ids, updating=True)

            message_list.append(
                _('%s: Find Products for Specific Prices job created: %s') % (integration.name, job)
            )

        if integration_id:
            message = '\n'.join(message_list) or self._integration_no_need_message()
            return self._return_display_notification(message)

        if not message_list:
            message = self._integration_no_need_message()
            return self._return_display_notification(message)

        return self._return_display_notification()

    def _prepare_prestashop_pricelist_item_ids(self, integration, active_pricelist_ids):
        all_item_ids = self.env['product.pricelist.item'].search([
            ('write_date', '>=', integration.last_update_pricelist_items),
            ('pricelist_id', 'in', active_pricelist_ids),
        ])

        newly_created = all_item_ids.filtered(lambda r: r.create_date == r.write_date)

        if newly_created:
            self.env.cr.execute("""
                SELECT item_id FROM integration_product_pricelist_item_external
                WHERE integration_id = %s AND item_id IN %s
            """, (integration.id, tuple(newly_created.ids)))
            imported_ids = {row[0] for row in self.env.cr.fetchall()}
        else:
            imported_ids = set()

        return all_item_ids - newly_created.browse(imported_ids)

    def _prepare_prestashop_force_sync_pricelist(self, integration):
        query = """
            SELECT COUNT(p.id) FROM integration_product_template_mapping AS m
            JOIN product_template as p
                ON m.integration_id = %s
                AND m.template_id = p.id
                AND p.to_force_sync_pricelist = true
                AND p.exclude_from_synchronization = false
        """

        self.env.cr.execute(query, (integration.id,))
        select = self.env.cr.fetchone()
        return select and select[0]
