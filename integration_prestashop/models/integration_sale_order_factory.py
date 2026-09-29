# See LICENSE file for full copyright and licensing details.

from odoo import models
from odoo.tools.float_utils import float_is_zero, float_round


class IntegrationSaleOrderFactory(models.TransientModel):
    _inherit = 'integration.sale.order.factory'

    def _prepare_order_line_price(self, order, price):
        price = super()._prepare_order_line_price(order, price)

        if not self.integration_id.is_integration_prestashop:
            return price

        return order.currency_id.round(price)

    def _get_sales_team_id(self, order_data):
        integration = self.integration_id
        customer_group_id = order_data.get('customer', {}).get('default_customer_group_id')

        if customer_group_id:
            mapping = integration.customer_group_mapping_ids.filtered(
                lambda m: m.external_customer_group_id.external_id == str(customer_group_id)
                and m.sales_team_id
            )
            if mapping:
                return mapping[0].sales_team_id.id

        return super()._get_sales_team_id(order_data)

    def _create_discount_line(self, order, discount_data):
        """
        Create PrestaShop discount line(s) from order-level discount amounts.

        When multiple_discount_lines is enabled and per-cart-rule data is available,
        creates one discount line per cart rule (coupon code shown in the description).

        Falls back to a single aggregate discount line with automatic tax inference
        (Guess A + Guess B) when:
          - the feature is disabled, or
          - discount_rules is None (order_cart_rule endpoint unavailable on this PS version).

        Returns an empty recordset when there is no discount on the order.
        """
        integration = self.integration_id

        if not integration.is_integration_prestashop:
            return super()._create_discount_line(order, discount_data)

        discount_tax_incl = abs(float(discount_data.get('total_discounts_tax_incl') or 0.0))
        discount_tax_excl = abs(float(discount_data.get('total_discounts_tax_excl') or 0.0))

        if not discount_tax_incl or not discount_tax_excl:
            return self.env['sale.order.line']

        if not integration.multiple_discount_lines:
            return self._create_discount_line_aggregate(order, discount_tax_incl, discount_tax_excl)

        discount_rules = discount_data.get('discount_rules')

        if discount_rules is None:
            # Endpoint not available — already warned at parse time; degrade gracefully.
            return self._create_discount_line_aggregate(order, discount_tax_incl, discount_tax_excl)

        if not discount_rules:
            return self.env['sale.order.line']

        self._get_discount_product()

        discount_lines = self.env['sale.order.line']

        for rule in discount_rules:
            lines = self._create_discount_line_per_rule(order, rule)
            discount_lines |= lines

        return discount_lines

    def _create_discount_line_aggregate(self, order, discount_tax_incl, discount_tax_excl):
        """
        Create a single aggregate discount line with automatic tax inference.

        PrestaShop reports the total discount as both a tax-inclusive and a
        tax-exclusive amount, but does not say which tax rate(s) apply to it.
        We infer the correct tax assignment by testing two strategies and
        picking the one whose computed tax matches the known discount tax amount
        (``discount_tax_incl - discount_tax_excl``) most closely.

        **Guess A — proportional distribution**
            Split the full discount across every tax group present on the order,
            weighted by each group's product subtotal.  The last tax group receives
            any rounding residual so the total always equals ``discount_price``.

        **Guess B — single tax group**
            Try applying the entire discount under each tax group in isolation
            (one candidate per group).  This works well when the discount targets
            products that all share the same rate.

        The candidate with the smallest absolute difference between its computed
        tax and the known discount tax is chosen, provided the relative error is
        < 1 %.  When no candidate meets that threshold (e.g. a complex mixed-rate
        order), Guess A is used as a safe fallback.

        **Example — discount applied only to taxed products (Guess B wins)**

            Order:
                Line A  €100 excl. @ 20 % VAT (price-included)
                Line B  €50  excl. @ 0 % VAT  (tax-exempt)

            Discount: €6.00 tax-incl. / €5.00 tax-excl.
            Known discount tax: €1.00  (= 6.00 − 5.00)
            discount_taxes = 5.00 − 6.00 = −1.00  (negative; discount price is negative)

            Guess A — proportional (weights: 100/150 and 50/150):
                −6.00 × (100/150) = −4.00 @ 20 % → tax = −4.00 × 20/120 ≈ −0.67
                −6.00 × (50/150)  = −2.00 @ 0  % → tax = 0
                Total computed tax ≈ −0.67  diff = |−0.67 − (−1.00)| = 0.33
                Relative error ≈ 33 % — exceeds 1 % threshold

            Guess B — full −6.00 @ 20 % only:
                tax = −6.00 × 20/120 = −1.00  diff = 0
                Relative error = 0 % < 1 % → accepted ✓

            Winner: Guess B @ 20 % — creates one discount line of −€6.00 with 20 % VAT.
            (The discount was entirely on the taxed product, so this is the correct result.)
        """
        self._get_discount_product()

        precision = self.env['decimal.precision'].precision_get('Product Price')
        product_lines = order.order_line.filtered(lambda x: not x.is_delivery)

        # The tax portion of the discount (always negative for positive rates because
        # discount_tax_excl < discount_tax_incl).  Used as the reference to minimise
        # against in step 4.
        discount_taxes = discount_tax_excl - discount_tax_incl

        # Use the tax-inclusive price when taxes are embedded in price_unit,
        # otherwise use the tax-exclusive amount so Odoo computes taxes on top.
        if self._get_tax_price_included(product_lines.mapped('tax_ids')):
            discount_price = discount_tax_incl * -1
        else:
            discount_price = discount_tax_excl * -1

        # Create a temporary no-tax placeholder so Odoo assigns a sequence number
        # and a name.  It will be replaced (or kept as-is) after tax inference.
        discount_line = self._insert_line_in_order(order, discount_price, False)

        # 1. Discount without taxes — nothing more to infer.
        if float_is_zero(discount_taxes, precision_digits=precision):
            return discount_line

        # 2. Group product lines by tax.
        #    all_grouped_taxes — accumulates subtotals per group (used by Guess A).
        #    grouped_taxes     — one entry per group with the full discount amount
        #                        (used by Guess B; last write wins per tax_key).
        all_grouped_taxes = {}
        grouped_taxes = {}
        all_lines_sum = 0
        delivery_line = order.order_line.filtered(lambda line: line.is_delivery)
        carrier_tax_id = delivery_line.tax_ids

        for line in product_lines:
            tax_key = str(line.tax_ids)
            all_lines_sum += line.price_subtotal

            # For Guess B: when all product subtotals are zero (every product is
            # free) fall back to the carrier tax; otherwise use the line's own tax.
            grouped_taxes.update({tax_key: {
                'tax_ids': line.tax_ids if line.price_unit and not all_lines_sum else carrier_tax_id,
                'discount': discount_price,
            }})
            all_grouped_taxes.update({tax_key: {
                'price_subtotal': (
                    line.price_subtotal
                    + all_grouped_taxes.get(tax_key, {}).get('price_subtotal', 0)
                ),
                'tax_ids': line.tax_ids,
            }})

        # 3. Guess A — distribute discount proportionally across tax groups.
        #    The last group absorbs any floating-point residual to ensure the
        #    discount lines sum exactly to discount_price.
        all_grouped_taxes = list(all_grouped_taxes.values())
        residual_amount = discount_price
        line_num = len(all_grouped_taxes)

        for tax_value in all_grouped_taxes:
            if line_num == 1 or not all_lines_sum:
                # Single group or all-zero subtotals: assign the full residual.
                tax_value['discount'] = residual_amount
            else:
                tax_value['discount'] = float_round(
                    value=discount_price * tax_value['price_subtotal'] / all_lines_sum,
                    precision_digits=precision,
                )

            residual_amount -= tax_value['discount']
            line_num -= 1

        # 4. Evaluate each candidate by temporarily writing it onto the placeholder
        #    line and reading back the ORM-computed price_tax.
        def calc_tax_summa(tax_values):
            tax_amount = 0
            for tax_value in tax_values:
                discount_line.tax_ids = tax_value['tax_ids']
                discount_line.price_unit = tax_value['discount']
                tax_amount += discount_line.price_tax
            return {
                'grouped_taxes': tax_values,
                'tax_diff': abs(tax_amount - discount_taxes),
            }

        # Guess A: proportional across all tax groups (one candidate).
        calc_taxes = [calc_tax_summa(all_grouped_taxes)]
        # Guess B: full discount under each individual tax group (one candidate per group).
        calc_taxes += [calc_tax_summa([grouped_tax]) for grouped_tax in grouped_taxes.values()]

        calc_taxes.sort(key=lambda calc_tax: calc_tax['tax_diff'])

        # Accept the best candidate only when its relative error is under 1 %.
        # Otherwise fall back to Guess A (proportional), which is always a valid
        # distribution even if not perfectly accurate.
        if abs(calc_taxes[0]['tax_diff'] / discount_taxes) < 0.01:
            the_most_suitable_discount = calc_taxes[0]['grouped_taxes']
        else:
            the_most_suitable_discount = all_grouped_taxes

        # Replace the placeholder with the final line(s) carrying the correct taxes.
        discount_line.unlink()

        discount_lines = self.env['sale.order.line']

        for tax_value in the_most_suitable_discount:
            discount_lines += self._insert_line_in_order(
                order,
                tax_value['discount'],
                tax_value['tax_ids'],
            )

        return discount_lines

    def _create_discount_line_per_rule(self, order, rule):
        """
        Create a single discount line for one cart rule.

        Finds the matching Odoo tax among those already on the order's product
        lines by comparing the rule's own tax-included / tax-excluded amounts
        in currency units (rather than computing a rate percentage), which is
        robust against the small rounding PrestaShop applies to monetary values.

        Falls back to no tax when no order tax matches (e.g. the rule spans
        products with mixed rates).
        """
        discount_tax_incl = abs(float(rule.get('total_discounts_tax_incl') or 0.0))
        discount_tax_excl = abs(float(rule.get('total_discounts_tax_excl') or 0.0))

        if not discount_tax_incl or not discount_tax_excl:
            return self.env['sale.order.line']

        tax = self._find_order_tax_by_amounts(order, discount_tax_incl, discount_tax_excl)

        if tax and self._get_tax_price_included(tax):
            price = discount_tax_incl * -1
        else:
            price = discount_tax_excl * -1

        line = self._insert_line_in_order(order, price, tax or False)
        if rule.get('code'):
            line.name = f'{line.name} (CODE: {rule["code"]})'

        return line
