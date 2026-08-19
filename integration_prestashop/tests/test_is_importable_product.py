# See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged

from odoo.addons.integration.tests.config.integration_init import OdooIntegrationInit, load_xml


@tagged('post_install', '-at_install')
class TestIsImportableProductPrestaShop(OdooIntegrationInit):
    '''Test is_importable_product method for PrestaShop integration.'''

    @classmethod
    def setUpClass(cls):
        super(TestIsImportableProductPrestaShop, cls).setUpClass()
        load_xml(
            cls.env,
            module='integration',
            path_file='tests/data',
            filename='init_sale_integration.xml',
        )
        company_id_1 = cls.env.ref('integration.test_integration_company_1')
        cls.integration = cls.env['sale.integration'].create({
            'name': 'Test PrestaShop Integration',
            'type_api': 'prestashop',
            'company_id': company_id_1.id,
        })

    def test_no_filter_returns_true(self):
        '''Empty filter should allow all products.'''
        self.integration.set_settings_value('import_products_filter', '')

        result = self.integration.is_importable_product({'active': '1'})
        self.assertTrue(result)

    def test_plain_value_filter_allows_matching(self):
        '''Product matching a plain filter value should pass.'''
        self.integration.set_settings_value(
            'import_products_filter', '{"active": "1"}',
        )

        self.assertTrue(self.integration.is_importable_product({'active': '1'}))

    def test_plain_value_filter_rejects_non_matching(self):
        '''Product not matching a plain filter value should be rejected.'''
        self.integration.set_settings_value(
            'import_products_filter', '{"active": "1"}',
        )

        self.assertFalse(self.integration.is_importable_product({'active': '0'}))

    def test_bracket_pipe_format_allows_any_listed_value(self):
        '''Bracket-pipe format [val1|val2] should accept any listed value.'''
        self.integration.set_settings_value(
            'import_products_filter', '{"active": "[0|1]"}',
        )

        self.assertTrue(self.integration.is_importable_product({'active': '0'}))
        self.assertTrue(self.integration.is_importable_product({'active': '1'}))

    def test_bracket_pipe_format_rejects_unlisted_value(self):
        '''Bracket-pipe format should reject values not in the list.'''
        self.integration.set_settings_value(
            'import_products_filter', '{"active": "[0|1]"}',
        )

        self.assertFalse(self.integration.is_importable_product({'active': '2'}))

    def test_missing_key_in_product_data_rejects(self):
        '''Product missing a filtered key should be rejected.'''
        self.integration.set_settings_value(
            'import_products_filter', '{"active": "1"}',
        )

        self.assertFalse(self.integration.is_importable_product({'name': 'Test'}))
