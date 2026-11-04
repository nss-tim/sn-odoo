# See LICENSE file for full copyright and licensing details.

from copy import deepcopy
from unittest.mock import patch

from odoo.tests import tagged

from .patch.storage import STORAGE
from .test_integration_prestashop import TestIntegrationPrestashopCommon


SOURCE_PRODUCT_ID = '9100500'
VIRTUAL_PRODUCT_ID = '9100501'
PHYSICAL_PRODUCT_ID = '9100502'


@tagged('post_install', '-at_install', 'test_prestashop_product_type_import')
class TestPrestashopProductTypeImport(TestIntegrationPrestashopCommon):
    """New PrestaShop products get their Odoo type from the shop product type, existing ones keep it."""

    @classmethod
    def _build_product(cls, product_id, product_type):
        """Clone the stub product as a combination-less one of the given PrestaShop type."""
        product = deepcopy(STORAGE['product'][SOURCE_PRODUCT_ID])
        product['id'] = product_id
        product['type']['value'] = product_type
        product['id_default_combination']['value'] = '0'
        product['associations']['combinations'] = {}
        product['associations']['product_option_values'] = {}

        return product

    def setUp(self):
        super().setUp()

        # The stub storage is a module level dict, so patch it for the test duration only
        for name, product_type in ((VIRTUAL_PRODUCT_ID, 'virtual'), (PHYSICAL_PRODUCT_ID, 'simple')):
            for storage, values in (
                (STORAGE['product'], {name: self._build_product(name, product_type)}),
                (STORAGE['combination'], {name: []}),
                (STORAGE['stock_available'], {name: deepcopy(STORAGE['stock_available'][SOURCE_PRODUCT_ID])}),
            ):
                patcher = patch.dict(storage, values)
                patcher.start()
                self.addCleanup(patcher.stop)

    def _import_product(self, product_id):
        external_template, __, errors, ___ = self.integration._import_external_product(
            [product_id],
            try_to_map=False,
            raise_error=False,
        )
        self.assertFalse(errors)

        return external_template, external_template.import_one_product(import_images=False)

    def test_virtual_product_is_imported_as_service(self):
        __, template = self._import_product(VIRTUAL_PRODUCT_ID)

        self.assertEqual(template.type, 'service', 'A virtual PrestaShop product must become a service')
        self.assertFalse(template.is_storable, 'A service must not be storable')

    def test_physical_product_is_imported_as_storable(self):
        __, template = self._import_product(PHYSICAL_PRODUCT_ID)

        self.assertEqual(template.type, 'consu', 'A physical PrestaShop product must stay storable')
        self.assertTrue(template.is_storable, 'A physical product must be storable')

    def test_reimport_does_not_change_product_type(self):
        external_template, template = self._import_product(PHYSICAL_PRODUCT_ID)
        self.assertTrue(template.is_storable)

        # The product becomes virtual in the shop afterwards
        STORAGE['product'][PHYSICAL_PRODUCT_ID]['type']['value'] = 'virtual'
        updated = external_template.import_one_product(import_images=False)

        self.assertEqual(updated, template)
        self.assertTrue(updated.is_storable, 'Re-import must not change the type of an existing product')

    def test_order_with_virtual_product_has_no_picking(self):
        __, template = self._import_product(VIRTUAL_PRODUCT_ID)

        order = self.env['sale.order'].with_company(self.company).create({
            'partner_id': self.env['res.partner'].create({'name': 'Virtual Buyer'}).id,
            'company_id': self.company.id,
            'order_line': [(0, 0, {
                'product_id': template.product_variant_id.id,
                'product_uom_qty': 1,
            })],
        })
        order.action_confirm()

        self.assertEqual(order.state, 'sale')
        self.assertFalse(order.picking_ids, 'A service product must not create a delivery')
