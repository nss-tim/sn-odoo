#  See LICENSE file for full copyright and licensing details.

import re

from odoo import models, fields, _
from odoo.exceptions import UserError


class QuickConfigurationPrestashop(models.TransientModel):
    _name = 'configuration.wizard.prestashop'
    _inherit = 'configuration.wizard'
    _description = 'Quick Configuration for Prestashop'
    _steps = [
        ('step_intro', 'Introduction'),
        ('step_languages', 'Step 1. Languages Mapping'),
        ('step_tax_group', 'Step 2. Configure Default Taxes for each Tax Rule'),
        ('step_order_status', 'Step 3. Sales Orders statuses management'),
        ('step_finish', 'Finish')
    ]

    state = fields.Char(
        default='step_intro',
    )

    configuration_tax_group_ids = fields.One2many(
        comodel_name='configuration.wizard.prestashop.tax.group',
        inverse_name='configuration_wizard_id',
        string='Taxes for Each Tax Rule',
    )
    order_status_ids = fields.Many2many(
        comodel_name='integration.sale.order.sub.status.external',
        string='Receive Orders in Status',
        relation='configuration_wizard_prestashop_status_rel',
        domain='[("integration_id", "=", integration_id)]',
    )

    # Step Intro
    def run_before_step_intro(self):
        pass

    # Step Languages
    def run_after_step_languages(self):
        res = super().run_after_step_languages()
        if res:
            self.integration_id.set_settings_value('language_id', self.language_default_id.code)
        return res

    # Step Tax Group
    def run_before_step_tax_group(self):
        self.integration_id.integrationApiImportTaxes()
        self.configuration_tax_group_ids.unlink()

        values_list = list()
        default_vals = dict(configuration_wizard_id=self.id)

        tax_group_ids = self.env['integration.account.tax.group.external'].search([
            ('integration_id', '=', self.integration_id.id),
        ])
        for tax_group in tax_group_ids:
            values = {
                **default_vals,
                'external_tax_group_id': tax_group.id,
                'default_external_tax_id': tax_group.default_external_tax_id.id,
                'sequence': tax_group.sequence,
            }
            values_list.append(values)

        self.env['configuration.wizard.prestashop.tax.group'].create(values_list)

    def run_after_step_tax_group(self):
        for line in self.configuration_tax_group_ids:
            tax_group = line.external_tax_group_id
            tax_group.default_external_tax_id = line.default_external_tax_id.id
            tax_group.sequence = line.sequence

        return True

    # Step Order Status
    def run_before_step_order_status(self):
        self.integration_id.integrationApiImportSaleOrderStatuses()

        importable_statuses = self.integration_id.get_importable_order_statuses()

        if importable_statuses:
            order_statuses = self.env['integration.sale.order.sub.status.external'].search([
                ('integration_id', '=', self.integration_id.id),
                ('code', 'in', importable_statuses),
            ])
            self.order_status_ids = [(6, 0, order_statuses.ids)]

        self.run_action_on_cancel_so = self.integration_id.run_action_on_cancel_so
        self.sub_status_cancel_id = self.integration_id.sub_status_cancel_id

        self.export_tracking_job_enabled = self.integration_id.export_tracking_job_enabled
        self.sub_status_shipped_id = self.integration_id.sub_status_shipped_id

        self.run_action_on_so_invoice_status = self.integration_id.run_action_on_so_invoice_status
        self.sub_status_paid_id = self.integration_id.sub_status_paid_id

    def run_after_step_order_status(self):
        if not self.order_status_ids:
            raise UserError(_(
                'You must select at least one store order status to be imported.'
            ))

        ids = [x.code for x in self.order_status_ids]

        receive_filter = self.integration_id.get_class().default_receive_orders_filter
        receive_filter = re.sub('<put state id here>', '|'.join(ids), receive_filter)

        self.integration_id.set_settings_value('receive_orders_filter', receive_filter)

        self.integration_id.run_action_on_cancel_so = self.run_action_on_cancel_so
        self.integration_id.export_tracking_job_enabled = self.export_tracking_job_enabled
        self.integration_id.run_action_on_so_invoice_status = self.run_action_on_so_invoice_status

        self.integration_id.sub_status_cancel_id = self.sub_status_cancel_id
        self.integration_id.sub_status_shipped_id = self.sub_status_shipped_id
        self.integration_id.sub_status_paid_id = self.sub_status_paid_id

        if self.sub_status_cancel_id or self.sub_status_shipped_id:
            self.integration_id.export_sale_order_status_job_enabled = True

        return True

    @staticmethod
    def get_form_xml_id():
        return 'integration_prestashop.view_configuration_wizard'


class QuickConfigurationPrestashopTaxGroup(models.TransientModel):
    _name = 'configuration.wizard.prestashop.tax.group'
    _inherit = 'configuration.wizard.tax.group.abstract'
    _description = 'Quick Configuration Prestashop Tax Group'

    sequence = fields.Integer(
        help=(
            'When exporting from Odoo to Prestashop, take the most priority item first '
            'in Order to define which Odoo Tax correspond to which tax group.'
        ),
    )
    configuration_wizard_id = fields.Many2one(
        comodel_name='configuration.wizard.prestashop',
    )
    external_tax_group_id = fields.Many2one(
        string='Prestashop External Tax Rule',
    )
