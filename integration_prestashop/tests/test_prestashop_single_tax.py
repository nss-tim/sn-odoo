# See LICENSE file for full copyright and licensing details.

from copy import deepcopy
from unittest.mock import patch

from odoo.tests import tagged, TransactionCase

from .patch.prestashop_api_patch import PrestashopAPIClientPatchTest
from .test_integration_prestashop import TestIntegrationPrestashopCommon
from ..prestashop_api import PrestaShopApiClient


def _make_shop(size):
    """Tax tables of a PrestaShop shop with `size` taxes. Ids 1-4 are the ones the tests look at."""
    taxes = [
        {'id': '1', 'name': 'PL VAT 23%', 'rate': '23.000', 'deleted': '0'},
        {'id': '2', 'name': 'PL VAT 8%', 'rate': '8.000', 'deleted': '0'},
        {'id': '3', 'name': 'No rules', 'rate': '5.000', 'deleted': '0'},
        {'id': '4', 'name': 'Deleted VAT', 'rate': '10.000', 'deleted': '1'},
    ]
    rules = [
        {'id': '1', 'id_tax': '1', 'id_tax_rules_group': '10'},
        {'id': '2', 'id_tax': '1', 'id_tax_rules_group': '11'},
        {'id': '3', 'id_tax': '1', 'id_tax_rules_group': '10'},
        {'id': '4', 'id_tax': '2', 'id_tax_rules_group': '12'},
        {'id': '5', 'id_tax': '2', 'id_tax_rules_group': '13'},
    ]
    groups = [
        {'id': '10', 'name': 'PL Standard Rate (23%)', 'deleted': '0'},
        {'id': '11', 'name': 'PL Services', 'deleted': '0'},
        {'id': '12', 'name': 'PL Reduced Rate (8%)', 'deleted': '0'},
        {'id': '13', 'name': 'Removed group', 'deleted': '1'},
    ]
    for tax_id in range(5, size + 1):
        taxes.append({'id': str(tax_id), 'name': f'US Tax {tax_id}', 'rate': '8.250', 'deleted': '0'})
        rules.append({'id': str(100 + tax_id), 'id_tax': str(tax_id), 'id_tax_rules_group': '10'})

    return {'tax': taxes, 'tax_rule': rules, 'tax_rule_group': groups}


class FakeModel:

    def __init__(self, shop, name):
        self.shop = shop
        self.name = name

    def search_read(self, filters=None, fields=None, **kw):
        filters = filters or {}
        self.shop.requests.append((self.name, deepcopy(filters)))

        rows = self.shop.tables[self.name]
        for key, value in filters.items():
            rows = [x for x in rows if self._matches(x[key], value)]

        return [{key: row[key] for key in fields} if fields else dict(row) for row in rows]

    @staticmethod
    def _matches(row_value, filter_value):
        if filter_value.startswith('['):
            return row_value in filter_value[1:-1].split('|')

        return row_value == filter_value


class FakeShop:
    """Webservice of a PrestaShop shop: serves the tax tables and records every request."""

    def __init__(self, tables):
        self.tables = tables
        self.requests = []

    def model(self, name):
        return FakeModel(self, name)


def _make_adapter(shop):
    # Same shortcut as the stub adapter: only what the tax methods use, no settings
    adapter = PrestaShopApiClient.__new__(PrestaShopApiClient)
    adapter._integration_id = None
    adapter._integration_name = 'PrestaShop Single Tax Test'
    adapter._client = shop
    return adapter


def _sorted_groups(tax):
    return {**tax, 'tax_groups': sorted(tax['tax_groups'], key=lambda x: x['id'])}


@tagged('post_install', '-at_install', 'test_prestashop_single_tax')
class TestPrestashopSingleTaxApi(TransactionCase):

    def test_single_tax_matches_the_item_of_the_full_list(self):
        adapter = _make_adapter(FakeShop(_make_shop(10)))
        full_list = {x['id']: _sorted_groups(x) for x in adapter.get_taxes()}

        for tax_id in ('1', '2', '3', '7'):
            with self.subTest(tax_id=tax_id):
                self.assertEqual(_sorted_groups(adapter.get_single_tax(tax_id)), full_list[tax_id])

    def test_single_tax_carries_its_tax_rule_groups_once_and_skips_deleted_ones(self):
        adapter = _make_adapter(FakeShop(_make_shop(10)))

        groups = sorted(adapter.get_single_tax('1')['tax_groups'], key=lambda x: x['id'])

        self.assertEqual(groups, [
            {'id': '10', 'name': 'PL Standard Rate (23%)'},
            {'id': '11', 'name': 'PL Services'},
        ])
        self.assertEqual(
            adapter.get_single_tax('2')['tax_groups'],
            [{'id': '12', 'name': 'PL Reduced Rate (8%)'}],
        )
        self.assertEqual(adapter.get_single_tax('3')['tax_groups'], [])

    def test_single_tax_requests_do_not_depend_on_the_size_of_the_tax_table(self):
        small_shop = FakeShop(_make_shop(10))
        large_shop = FakeShop(_make_shop(1000))

        _make_adapter(small_shop).get_single_tax('7')
        _make_adapter(large_shop).get_single_tax('7')

        self.assertEqual(
            [name for name, filters in small_shop.requests],
            [name for name, filters in large_shop.requests],
        )
        for name, filters in large_shop.requests:
            self.assertTrue(
                filters.get('id') or filters.get('id_tax'),
                'Request to "%s" is not limited to the requested tax: %s' % (name, filters),
            )
        self.assertLessEqual(len(large_shop.requests), 3)

    def test_single_tax_that_does_not_exist_or_is_deleted_gives_empty_dict(self):
        adapter = _make_adapter(FakeShop(_make_shop(10)))

        self.assertEqual(adapter.get_single_tax('999'), {})
        self.assertEqual(adapter.get_single_tax('4'), {})


@tagged('post_install', '-at_install', 'test_prestashop_single_tax')
class TestPrestashopAutoCreateTax(TestIntegrationPrestashopCommon):

    def setUp(self):
        super().setUp()
        self.integration.auto_create_taxes_on_so = True

    def _use_shop(self, shop_size):
        shop = FakeShop(_make_shop(shop_size))
        adapter = _make_adapter(shop)

        def get_single_tax(stub_adapter, tax_id):
            return adapter.get_single_tax(tax_id)

        # The stub adapter answers from its canned tax list, so its `get_single_tax()` is replaced with the real one
        patcher = patch.object(PrestashopAPIClientPatchTest, 'get_single_tax', get_single_tax)
        patcher.start()
        self.addCleanup(patcher.stop)

        return shop

    def _import_unknown_tax(self, tax_id, shop_size):
        shop = self._use_shop(shop_size)

        return self.integration._import_external_tax(tax_id), shop

    def test_button_on_a_mapping_line_imports_only_that_tax(self):
        shop = self._use_shop(1000)
        external_tax = self.env['integration.account.tax.external'].create({
            'integration_id': self.integration.id,
            'code': '2',
            'name': 'PL VAT 8%',
        })
        mapping = external_tax.create_or_update_mapping()

        mapping.action_import_taxes_from_mapping()

        self.assertEqual(mapping.tax_id.amount, 8.0)
        self.assertLessEqual(len(shop.requests), 3)
        for name, filters in shop.requests:
            self.assertTrue(
                filters.get('id') or filters.get('id_tax'),
                'Request to "%s" is not limited to the requested tax: %s' % (name, filters),
            )

    def test_unknown_tax_is_created_without_requesting_the_whole_tax_table(self):
        tax, shop = self._import_unknown_tax('2', shop_size=1000)

        self.assertEqual(tax.name, 'PL VAT 8%')
        self.assertEqual(tax.amount, 8.0)
        self.assertEqual(tax.amount_type, 'percent')
        self.assertEqual(tax.price_include_override, 'tax_excluded')
        self.assertLessEqual(len(shop.requests), 3)
        for name, filters in shop.requests:
            self.assertTrue(
                filters.get('id') or filters.get('id_tax'),
                'Request to "%s" is not limited to the requested tax: %s' % (name, filters),
            )

    def test_created_tax_is_linked_to_its_external_tax_group(self):
        tax, shop = self._import_unknown_tax('1', shop_size=10)

        external_tax = self.env['integration.account.tax.external'].search([
            ('integration_id', '=', self.integration.id),
            ('code', '=', '1'),
        ])
        self.assertEqual(external_tax.odoo_record, tax)
        self.assertEqual(sorted(external_tax.external_tax_group_ids.mapped('code')), ['10', '11'])
