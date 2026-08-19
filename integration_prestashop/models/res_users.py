# See LICENSE file for full copyright and licensing details.

from odoo import models


class ResUsers(models.Model):
    _name = 'res.users'
    _inherit = ['res.users', 'integration.model.mixin']

    _internal_reference_field = 'email'
