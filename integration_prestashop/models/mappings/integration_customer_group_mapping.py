# See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class IntegrationCustomerGroupMapping(models.Model):
    _name = 'integration.customer.group.mapping'
    _inherit = 'integration.mapping.mixin'
    _description = 'Integration Customer Group Mapping'
    _mapping_fields = ('sales_team_id', 'external_customer_group_id')
    _mapping_label = 'Customer Group'

    sales_team_id = fields.Many2one(
        string='Odoo Sales Team',
        comodel_name='crm.team',
        ondelete='set null',
    )

    external_customer_group_id = fields.Many2one(
        string='PrestaShop Customer Group',
        comodel_name='integration.customer.group.external',
        required=True,
        ondelete='cascade',
    )

    _uniq_mapping = models.Constraint(
        'unique(integration_id, external_customer_group_id)',
        'Customer Group mapping must be unique per integration',
    )

    def requeue_jobs_if_needed(self):
        # integration.customer.group.external is not a standard external.mixin model
        # and has no associated import jobs to requeue, so this is intentionally a no-op.
        pass
