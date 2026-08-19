# See LICENSE file for full copyright and licensing details.

from datetime import datetime

from .test_integration_prestashop import TestIntegrationPrestashopCommon


class TestPrestashopReceiveOrdersPagination(TestIntegrationPrestashopCommon):
    """PrestaShop id-keyset pagination: full page -> id of the last order, partial -> None,
    and a page_token continues the import run via a `filter[id] > token` option (immune to
    the set shrinking mid-run) while the date_upd filter stays fixed."""

    def setUp(self):
        super().setUp()
        self.integration.last_receive_orders_datetime = datetime(2026, 6, 22, 5, 0, 0)

    def _order(self, oid, date_upd):
        return {'id': oid, 'date_upd': date_upd, 'date_add': date_upd}

    def _patch_orders_response(self, orders):
        """Return `orders` from the webservice and record the options it was called with."""
        calls = {}
        core = self.adapter._Adapter__cache_core

        def _client_get(client_self, endpoint, **kwargs):
            calls['kwargs'] = kwargs
            return {'orders': {'order': list(orders)} if orders else {}}

        # date-based data building hits the API per order; the token only needs date_upd
        self.patch(type(core), '_get_input_file_data', lambda core_self, order: order)
        self.patch(type(core._client), 'get', _client_get)
        return calls

    def test_full_page_returns_last_id(self):
        limit = self.adapter.order_limit_value()
        orders = [self._order(1000 + i, '2026-06-22 05:10:00') for i in range(limit)]
        self._patch_orders_response(orders)

        result, next_page_token = self.adapter.receive_orders()

        self.assertEqual(len(result), limit)
        self.assertEqual(next_page_token, 1000 + limit - 1)  # id of the last order = keyset

    def test_partial_page_returns_no_token(self):
        self._patch_orders_response([
            self._order(1, '2026-06-22 05:10:00'),
            self._order(2, '2026-06-22 05:20:00'),
        ])

        result, next_page_token = self.adapter.receive_orders()

        self.assertEqual(len(result), 2)
        self.assertIsNone(next_page_token)

    def test_continuation_uses_id_keyset_and_keeps_date_filter(self):
        calls = self._patch_orders_response([])

        self.adapter.receive_orders(page_token=4242)

        options = calls['kwargs']['options']
        # The token becomes a `filter[id] > token` keyset; limit is count-only (no offset), so
        # the continuation cannot be shifted by the set shrinking. Date filter unchanged.
        self.assertEqual(options['filter[id]'], '>[4242]')
        self.assertEqual(options['limit'], self.adapter.order_limit_value())
        self.assertEqual(
            options['filter[date_upd]'],
            '>[%s]' % self.integration.last_receive_orders_datetime_str,
        )
        self.assertEqual(options['sort'], '[id_asc]')

    def test_full_page_of_identical_timestamps_makes_progress(self):
        """Regression for the crowded-timestamp gap: a full page of orders sharing one
        date_upd must still return a next-page token (the last id), so a burst of >= `limit`
        orders in the same second no longer stalls the import run."""
        limit = self.adapter.order_limit_value()
        orders = [self._order(1000 + i, '2026-06-22 05:30:00') for i in range(limit)]
        self._patch_orders_response(orders)

        result, next_page_token = self.adapter.receive_orders()

        self.assertEqual(len(result), limit)
        self.assertEqual(next_page_token, 1000 + limit - 1)
