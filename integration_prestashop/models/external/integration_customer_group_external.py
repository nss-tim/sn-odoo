# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, _
from odoo.exceptions import ValidationError


class CustomerGroupExternal(models.Model):
    _name = 'integration.customer.group.external'
    _description = 'External Customer Group'

    _uniq = models.Constraint(
        'unique(integration_id, external_id)',
        'External ID must be unique per integration',
    )

    integration_id = fields.Many2one(
        comodel_name='sale.integration',
        string='E-Commerce Store',
        required=True,
        ondelete='cascade',
    )

    external_id = fields.Char(
        string='External ID',
        required=True,
    )

    name = fields.Char(
        string='Name',
        required=True,
    )

    def create_or_update(self, external_id, name):
        """
            Get an existing customer group or create a new one if it doesn't exist.
        """
        integration_id = self.env.context.get('default_integration_id')
        if not integration_id:
            raise ValidationError(_('Integration ID is required in the context.'))

        group = self.get_record(integration_id, external_id, raise_error=False)

        if group:
            group.write({'name': name})
        else:
            group_vals = {
                'integration_id': integration_id,
                'external_id': external_id,
                'name': name,
            }

            group = self.create(group_vals)

        return group

    def create_or_update_mapping(self):
        self.ensure_one()
        Mapping = self.env['integration.customer.group.mapping']
        internal_field_name, external_field_name = Mapping._mapping_fields

        mapping = Mapping.search([
            ('integration_id', '=', self.integration_id.id),
            (external_field_name, '=', self.id),
        ], limit=1)

        if not mapping:
            mapping = Mapping.create({
                external_field_name: self.id,
                'integration_id': self.integration_id.id,
            })

        return mapping

    def get_record(self, integration_id, external_id, raise_error=True):
        """
            Get the customer group record by external ID.
        """
        domain = [
            ('external_id', '=', external_id),
            ('integration_id', '=', integration_id),
        ]

        group = self.search(domain, limit=1)
        if not group and raise_error:
            raise ValidationError(
                _(
                    f'Customer group with ID "{external_id}" not found in external records.\n\n'
                    f'How to resolve:\n\n'
                    f'\t1. Run an initial import to synchronize master data.\n'
                    f'\t2. Navigate to E-Commerce Integrations → %s → Initial Import → Import Master Data.\n'
                    f'\t3. Wait for the import jobs to complete and then restart this job.\n\n'
                    f'If the issue persists, please contact our support team for assistance: '
                    f'https://support.ventor.tech/'
                ) % self.env['sale.integration'].browse(integration_id).name
            )

        return group
