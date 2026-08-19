# See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.exceptions import UserError
from odoo.addons.integration.tools import Adapter
from odoo.addons.integration.exceptions import ApiImportError
from odoo.addons.integration.tests.config.integration_init import OdooIntegrationBase, load_xml

from .patch.prestashop_api_patch import PrestashopAPIClientPatchTest, PrestashopClientPatchTest


ORDER_ID = '100501'


class TestIntegrationPrestashopCommon(OdooIntegrationBase):

    @classmethod
    def setUpClass(cls):
        super(TestIntegrationPrestashopCommon, cls).setUpClass()

        # Load base integration XML data first (needed for integration_user)
        load_xml(
            cls.env,
            module='integration',
            path_file='tests/data',
            filename='init_sale_integration.xml',
        )

        # Activate currency
        cls.env.ref('base.EUR').active = True

        # Install language
        cls.env['base.language.install'].create({
            'lang_ids': [(6, 0, [
                cls.env.ref('base.lang_nl').id,
                cls.env.ref('base.lang_pl').id,
            ])]
        }).lang_install()

        # Load data
        load_xml(
            cls.env,
            module='integration_prestashop',
            path_file='tests/data/',
            filename='init_sale_integration_prestashop.xml',
        )

        # Apply company to existing user
        cls.company = cls.env.ref('integration_prestashop.test_integration_company_prestashop_nl')
        # Access integration_user via env.ref since it's set up in parent's setUp (instance method)
        integration_user = cls.env.ref('integration.integration_user')
        integration_user.company_ids = [(4, cls.company.id)]

        # Patch adapter
        cls.integration = cls.env.ref('integration_prestashop.integration_prestashop_test_1')
        cls.classPatch(type(cls.integration), 'get_class', cls._get_class_patch)

        # Activate all mapping fields except optional Product Brand mapping when
        # product_brand is not installed in the current test environment.
        mappings = cls.env['product.ecommerce.field.mapping'].with_context(active_test=False).search([
            ('integration_id', '=', cls.integration.id),
        ])

        product_brand_installed = bool(cls.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'product_brand'),
            ('state', '=', 'installed'),
        ]))

        mappings.filtered(
            lambda m: product_brand_installed or m.technical_name != 'id_manufacturer'
        ).write({
            'active': True,
            'export_enabled': True,
            'import_enabled': True,
        })

        # Update WH data
        cls.wh = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)])
        cls.wh.ensure_one()

        cls.invoice_journal = cls.env.ref(
            'integration_prestashop.integration_prestashop_account_sales_journal_test')

        # Import languages
        external_langs = cls.integration.integrationApiImportLanguages()

        nl = external_langs.filtered(lambda x: x.external_reference == 'nl_nl')
        nl.mapping_record.write({'language_id': cls.env.ref('base.lang_nl').id})
        cls.nl_ext_id = nl.code
        cls.nl_id = nl.odoo_record.id

        pl = external_langs.filtered(lambda x: x.external_reference == 'pl_pl')
        pl.mapping_record.write({'language_id': cls.env.ref('base.lang_pl').id})
        cls.pl_ext_id = pl.code
        cls.pl_id = pl.odoo_record.id

        # Import payment methods
        cls.integration.integrationApiImportPaymentMethods()

        # Import sale order statuses
        cls.integration.integrationApiImportSaleOrderStatuses()

        # Import categories
        external_categories = cls.integration.integrationApiImportCategories()
        external_categories.import_categories()
        cls.integration_category_ids = external_categories.mapped(lambda x: x.odoo_record.id)

        # Import taxes
        external_taxe = cls.integration.integrationApiImportTaxes()
        external_taxe.action_import_taxes_from_external()

        external_tax_group = cls.env['integration.account.tax.group.external'].search([
            ('integration_id', '=', cls.integration.id),
        ])
        external_tax_group.ensure_one()
        external_tax_group.default_external_tax_id = external_taxe.id
        cls.tax_100_id = external_taxe.odoo_record.id

        # Import features
        external_features = cls.integration.initial_import_features()
        external_features.run_import_features()

        # Import attributes
        external_attributes = cls.integration.initial_import_attributes()
        external_attributes.run_import_attributes()

        # Accounts adjustments
        cls.product1 = cls.env.ref('integration_prestashop.prestashop_product_product_49620724449001')
        t = cls.product1.product_tmpl_id.with_company(cls.company)
        t.property_account_income_id = cls.env.ref('integration_prestashop.integration_prestashop_account_a_income')
        t.property_account_expense_id = cls.env.ref(
            'integration_prestashop.integration_prestashop_account_a_expense')

        cls.product2 = cls.env.ref('integration_prestashop.prestashop_product_product_47738503495001')
        t = cls.product2.product_tmpl_id.with_company(cls.company)
        t.property_account_income_id = cls.env.ref('integration_prestashop.integration_prestashop_account_a_income')
        t.property_account_expense_id = cls.env.ref(
            'integration_prestashop.integration_prestashop_account_a_expense')

    @property
    def adapter(self):
        return self.integration.adapter

    def _get_class_patch(self):
        return PrestashopAPIClientPatchTest

    def _set_permissions(self, orm_record):
        orm_record = orm_record.with_user(self.integration_user.id).with_company(self.company)
        return orm_record.with_context(company_id=self.company.id, **self._ctx)


@tagged('post_install', '-at_install', 'test_integration_prestashop')
class TestIntegrationPrestashop(TestIntegrationPrestashopCommon):

    def test_search_read_product(self):
        template_list = self.adapter._client.model('product').search_read(
            filters={'id': '9100500'},
        )

        self.assertEqual(template_list[0]['id'], '9100500')

    def test_convert_product_fields_in_and_out(self):
        t, (v1, v2), errors, __ = self.integration._import_external_product(
            ['9100500'],
            try_to_map=False,
            raise_error=False,
        )

        # 1. Test external records
        self.assertEqual(t.name, 'Mountain fox cushion kjhz2n31_test-nl')
        self.assertEqual(t.code, '9100500')
        self.assertEqual(t.external_reference, 'demo_15_jqhxz3_test_main')
        self.assertEqual(t.external_barcode, '432432432432')

        self.assertEqual(v1.name, 'Mountain fox cushion kjhz2n31_test-nl')
        self.assertEqual(v2.name, 'Mountain fox cushion kjhz2n31_test-nl')

        self.assertEqual(v1.code, '9100500-22100500')
        self.assertEqual(v2.code, '9100500-23100500')

        self.assertEqual(v1.external_reference, 'demo_15_jqhxz3_test_main_22')
        self.assertEqual(v2.external_reference, 'demo_15_jqhxz3_test_main_23')

        self.assertEqual(v1.external_barcode, '432432432433')
        self.assertEqual(v2.external_barcode, '432432432434')

        self.assertFalse(errors)

        # 2. Test external-template fields IN
        data = t.calculate_import_fields_data()

        self.assertEqual(data['name']['language'][self.nl_id], 'Mountain fox cushion kjhz2n31_test-nl')
        self.assertEqual(data['name']['language'][self.pl_id], 'Mountain fox cushion kjhz2n31_test-pl')
        self.assertEqual(data['website_product_name']['language'][self.nl_id], 'Mountain fox cushion kjhz2n31_test-nl')
        self.assertEqual(data['website_product_name']['language'][self.pl_id], 'Mountain fox cushion kjhz2n31_test-pl')
        self.assertEqual(data['website_description']['language'][self.nl_id], '<p>The mountain fox cushion will add a graphic and colorful touch to your sofa, armchair or bed. Create a modern and zen atmosphere that inspires relaxation. Cover 100% cotton, machine washable at 60° / Filling 100% hypoallergenic polyester NL.</p>')  # noqa
        self.assertEqual(data['website_description']['language'][self.pl_id], '<p>The mountain fox cushion will add a graphic and colorful touch to your sofa, armchair or bed. Create a modern and zen atmosphere that inspires relaxation. Cover 100% cotton, machine washable at 60° / Filling 100% hypoallergenic polyester PL.</p>')  # noqa
        self.assertEqual(data['website_short_description']['language'][self.nl_id], '<p>Cushion with removable cover and invisible zip on the back. 32x32cm NL.</p>')  # noqa
        self.assertEqual(data['website_short_description']['language'][self.pl_id], '<p>Cushion with removable cover and invisible zip on the back. 32x32cm PL.</p>')  # noqa
        self.assertEqual(data['website_seo_metatitle']['language'][self.nl_id], False)
        self.assertEqual(data['website_seo_metatitle']['language'][self.pl_id], False)
        self.assertEqual(data['website_seo_description']['language'][self.nl_id], False)
        self.assertEqual(data['website_seo_description']['language'][self.pl_id], False)

        self.assertEqual(data['default_code'], 'demo_15_jqhxz3_test_main')
        self.assertEqual(data['barcode'], '432432432432')
        self.assertEqual(round(data['weight'], 1), 0.3)
        self.assertEqual(round(data['list_price'], 1), 18.9)
        self.assertEqual(data['sale_ok'], True)
        self.assertEqual(data['active'], True)
        self.assertEqual(data['is_storable'], True)
        self.assertEqual(
            data['integration_default_category_id'],
            self.env.ref('integration_prestashop.integration_prestashop_product_public_category_2').id,
        )
        self.assertEqual(
            set(data['integration_category_ids'][0][2]),
            set(self.integration_category_ids),
        )
        self.assertEqual(data['optional_product_ids'][0][2], [])
        self.assertEqual(data['taxes_id'][0][2][0], self.tax_100_id)
        self.assertEqual(data['feature_line_ids'][0], (5, 0))
        self.assertEqual(len(data['feature_line_ids']), 3)

        # 2.1 Test external-variant 1 fields IN
        data1 = v1.calculate_import_fields_data()

        self.assertEqual(round(data1['variant_extra_price'], 1), 0.0)
        self.assertEqual(round(data1['weight'], 1), 0.3)
        self.assertEqual(data1['default_code'], 'demo_15_jqhxz3_test_main_22')
        self.assertEqual(data1['barcode'], '432432432433')
        self.assertEqual(round(data1['standard_price'], 1), 0.0)

        # 2.2 Test external-variant 2 fields IN
        data2 = v2.calculate_import_fields_data()

        self.assertEqual(round(data2['variant_extra_price'], 1), 0.0)
        self.assertEqual(round(data2['weight'], 1), 0.3)
        self.assertEqual(data2['default_code'], 'demo_15_jqhxz3_test_main_23')
        self.assertEqual(data2['barcode'], '432432432434')
        self.assertEqual(round(data2['standard_price'], 1), 0.0)

        # 3. Run import product
        template = t.import_one_product(import_images=False)

        self.assertEqual(template.name, 'Mountain fox cushion kjhz2n31_test-nl')
        self.assertEqual(
            template.with_context(lang='pl_PL').name,
            'Mountain fox cushion kjhz2n31_test-pl',
        )
        self.assertEqual(template.product_variant_count, 2)
        self.assertEqual(template.active, True)
        self.assertEqual(template.sale_ok, True)

        variant1, variant2 = template.product_variant_ids

        self.assertEqual(variant1.name, 'Mountain fox cushion kjhz2n31_test-nl')
        self.assertEqual(variant1.default_code, 'demo_15_jqhxz3_test_main_22')
        self.assertEqual(variant1.barcode, '432432432433')
        self.assertEqual(round(variant1.variant_extra_price, 1), 0.0)
        self.assertEqual(round(variant1.weight, 1), 0.3)
        self.assertEqual(round(variant1.standard_price, 1), 0.0)
        self.assertTrue(self.tax_100_id in variant1.taxes_id.ids)
        self.assertTrue(self.integration.id in variant1.integration_ids.ids)
        self.assertEqual(len(variant1.integration_mapping_ids), 1)

        self.assertEqual(variant2.name, 'Mountain fox cushion kjhz2n31_test-nl')
        self.assertEqual(variant2.default_code, 'demo_15_jqhxz3_test_main_23')
        self.assertEqual(variant2.barcode, '432432432434')
        self.assertEqual(round(variant2.variant_extra_price, 1), 0.0)
        self.assertEqual(round(variant2.weight, 1), 0.3)
        self.assertEqual(round(variant2.standard_price, 1), 0.0)
        self.assertTrue(self.tax_100_id in variant2.taxes_id.ids)
        self.assertTrue(self.integration.id in variant2.integration_ids.ids)
        self.assertEqual(len(variant2.integration_mapping_ids), 1)

        # 4. Test export-format
        template.with_context(skip_product_export=True).combination_default_id = variant1.id

        data = template.to_export_format(self.integration)

        # 4.1 Template
        self.assertEqual(data['id'], template.id)
        self.assertEqual(data['odoo_external_id'], t.id)
        self.assertEqual(data['external_id'], t.code)
        self.assertEqual(data['type'], 'consu')
        self.assertEqual(data['kits'], [])
        self.assertEqual(data['variants_count'], 2)

        fields = data['fields']

        self.assertEqual(fields['name']['language'][self.nl_ext_id], 'Mountain fox cushion kjhz2n31_test-nl')
        self.assertEqual(fields['name']['language'][self.pl_ext_id], 'Mountain fox cushion kjhz2n31_test-pl')
        self.assertEqual(fields['description']['language'][self.nl_ext_id], '<p>The mountain fox cushion will add a graphic and colorful touch to your sofa, armchair or bed. Create a modern and zen atmosphere that inspires relaxation. Cover 100% cotton, machine washable at 60\u00b0 / Filling 100% hypoallergenic polyester NL.</p>')  # noqa
        self.assertEqual(fields['description']['language'][self.pl_ext_id], '<p>The mountain fox cushion will add a graphic and colorful touch to your sofa, armchair or bed. Create a modern and zen atmosphere that inspires relaxation. Cover 100% cotton, machine washable at 60\u00b0 / Filling 100% hypoallergenic polyester PL.</p>')  # noqa
        self.assertEqual(fields['description_short']['language'][self.nl_ext_id], '<p>Cushion with removable cover and invisible zip on the back. 32x32cm NL.</p>')  # noqa
        self.assertEqual(fields['description_short']['language'][self.pl_ext_id], '<p>Cushion with removable cover and invisible zip on the back. 32x32cm PL.</p>')  # noqa
        self.assertEqual(fields['meta_title']['language'][self.nl_ext_id], '')
        self.assertEqual(fields['meta_title']['language'][self.pl_ext_id], '')
        self.assertEqual(fields['meta_description']['language'][self.nl_ext_id], '')
        self.assertEqual(fields['meta_description']['language'][self.pl_ext_id], '')

        self.assertEqual(fields['active'], '1')
        self.assertEqual(fields['price'], '18.9')
        self.assertEqual(fields['show_price'], '1')
        self.assertEqual(fields['available_for_order'], '1')
        self.assertEqual(fields['id_category_default'], '8')
        self.assertEqual(set(fields['categories']), {'2', '8', '6'})
        self.assertEqual(fields['id_tax_rules_group'], '10')
        self.assertEqual(fields['additional_delivery_times'], '0')
        self.assertEqual(fields['delivery_in_stock'], {'language': {'1': '', '2': ''}})
        self.assertEqual(fields['delivery_out_stock'], {'language': {'1': '', '2': ''}})

        self.assertEqual(fields['product_features'][0]['id'], '1')
        self.assertEqual(fields['product_features'][0]['id_feature_value'], '1')
        self.assertEqual(fields['product_features'][1]['id'], '2')
        self.assertEqual(fields['product_features'][1]['id_feature_value'], '9')
        self.assertEqual(fields['accessories'], [])
        self.assertEqual(fields['reference'], '')
        self.assertEqual(fields['ean13'], '')

        self.assertEqual(len(data['products']), 2)

        # 4.2 Variant 1
        data1 = data['products'][0]

        self.assertEqual(data1['id'], variant1.id)
        self.assertEqual(data1['odoo_external_id'], v1.id)
        self.assertEqual(data1['external_id'], '9100500-22100500')
        self.assertEqual(len(data1['attribute_values']), 1)
        self.assertEqual(data1['attribute_values'][0]['name']['language'][self.nl_ext_id], 'Whiteee')
        self.assertEqual(data1['attribute_values'][0]['name']['language'][self.pl_ext_id], 'Biały')
        self.assertEqual(data1['attribute_values'][0]['attribute'], '2')
        self.assertEqual(data1['attribute_values'][0]['external_id'], '8')
        self.assertEqual(data1['reference'], 'demo_15_jqhxz3_test_main_22')
        self.assertEqual(data1['reference_api_field'], 'reference')
        self.assertEqual(data1['is_default'], True)
        self.assertEqual(data1['fields']['price'], '0')
        self.assertEqual(data1['fields']['weight'], '0.3')
        self.assertEqual(data1['fields']['reference'], 'demo_15_jqhxz3_test_main_22')
        self.assertEqual(data1['fields']['ean13'], '432432432433')
        self.assertEqual(data1['fields']['wholesale_price'], '0.0')

        # 4.3 Variant 2
        data2 = data['products'][1]

        self.assertEqual(data2['id'], variant2.id)
        self.assertEqual(data2['odoo_external_id'], v2.id)
        self.assertEqual(data2['external_id'], '9100500-23100500')
        self.assertEqual(len(data2['attribute_values']), 1)
        self.assertEqual(data2['attribute_values'][0]['name']['language'][self.nl_ext_id], 'Blackkko')
        self.assertEqual(data2['attribute_values'][0]['name']['language'][self.pl_ext_id], 'czarny')
        self.assertEqual(data2['attribute_values'][0]['attribute'], '2')
        self.assertEqual(data2['attribute_values'][0]['external_id'], '11')
        self.assertEqual(data2['reference'], 'demo_15_jqhxz3_test_main_23')
        self.assertEqual(data2['reference_api_field'], 'reference')
        self.assertEqual(data2['is_default'], False)
        self.assertEqual(data2['fields']['price'], '0')
        self.assertEqual(data2['fields']['weight'], '0.3')
        self.assertEqual(data2['fields']['reference'], 'demo_15_jqhxz3_test_main_23')
        self.assertEqual(data2['fields']['ean13'], '432432432434')
        self.assertEqual(data2['fields']['wholesale_price'], '0.0')

    def test_get_product_accounts(self):
        # Product 1
        res = self.product1.product_tmpl_id.with_company(self.company).get_product_accounts()
        self.assertEqual(
            res['income'].id,
            self.env.ref('integration_prestashop.integration_prestashop_account_a_income').id,
        )
        self.assertEqual(
            res['expense'].id,
            self.env.ref('integration_prestashop.integration_prestashop_account_a_expense').id,
        )

        # Product 2
        res = self.product2.product_tmpl_id.with_company(self.company).get_product_accounts()
        self.assertEqual(
            res['income'].id,
            self.env.ref('integration_prestashop.integration_prestashop_account_a_income').id,
        )
        self.assertEqual(
            res['expense'].id,
            self.env.ref('integration_prestashop.integration_prestashop_account_a_expense').id,
        )

    def test_integration_settings_patch(self):
        self.assertTrue(isinstance(self.adapter, Adapter))
        self.assertTrue(isinstance(self.adapter._Adapter__cache_core, PrestashopAPIClientPatchTest))
        self.assertTrue(isinstance(self.adapter._client, PrestashopClientPatchTest))

        self.assertEqual(self.adapter._integration_id, self.integration.id)
        self.assertEqual(self.adapter._integration_name, self.integration.name)

    def test_fetch_order(self):
        received_data = self.integration.adapter.receive_order(ORDER_ID)
        data = received_data['data']

        self.assertEqual(received_data['id'], ORDER_ID)

        self.assertEqual(data['order']['id'], ORDER_ID)
        self.assertEqual(data['order']['reference'], 'QIUZKILRV')
        self.assertEqual(data['order']['id_customer'], '3')
        self.assertEqual(data['order']['id_carrier'], '10')
        self.assertEqual(data['order']['id_address_delivery'], '6')
        self.assertEqual(data['order']['id_address_invoice'], '6')
        self.assertEqual(data['order']['id_currency'], '1')
        self.assertEqual(data['order']['id_cart'], '15')
        self.assertEqual(data['order']['current_state'], '3')
        self.assertEqual(data['order']['invoice_number'], '7')
        self.assertEqual(data['order']['delivery_number'], '6')
        self.assertEqual(data['order']['payment'], 'Bank transfer')
        self.assertEqual(data['order']['total_discounts_tax_incl'], '66.550000')
        self.assertEqual(data['order']['total_discounts_tax_excl'], '55.000000')
        self.assertEqual(data['order']['total_paid'], '1435.060000')
        self.assertEqual(data['order']['total_paid_tax_incl'], '1435.060000')
        self.assertEqual(data['order']['total_paid_tax_excl'], '1186.000000')
        self.assertEqual(data['order']['total_shipping'], '8.470000')
        self.assertEqual(data['order']['total_shipping_tax_incl'], '8.470000')
        self.assertEqual(data['order']['total_shipping_tax_excl'], '7.000000')
        self.assertEqual(data['order']['carrier_tax_rate'], '21.000')

        self.assertEqual(data['customer']['id'], '3')
        self.assertEqual(data['customer']['id_lang'], '1')
        self.assertEqual(data['customer']['email'], 'test_prestashop_nl@prestashop.com')
        self.assertEqual(data['customer']['lastname'], 'Customer')
        self.assertEqual(data['customer']['firstname'], 'TestPresta')

        self.assertEqual(data['invoice_address']['id'], '6')
        self.assertEqual(data['invoice_address']['id_customer'], '3')
        self.assertEqual(data['invoice_address']['id_country'], '13')
        self.assertEqual(data['invoice_address']['alias'], 'NL Address')
        self.assertEqual(data['invoice_address']['lastname'], 'Customer')
        self.assertEqual(data['invoice_address']['firstname'], 'TestPresta')
        self.assertEqual(data['invoice_address']['address1'], 'Buitenruststraat 117')
        self.assertEqual(data['invoice_address']['address2'], '')
        self.assertEqual(data['invoice_address']['phone'], '1000034563')
        self.assertEqual(data['invoice_address']['phone_mobile'], '1100034563')
        self.assertEqual(data['invoice_address']['postcode'], '4337 EL')
        self.assertEqual(data['invoice_address']['city'], 'Middelburg')

        self.assertEqual(data['delivery_address']['id'], '6')
        self.assertEqual(data['delivery_address']['id_customer'], '3')
        self.assertEqual(data['delivery_address']['id_country'], '13')
        self.assertEqual(data['delivery_address']['alias'], 'NL Address')
        self.assertEqual(data['delivery_address']['lastname'], 'Customer')
        self.assertEqual(data['delivery_address']['firstname'], 'TestPresta')
        self.assertEqual(data['delivery_address']['address1'], 'Buitenruststraat 117')
        self.assertEqual(data['delivery_address']['address2'], '')
        self.assertEqual(data['delivery_address']['phone'], '1000034563')
        self.assertEqual(data['delivery_address']['phone_mobile'], '1100034563')
        self.assertEqual(data['delivery_address']['postcode'], '4337 EL')
        self.assertEqual(data['delivery_address']['city'], 'Middelburg')

        self.assertEqual(data['payment_transactions'], [])

    def test_create_order_from_input(self):
        # `_run_and_call_next` (used by `_run_step_sync()` now) would otherwise cascade through
        # the whole remaining pipeline on success under `queue_job__no_delay` - this
        # test drives each step manually, one at a time.
        self.patch(type(self.env['integration.workflow.pipeline.line']), 'call_next_step_job', lambda self: None)

        # 1. Create input file
        self.integration.test_method_parameter = ORDER_ID
        input_file = self.integration.integrationApiReceiveOrder()

        self.assertEqual(input_file.si_id.id, self.integration.id)
        self.assertEqual(input_file.name, ORDER_ID)
        self.assertFalse(input_file.order_id)
        self.assertTrue(input_file.update_required)

        # 2. Create order from input file
        input_file.update_required = False
        input_file = self._set_permissions(input_file)

        parsed_data = input_file.parse()
        self.assertEqual(parsed_data['id'], ORDER_ID)

        with self.assertRaises(ApiImportError) as ex:
            input_file.process_no_job()

        self.assertIn('Discount Product is not configured', str(ex.exception))

        self.integration.discount_product_id = self.env.ref(
            'integration_prestashop.prestashop_product_product_discount').id

        order = input_file.process_no_job()

        # 2.1 Check order
        self.assertEqual(order.name, 'QIUZKILRV')
        self.assertEqual(len(order.order_line), 4)
        self.assertEqual(order.company_id, self.company)
        self.assertEqual(order.currency_id, self.env.ref('base.EUR'))

        self.assertEqual(order.partner_id.type, 'contact')
        self.assertEqual(order.partner_id.company_type, 'person')
        self.assertEqual(order.partner_id.name, 'TestPresta Customer')
        self.assertEqual(order.partner_id.city, 'Middelburg')
        # self.assertEqual(order.partner_id.phone, '1000034563')
        # self.assertEqual(order.partner_id.mobile, '1100034563')
        self.assertEqual(order.partner_id.email, 'test_prestashop_nl@prestashop.com')
        self.assertEqual(order.partner_id.country_id, self.env.ref('base.nl'))
        self.assertEqual(order.partner_id.zip, '4337 EL')
        self.assertEqual(order.partner_id.street, 'Buitenruststraat 117')
        self.assertFalse(order.partner_id.company_name)
        self.assertFalse(order.partner_id.is_company)
        self.assertEqual(order.partner_id.lang, self.env.ref('base.lang_nl').code)
        self.assertEqual(order.partner_id.category_id.name, self.integration.name)

        self.assertEqual(order.pricelist_id.company_id, self.company)
        self.assertEqual(order.pricelist_id.currency_id, self.env.ref('base.EUR'))

        self.assertEqual(round(order.amount_untaxed, 1), 1186.0)
        self.assertEqual(round(order.amount_tax, 2), 249.06)
        self.assertEqual(round(order.amount_total, 2), 1435.06)

        # Line 1
        line = order.order_line[0]
        self.assertEqual(line.product_id.default_code, 'gtp3-ref-1-prestashop-test')
        self.assertEqual(round(line.product_qty, 1), 2.0)
        self.assertEqual(round(line.qty_to_deliver, 1), 2.0)

        self.assertFalse(line.is_delivery)
        # self.assertEqual(round(line.price_unit, 2), 158.51)  131.0 --> tax price_include doesn't work
        self.assertEqual(round(line.price_subtotal, 1), 262.0)
        self.assertEqual(round(line.price_tax, 2), 55.02)
        self.assertEqual(round(line.price_total, 2), 317.02)

        # Line 2
        line = order.order_line[1]
        self.assertEqual(line.product_id.default_code, 'guit1-sku-bl-prestashop-test')
        self.assertEqual(round(line.product_qty, 1), 3.0)
        self.assertEqual(round(line.qty_to_deliver, 1), 3.0)

        self.assertFalse(line.is_delivery)
        # self.assertEqual(round(line.price_unit, 2), 392.04)  324 --> tax price_include doesn't work
        self.assertEqual(round(line.price_subtotal, 1), 972.0)
        self.assertEqual(round(line.price_tax, 2), 204.12)
        self.assertEqual(round(line.price_total, 2), 1176.12)

        # Line 3
        line = order.order_line[2]
        self.assertEqual(line.product_id.default_code, 'discount-product-prestashop-test')
        self.assertEqual(round(line.product_qty, 1), 1.0)
        self.assertEqual(round(line.qty_to_deliver, 1), 1.0)

        self.assertFalse(line.is_delivery)
        # self.assertEqual(round(line.price_unit, 2), -66.55)  -55.0 --> tax price_include doesn't work
        self.assertEqual(round(line.price_subtotal, 1), -55.0)
        self.assertEqual(round(line.price_tax, 2), -11.55)
        self.assertEqual(round(line.price_total, 2), -66.55)

        # Line 4
        line = order.order_line[3]
        self.assertEqual(line.product_id.default_code, '10')
        self.assertEqual(round(line.product_qty, 1), 1.0)
        self.assertEqual(round(line.qty_to_deliver, 1), 1.0)

        self.assertTrue(line.is_delivery)
        # self.assertEqual(round(line.price_unit, 2), 8.47)  7.0 --> tax price_include doesn't work
        self.assertEqual(round(line.price_subtotal, 1), 7.0)
        self.assertEqual(round(line.price_tax, 2), 1.47)
        self.assertEqual(round(line.price_total, 2), 8.47)

        # 2.2 Integration fields
        self.assertEqual(order.integration_id, self.integration)

        self.assertEqual(order.sub_status_id.name, 'Processing in progress')

        self.assertEqual(order.payment_method_id.integration_id, self.integration)
        self.assertEqual(order.payment_method_id.name, 'Bank transfer')
        self.assertEqual(order.external_sales_order_ref, 'QIUZKILRV')

        self.assertFalse(order.external_fulfillment_ids)
        self.assertFalse(order.external_payment_ids)

        # 2.3 Check pipeline
        pipeline = order.integration_pipeline
        pipeline.ensure_one()
        self.assertTrue(all(pipeline.pipeline_task_ids.mapped(lambda x: x.state == 'skip')))
        self.assertEqual(pipeline.sub_state_external_ids.code, '3')
        self.assertFalse(pipeline.skip_dispatch)
        self.assertFalse(pipeline.invoice_journal_id)
        self.assertFalse(pipeline.payment_journal_id)
        self.assertFalse(pipeline.current_info)
        self.assertEqual(pipeline.input_file_id, input_file)

        # 3. Run pipeline
        pipeline.pipeline_task_ids.write({'state': 'todo'})
        # Advance payment is not part of this scenario; this status registers against the invoice.
        pipeline.pipeline_task_ids.filtered(
            lambda x: x.current_step_method == 'apply_advance_payment'
        ).write({'state': 'skip'})

        # 3.1 validate_order
        task1 = pipeline.pipeline_task_ids.filtered(lambda x: x.current_step_method == 'validate_order')

        self.assertEqual(order.state, 'draft')
        self.assertEqual(len(order.picking_ids), 0)

        task1._run_step_sync()

        self.assertEqual(task1.state, 'done')

        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.delivery_status, 'pending')
        self.assertEqual(order.invoice_status, 'to invoice')
        self.assertEqual(len(order.picking_ids), 1)

        # 3.2 validate_picking
        task2 = pipeline.pipeline_task_ids.filtered(lambda x: x.current_step_method == 'validate_picking')

        self.env['stock.quant'].create({
            'product_id': self.env.ref('integration_prestashop.prestashop_product_product_49620724449001').id,
            'location_id': self.wh.lot_stock_id.id,
            'quantity': 100,
        })
        self.env['stock.quant'].create({
            'product_id': self.env.ref('integration_prestashop.prestashop_product_product_47738503495001').id,
            'location_id': self.wh.lot_stock_id.id,
            'quantity': 100,
        })

        picking = order.picking_ids
        self.assertEqual(picking.state, 'assigned')
        self.assertEqual(picking.carrier_id.name, 'My carrier Prestashop Test')

        task2._run_step_sync()

        self.assertEqual(task2.state, 'done')
        self.assertEqual(picking.state, 'done')
        self.assertFalse(pipeline.current_info)

        # 3.3 create_invoice
        task3 = pipeline.pipeline_task_ids.filtered(lambda x: x.current_step_method == 'create_invoice')
        self.assertEqual(task3.state, 'todo')

        # Not self.assertRaises(): Odoo's version wraps the block in a savepoint and
        # rolls it back when the expected exception fires (see
        # `TransactionCase._assertRaises`), which would silently undo the
        # state='failed'/current_info writes we're about to check below.
        try:
            task3._run_step_sync()
            self.fail('create_invoice should have raised UserError')
        except UserError:
            pass

        self.assertEqual(task3.state, 'failed')
        self.assertIn('No Invoice Journal defined', pipeline.current_info)

        pipeline.sub_state_external_ids.invoice_journal_id = self.invoice_journal.id
        # invoice_journal_id is a non-stored compute; refresh it after the failed run
        # left it cached empty (a real request would read it fresh).
        pipeline.invalidate_recordset(['invoice_journal_id'])

        self.assertEqual(pipeline.invoice_journal_id, self.invoice_journal)

        # Define partner's accounts
        partner = order.partner_id.with_company(self.company)
        partner.property_account_receivable_id = self.env.ref(
            'integration_prestashop.integration_prestashop_account_a_recv').id
        partner.property_account_payable_id = self.env.ref(
            'integration_prestashop.integration_prestashop_account_a_pay').id

        task3._run_step_sync()

        self.assertEqual(task3.state, 'done')

        self.assertEqual(order.invoice_status, 'invoiced')

        invoice = order.actual_invoice_ids
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.invoice_origin, order.name)
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.country_code, 'NL')
        self.assertEqual(invoice.currency_id, self.env.ref('base.EUR'))
        self.assertEqual(invoice.payment_state, 'not_paid')
        self.assertEqual(invoice.integration_id, self.integration)
        self.assertEqual(round(invoice.amount_untaxed, 1), 1186.0)
        self.assertEqual(round(invoice.amount_tax, 2), 249.06)
        self.assertEqual(round(invoice.amount_total, 2), 1435.06)
        self.assertEqual(round(invoice.amount_residual, 2), 1435.06)

        # 3.4 validate_invoice
        task4 = pipeline.pipeline_task_ids.filtered(lambda x: x.current_step_method == 'validate_invoice')

        self.assertEqual(task4.state, 'todo')

        task4._run_step_sync()

        self.assertEqual(task4.state, 'done')
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(round(invoice.amount_residual, 2), 1435.06)

        # 3.5 send invoice
        task5 = pipeline.pipeline_task_ids.filtered(lambda x: x.current_step_method == 'send_invoice')
        self.assertEqual(task5.state, 'todo')

        # Patch wizard action to avoid actually sending email
        def _mock_action_send_and_print(self):
            invoice.write({'is_move_sent': True})
            return {'type': 'ir.actions.act_window_close'}  # Simulate success

        self.patch(
            type(self.env['account.move.send.wizard']),
            'action_send_and_print',
            _mock_action_send_and_print,
        )

        self.assertFalse(invoice.is_move_sent)

        task5._run_step_sync()

        self.assertEqual(task5.state, 'done')
        self.assertTrue(invoice.is_move_sent)

        # # 3.6 register_payment
        task6 = pipeline.pipeline_task_ids.filtered(lambda x: x.current_step_method == 'register_payment')
        self.assertEqual(task6.state, 'todo')

        try:
            task6._run_step_sync()
            self.fail('register_payment should have raised UserError')
        except UserError:
            pass

        self.assertEqual(task6.state, 'failed')
        self.assertIn(
            f'No Payment Journal defined for Payment Method "{order.payment_method_id.name}"', pipeline.current_info
        )

        journal = self.env.ref('integration_prestashop.integration_prestashop_account_cash_journal')

        pipeline.payment_method_external_id.payment_journal_id = journal.id

        def _get_available_payment_method_lines_patch(self, payment_type):
            if not self:
                return self.env['account.payment.method.line']

            self.ensure_one()
            if payment_type == 'inbound':
                return self.env.ref('integration_prestashop.integration_prestashop_line_check_in')

            return journal.outbound_payment_method_line_ids

        self.patch(type(journal), '_get_available_payment_method_lines', _get_available_payment_method_lines_patch)

        task6._run_step_sync()

        self.assertEqual(task6.state, 'done')

        self.assertEqual(round(invoice.amount_residual, 1), 0.0)
        self.assertEqual(invoice.payment_state, 'paid')

        payment = self.env['account.payment'].search([('invoice_ids', 'in', invoice.id)])
        payment.ensure_one()
        self.assertTrue(payment.state in ('paid', 'in_process'))
        self.assertEqual(round(payment.amount, 2), 1435.06)
