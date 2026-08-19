# See LICENSE file for full copyright and licensing details.

from typing import Dict
from datetime import datetime

from odoo.addons.integration.tools import IS_TRUE
from odoo import api, fields, models


class IntegrationResPartnerProxy(models.TransientModel):
    _inherit = 'integration.res.partner.proxy'

    # Fields for customer
    newsletter = fields.Char(string='Newsletter')
    newsletter_date_add = fields.Char(string='Newsletter Date Add')
    customer_date_add = fields.Char(string='Customer Date Add')
    default_customer_group_id = fields.Char(string='Default Customer Group ID')

    def _prepare_proxy_values(self, integration_id: int, data: dict) -> Dict:
        """
        Override to add customer-specific fields.
        """
        vals = super(IntegrationResPartnerProxy, self)._prepare_proxy_values(integration_id, data)

        integration = self.env['sale.integration'].browse(integration_id)
        if integration.is_prestashop():
            # We add customer-specific fields
            type_ = self.env.context.get('type_')
            if vals and type_ == 'customer':
                vals.update({
                    'newsletter': data.get('newsletter', '').strip(),
                    'newsletter_date_add': data.get('newsletter_date_add', ''),
                    'customer_date_add': data.get('customer_date_add', ''),
                    'default_customer_group_id': data.get('default_customer_group_id', ''),
                })

        return vals

    def _prepare_partner_vals(self):
        partner_vals = super(IntegrationResPartnerProxy, self)._prepare_partner_vals()

        if not self.integration_id.is_prestashop():
            return partner_vals

        # Adding PrestaShop specific fields
        integration = self.integration_id.sudo()
        if self.newsletter and integration.subscribed_to_newsletter_id:
            newsletter_subscription_status = self.newsletter == IS_TRUE
            partner_vals[integration.subscribed_to_newsletter_id.name] = newsletter_subscription_status  # NOQA

        if self.newsletter_date_add and integration.newsletter_registration_date_id:
            try:
                newsletter_registration_date = datetime.strptime(
                    self.newsletter_date_add, self.integration_id.datetime_format)
            except ValueError:
                newsletter_registration_date = False

            partner_vals[integration.newsletter_registration_date_id.name] = newsletter_registration_date  # NOQA

        if self.customer_date_add and integration.customer_registration_date_id:
            try:
                customer_registration_date = datetime.strptime(
                    self.customer_date_add, self.integration_id.datetime_format)
            except ValueError:
                customer_registration_date = False

            partner_vals[integration.customer_registration_date_id.name] = customer_registration_date  # NOQA

        if self.other and integration.additional_address_information:
            partner_vals[integration.additional_address_information.name] = self.other

        # Get customer group field for res.partner model from the integration
        if self.default_customer_group_id and integration.default_customer_group_field_id:
            customer_group = self.env['integration.customer.group.external'].get_record(
                integration.id, self.default_customer_group_id, raise_error=True)
            partner_vals[integration.default_customer_group_field_id.name] = customer_group.name

        return partner_vals

    def _post_update_partner(self, partner: models.Model):
        if not self.integration_id.is_prestashop():
            return partner

        # Get customer group field for res.partner model from the integration
        customer_group_field = self.integration_id.default_customer_group_field_id
        if not customer_group_field:
            return partner

        if self.default_customer_group_id and not partner[customer_group_field.name]:
            customer_group = self.env['integration.customer.group.external'].get_record(
                self.integration_id.id, self.default_customer_group_id, raise_error=True,
            )
            partner.write({
                customer_group_field.name: customer_group.name,
            })

        return partner

    @api.model
    def _prepare_address_vals(self) -> Dict:
        address_vals = super(IntegrationResPartnerProxy, self)._prepare_address_vals()

        # Adding Other Specific fields
        if self.other:
            additional_address_information_field = self.integration_id.additional_address_information
            if additional_address_information_field:
                address_vals[additional_address_information_field.name] = self.other

        return address_vals
