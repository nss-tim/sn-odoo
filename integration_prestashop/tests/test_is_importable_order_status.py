# See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.exceptions import ValidationError

from odoo.addons.integration.tests.config.integration_init import OdooIntegrationInit, load_xml


@tagged('post_install', '-at_install')
class TestIsImportableOrderStatusPrestaShop(OdooIntegrationInit):
    '''Test is_importable_order_status method for PrestaShop integration.'''

    @classmethod
    def setUpClass(cls):
        super(TestIsImportableOrderStatusPrestaShop, cls).setUpClass()
        # Load base integration XML data first (needed for refs)
        load_xml(
            cls.env,
            module='integration',
            path_file='tests/data',
            filename='init_sale_integration.xml',
        )
        company_id_1 = cls.env.ref('integration.test_integration_company_1')
        cls.prestashop_integration = cls.env['sale.integration'].create({
            'name': 'Test PrestaShop Integration',
            'type_api': 'prestashop',
            'company_id': company_id_1.id,
        })
        # Clear the default receive_orders_filter to avoid placeholder values
        cls.prestashop_integration.set_settings_value('receive_orders_filter', '[]')

    def test_prestashop_empty_filter_returns_false(self):
        '''Test PrestaShop integration with empty filter returns False.'''
        result = self.prestashop_integration.is_importable_order_status(['1'])
        self.assertFalse(result)

    def test_prestashop_single_status_allowed(self):
        '''Test PrestaShop integration with single status in filter.'''
        self.prestashop_integration.set_settings_value('receive_orders_filter', {
            'filter[current_state]': '[1]'
        })

        result = self.prestashop_integration.is_importable_order_status(['1'])
        self.assertTrue(result)

        result = self.prestashop_integration.is_importable_order_status(['2'])
        self.assertFalse(result)

    def test_prestashop_multiple_statuses_allowed(self):
        '''Test PrestaShop integration with multiple statuses in filter.'''
        self.prestashop_integration.set_settings_value('receive_orders_filter', {
            'filter[current_state]': '[1|2|3|4|5]'
        })

        # Test allowed statuses
        for status in ['1', '2', '3', '4', '5']:
            result = self.prestashop_integration.is_importable_order_status([status])
            self.assertTrue(result, f'Status {status} should be allowed')

        # Test non-allowed status
        result = self.prestashop_integration.is_importable_order_status(['6'])
        self.assertFalse(result)

    def test_prestashop_large_status_list(self):
        '''Test PrestaShop integration with large status list.'''
        self.prestashop_integration.set_settings_value('receive_orders_filter', {
            'filter[current_state]': '[1|2|3|4|5|6|7|8|9|10|11|12|13]'
        })

        # Test some allowed statuses
        for status in ['1', '5', '10', '13']:
            result = self.prestashop_integration.is_importable_order_status([status])
            self.assertTrue(result, f'Status {status} should be allowed')

        # Test non-allowed status
        result = self.prestashop_integration.is_importable_order_status(['14'])
        self.assertFalse(result)

    def test_prestashop_invalid_input_status(self):
        '''Test PrestaShop integration with invalid input status raises ValidationError.'''
        self.prestashop_integration.set_settings_value('receive_orders_filter', {
            'filter[current_state]': '[1|2|3]'
        })

        # Test with invalid status
        with self.assertRaises(ValidationError) as context:
            self.prestashop_integration.is_importable_order_status(['invalid'])

        self.assertIn('Invalid order status: "invalid"', str(context.exception))
        self.assertIn('Order status must be a valid integer', str(context.exception))

    def test_prestashop_empty_status_list(self):
        '''Test PrestaShop integration with empty status list raises ValidationError.'''
        self.prestashop_integration.set_settings_value('receive_orders_filter', {
            'filter[current_state]': '[1|2|3]'
        })

        # Test with empty status list
        with self.assertRaises(ValidationError) as context:
            self.prestashop_integration.is_importable_order_status([])

        self.assertIn('Invalid order status: empty or missing status provided', str(context.exception))

    def test_prestashop_empty_status_string(self):
        '''Test PrestaShop integration with empty status string raises ValidationError.'''
        self.prestashop_integration.set_settings_value('receive_orders_filter', {
            'filter[current_state]': '[1|2|3]'
        })

        # Test with empty status string
        with self.assertRaises(ValidationError) as context:
            self.prestashop_integration.is_importable_order_status([''])

        self.assertIn('Invalid order status: empty or missing status provided', str(context.exception))

    def test_prestashop_invalid_filter_format(self):
        '''Test PrestaShop integration with invalid filter format raises ValidationError.'''
        # Test with invalid filter format (missing brackets)
        self.prestashop_integration.set_settings_value('receive_orders_filter', {
            'filter[current_state]': '1|2|3'  # Missing brackets
        })

        with self.assertRaises(ValidationError) as context:
            self.prestashop_integration.is_importable_order_status(['1'])

        self.assertIn('Invalid receive_orders_filter format: "1|2|3"', str(context.exception))
        self.assertIn('Expected format: "[1]", "[1|2|3]", or "[]".', str(context.exception))

    def test_prestashop_invalid_status_ids_in_filter(self):
        '''Test PrestaShop integration with invalid status IDs in filter raises ValidationError.'''
        # Test with invalid status IDs in filter
        self.prestashop_integration.set_settings_value('receive_orders_filter', {
            'filter[current_state]': '[1|invalid|3|<put state id here>]'
        })

        with self.assertRaises(ValidationError) as context:
            self.prestashop_integration.is_importable_order_status(['1'])

        self.assertIn('Invalid receive_orders_filter format: "[1|invalid|3|]"', str(context.exception))
        self.assertIn('Expected format: "[1]", "[1|2|3]", or "[]".', str(context.exception))

    def test_prestashop_non_string_filter(self):
        '''Test PrestaShop integration with non-string filter raises TypeError.'''
        # Test with non-string filter value
        self.prestashop_integration.set_settings_value('receive_orders_filter', {
            'filter[current_state]': 123  # Not a string
        })

        try:
            self.prestashop_integration.is_importable_order_status(['1'])
            assert False, 'Expected ValidationError due to non-string filter'
        except ValidationError:
            assert True
