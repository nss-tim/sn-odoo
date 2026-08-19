# See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields

from ..prestashop_api import Client


API_NO = 'no'
API_YES = 'yes'
API_NOT_USED = 'not_used'

USED_RESOURCES = {
    'addresses': '10001',  # GET, PUT, POST, DELETE, REQUIRED
    'carriers': '10001',
    'categories': '11111',
    'combinations': '11111',
    'configurations': '10001',
    'countries': '10001',
    'customers': '10001',
    'currencies': '10001',
    'groups': '10001',
    'images': '11111',
    'languages': '10001',
    'messages': '10001',
    'orders': '10001',
    'order_carriers': '11001',
    'order_details': '10001',
    'order_states': '10001',
    'order_payments': '10001',
    'manufacturers': '10100',
    'products': '11111',
    'product_options': '11111',
    'product_option_values': '11111',
    'product_features': '11111',
    'product_feature_values': '11111',
    'states': '10001',
    'stock_availables': '11001',
    'taxes': '10001',
    'tax_rule_groups': '10001',
    'webhooks': '10110',
    'specific_prices': '10111',
    'employees': '10001',
    'order_histories': '00101',
    'tax_rules': '10001',
}


class PrestashopAccessScopeLine(models.TransientModel):
    _name = 'prestashop.access.scope.line'
    _description = 'Prestashop Access Scope Line'
    _order = 'resource_name asc'

    def _get_api_method_usage(self):
        return [(API_YES, 'Yes'), (API_NO, 'No'), (API_NOT_USED, 'Not Used')]

    resource_name = fields.Char(
        string='Resource',
    )
    method_get = fields.Selection(
        selection=_get_api_method_usage,
        string='GET',
    )
    method_put = fields.Selection(
        selection=_get_api_method_usage,
        string='PUT',
    )
    method_post = fields.Selection(
        selection=_get_api_method_usage,
        string='POST',
    )
    method_delete = fields.Selection(
        selection=_get_api_method_usage,
        string='DELETE',
    )
    method_required = fields.Selection(
        selection=_get_api_method_usage,
        string='Required',
    )
    integration_auth_prestashop_id = fields.Many2one(
        string='Integration Auth Prestashop',
        comodel_name='integration.auth.prestashop',
        ondelete='cascade',
    )


class IntegrationAuthPrestashop(models.TransientModel):
    _name = 'integration.auth.prestashop'
    _inherit = 'integration.auth.abstract'
    _description = 'Prestashop Integration Authentication'

    state = fields.Selection(
        selection=[
            ('authentication', 'Authentication'),
            ('authorization', 'Authorization'),
        ],
        string='State',
        default='authentication',
    )

    admin_url = fields.Char(
        string='Admin URL',
    )

    configuration_scope_ids = fields.One2many(
        comodel_name='prestashop.access.scope.line',
        inverse_name='integration_auth_prestashop_id',
        string='Access Scopes Lines',
    )

    is_valid_access_scopes = fields.Boolean(
        string='Proven Access Scopes',
        compute='_compute_is_valid_access_scopes',
    )

    @api.depends('configuration_scope_ids')
    def _compute_is_valid_access_scopes(self):
        for rec in self:
            value = True
            scopes = rec.configuration_scope_ids

            if scopes:
                value1 = not any([x.method_get == API_NO for x in scopes if x.method_required == API_YES])
                value2 = not any([x.method_put == API_NO for x in scopes if x.method_required == API_YES])
                value3 = not any([x.method_post == API_NO for x in scopes if x.method_required == API_YES])
                value4 = not any([x.method_delete == API_NO for x in scopes if x.method_required == API_YES])

                value = value1 and value2 and value3 and value4

            rec.is_valid_access_scopes = value

    def set_authentication_state(self):
        self.state = 'authentication'

    def set_authorization_state(self):
        self.state = 'authorization'

    # Open Form

    def open_form_authentication(self):
        self.ensure_one()
        self.set_authentication_state()
        return self.open_form()

    def open_form_authorization(self):
        self.ensure_one()

        self.set_authorization_state()

        action = self.sudo().env.ref(
            'integration_prestashop.action_view_prestashop_integration_authorization').read()[0]
        action['res_id'] = self.id

        return action

    # Save Credentials
    def save_credentials(self, **kw):
        self.ensure_one()

        integration = self.integration_id

        integration.set_settings_value('url', self.url)
        integration.set_settings_value('admin_url', self.admin_url)
        integration.set_settings_value('key', self.key)

        integration.set_settings_value('access_granted', str(self.access_granted))

        for key, value in kw.items():
            integration.set_settings_value(key, value)

        return self.close_form()

    # Private Methods

    def _build_scope_lines(self):
        self.ensure_one()
        self.configuration_scope_ids.unlink()

        adapter = self.integration_id.adapter

        resources = adapter.get_api_resources()

        def get_setting_value(res_name, res_used, method_name):
            # In old PrestaShop 1.6 version there are not all resources available,
            # so we need to skip them. At the moment, we need to skip
            # employees and messages resources.
            if res_name in ('employees', 'messages'):
                if res_name not in resources.get('api', {}):
                    return API_NOT_USED

            if method_name == 'required':
                return API_YES if int(res_used) else API_NO

            if not int(res_used):
                return API_NOT_USED

            value = resources.get('api', {}).get(res_name, {}).get('attrs', {}).get(method_name)
            return API_YES if value == 'true' else API_NO

        values_list = []
        for resource_name, usage in USED_RESOURCES.items():
            values = {
                'resource_name': resource_name,
                'method_get': get_setting_value(resource_name, usage[0], 'get'),
                'method_put': get_setting_value(resource_name, usage[1], 'put'),
                'method_post': get_setting_value(resource_name, usage[2], 'post'),
                'method_delete': get_setting_value(resource_name, usage[3], 'delete'),
                'method_required': get_setting_value(resource_name, usage[4], 'required'),
                'integration_auth_prestashop_id': self.id,
            }
            values_list.append(values)

        self.env['prestashop.access.scope.line'].create(values_list)

    def _build_and_test_client_from_wizard(self):
        self.ensure_one()

        client = Client(
            self.url,
            self.key,
        )

        resources = client.get('')

        return bool(resources)
