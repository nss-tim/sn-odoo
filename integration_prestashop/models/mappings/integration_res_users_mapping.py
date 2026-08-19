# See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class IntegrationResUsersMapping(models.Model):
    _name = 'integration.res.users.mapping'
    _inherit = 'integration.mapping.mixin'
    _description = 'Integration Res Users Mapping'
    _mapping_fields = ('user_id', 'external_user_id')
    _mapping_label = 'User'

    user_id = fields.Many2one(
        string='Odoo User',
        comodel_name='res.users',
        ondelete='set null',
    )

    external_user_id = fields.Many2one(
        string='External User',
        comodel_name='integration.res.users.external',
        required=True,
        ondelete='cascade',
    )
