# See LICENSE file for full copyright and licensing details.

from odoo import models


class IntegrationResUsersExternal(models.Model):
    _name = 'integration.res.users.external'
    _inherit = 'integration.external.mixin'
    _description = 'Integration Res Users External'
    _odoo_model = 'res.users'
