# See LICENSE file for full copyright and licensing details.

import base64
import itertools
import json
import logging
import pytz

from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Union

from odoo import _
from odoo.tools import frozendict
from odoo.exceptions import UserError
from odoo.addons.integration.tools import IS_FALSE, IS_TRUE
from odoo.addons.integration.tools import (
    add_dynamic_kwargs, make_list_if_not, ExternalImage, ProductType,
)
from odoo.addons.integration.api.abstract_apiclient import AbsApiClient
from odoo.addons.integration.models.sale_integration import IMPORT_EXTERNAL_BLOCK

from .prestashop import Client, PRESTASHOP  # noqa
from .prestashop.webservice import PrestaShopAPIError
from ..integration.exceptions import ApiImportError


_logger = logging.getLogger(__name__)


ACCESSORIES_FETCH_BLOCK = 50

PRODUCT_TYPE_MAP = {
    'simple': 'consu',
    'pack': 'consu',
    'virtual': 'service',
}
ROOT_CMS_PAGE_CATEGORY_ID = '1'
NULL_DATETIME = '0000-00-00 00:00:00'

# We store human readable values for Delivery Time field, so we need to map them to
# PrestaShop values
PRESTASHOP_DELIVERY_TIME_MAPPING = {
    'none': '0',
    'default': '1',
    'specific': '2',
}


# TODO: all reading through pagination
class PrestaShopApiClient(AbsApiClient):

    default_receive_orders_filter = (
        '{"filter[current_state]": "[<put state id here>]"}'
    )

    settings_fields = (
        ('url', 'Shop URL', ''),
        ('admin_url', 'Admin URL', ''),
        ('key', 'Webservice Key', ''),
        ('language_id', 'Shop Language Code', ''),
        (
            'receive_orders_filter',
            'Receive Orders Filter',
            default_receive_orders_filter,
            True,
        ),
        ('import_products_filter', 'Import Products Filter', '{"active": "1"}'),
        ('id_group_shop', 'Shop Group where export products', ''),
        ('shop_ids', 'Shop ids in id_group_shop separated by comma', ''),
        (
            'PS_TIMEZONE',
            (
                'PrestaShop timezone value.'
                ' Will be automatically populated when integration is active'
            ),
            '',
        ),
        (
            'weight_uom',
            (
                'PrestaShop weight unit.'
                ' Will be automatically populated when integration is active'
            ),
            '',
        ),
        ('decimal_precision', 'Number of decimal places in the price of the exported product', '6'),
        *AbsApiClient.settings_fields,
    )

    def __init__(self, settings):
        super().__init__(settings)

        store_url = self.get_settings_value('url')
        api_key = self.get_settings_value('key')

        admin_url = self.get_settings_value('admin_url').strip('/')
        if not admin_url.endswith('index.php'):
            admin_url += '/index.php'
        self.admin_url = admin_url
        self._datetime_format = self._settings['datetime_format']

        self._client = Client(
            store_url,
            api_key,
        )

        self._language_id = self.get_settings_value('language_id')
        self._weight_uom = self.get_settings_value('weight_uom')

        self._client.id_group_shop = self._parse_numeric_ids(
            self.get_settings_value('id_group_shop'),
            'id_group_shop',
            allow_multiple=False,
        )
        self._client.shop_ids = self._parse_numeric_ids(
            self.get_settings_value('shop_ids'),
            'shop_ids',
        )

        self._client.default_language_id = self._language_id
        self._client.data_block_size = self._settings['data_block_size']

        self._default_shop_id = None

    @staticmethod
    def _parse_numeric_ids(value, setting_name, allow_multiple=True):
        if not value:
            return [] if allow_multiple else ''

        ids = [item.strip() for item in value.split(',')]

        error = None
        if any(not item.isdigit() for item in ids):
            error = _('Only numeric IDs are allowed.')
        elif not allow_multiple and len(ids) != 1:
            error = _('Only one numeric ID is allowed.')

        if error:
            raise UserError(_(
                'Invalid value for PrestaShop setting "%(setting)s": '
                '"%(value)s". %(error)s'
            ) % {
                'setting': setting_name,
                'value': value,
                'error': error,
            })

        return list(dict.fromkeys(ids)) if allow_multiple else ids[0]

    @property
    def lang(self):
        return self._language_id

    def get_api_resources(self):
        return self._client.get('')

    def get_users(self):
        # Old PrestaShop versions (1.6) do not have 'employee' model,
        # so we need be ready to get exception here
        try:
            records = self._client.model('employee').search_read(
                filters={'active': IS_TRUE},
                fields=['id', 'lastname', 'firstname', 'email'],
            )
        except PrestaShopAPIError:
            return []

        users = []
        for record in records:
            users.append({
                'id': record['id'],
                'name': '%s %s' % (record['firstname'], record['lastname']),
                'external_reference': record['email'],
            })

        return users

    def get_delivery_methods(self):
        delivery_methods = self._client.model('carrier').search_read(
            filters={
                'deleted': IS_FALSE,
                'id': '![0]',  # Exclude bad carriers
            },
            fields=['id', 'name'],
        )
        return delivery_methods

    def get_single_carrier(self, external_id):
        carrier = self._client.model('carrier').search_read(
            filters={'id': external_id},
            fields=['id', 'name'],
        )
        return carrier and carrier[0] or dict()

    def get_parent_delivery_methods(self, not_mapped_id):
        id_reference = self._client.model('carrier').search_read(
            filters={'id': not_mapped_id},
            fields=['id_reference'],
        )
        reference = id_reference and id_reference[0]
        if not reference:
            return False
        family_delivery_methods = self._client.model('carrier').search_read(
            filters={'id_reference': reference['id_reference']},
            fields=['id', 'name'],
        )
        return family_delivery_methods

    @property
    def default_shop_id(self):
        if not self._default_shop_id:
            self._default_shop_id = self.get_configuration('PS_SHOP_DEFAULT')

        return self._default_shop_id

    def get_weight_uom_for_converter(self):
        if not self._weight_uom:
            raise UserError(_(
                'Sale Integration setting "PrestaShop weight units" is not specified. '
                'To resolve this issue:\n'
                '1. Go to E-Commerce Integrations → Stores → <Your Store> → General tab.\n'
                '2. Deactivate integration using Deactivate button.\n'
                '3. Then activate the integration to populate weight unites automatically.'
            ))

        return self._weight_uom

    def get_weight_uoms(self):
        if self._weight_uom:
            return [self._weight_uom]
        return []

    def get_configuration(self, name):
        value = self._client.model('configuration').search_read(
            filters={'name': f'[{name}]'},
            fields=['value'],
            with_translation=True,
        )

        return value and value[0] if isinstance(value, list) else value

    def get_shops(self):
        return self._client.model('shop').search_read()

    def get_shop_groups(self):
        shop_groups = self._client.model('shop_group').search_read(
            fields=['id', 'name'],
        )
        return [(x['id'], x['name']) for x in shop_groups]

    def get_single_tax(self, tax_id):
        taxes = self.get_taxes()
        tax_list = [x for x in taxes if x['id'] == tax_id]
        return tax_list and tax_list[0] or dict()

    def get_taxes(self):
        """Will return the following list:
            [
                {'id': '1',
                 'rate': '5.000',
                 'name': 'CA 5%',
                 'tax_groups': [{'id': '6', 'name': 'CA Standard Rate'}]
                 },
                 {'id': '3',
                  'rate': '0.000',
                  'name': 'CA-MB 8%',
                  'tax_groups': [{'id': '6', 'name': 'CA Standard Rate'}]
                 },
                 ...
            ]
        """
        # first retrieve all taxes
        taxes = self._client.model('tax').search_read(
            filters={'deleted': IS_FALSE},
            fields=['id', 'name', 'rate'],
        )

        # retrieve tax groups and convert to dictionary for fast searching
        tax_groups = self._client.model('tax_rule_group').search_read(
            filters={'deleted': IS_FALSE},
            fields=['id', 'name'],
        )

        tax_groups_dict = dict((p['id'], p['name']) for p in tax_groups)

        # retrieve all tax rules
        tax_rules = self._client.model('tax_rule').search_read(
            fields=['id_tax_rules_group', 'id_tax'],
        )

        # create dictionary of tax groups per tax
        tax_to_tax_rule_dict = defaultdict(set)
        for tax_rule in tax_rules:
            tax_id = tax_rule['id_tax']
            tax_group_id = tax_rule['id_tax_rules_group']
            tax_group_name = tax_groups_dict.get(tax_group_id)
            if tax_group_name:
                tax_group_dict = frozendict(
                    {
                        'id': tax_group_id,
                        'name': tax_group_name,
                    }
                )
                tax_to_tax_rule_dict[tax_id].add(tax_group_dict)

        for tax in taxes:
            tax['tax_groups'] = list(tax_to_tax_rule_dict.get(tax['id'], []))

        return taxes

    @staticmethod
    def create_error_message(duplicate_dict, object_name):
        """
        Format and return a detailed error message for duplicates found in PrestaShop.

        :param duplicate_dict: Dictionary with duplicates (key: normalized code, values: list of records)
        :param object_name: Name of the object for which duplicates were searched for
        :return: str: A formatted error message
        """
        duplicate_message = []

        for key, vals in duplicate_dict.items():
            name, code = key[1], key[0]

            dupl_list = [f'[{d.get("iso_code")}] {d.get("name")} (id={d.get("id")})' for d in vals]

            text_error = (
                f'{name} ({code}) - ' +
                _('found in PrestaShop in the following records: ') +
                f'{", ".join(dupl_list)}'
            )

            duplicate_message.append(text_error)

        if duplicate_message:
            return _(
                'Duplicated active %s found in PrestaShop. To resolve this issue:\n'
                '1. Go to your PrestaShop system and locate the following duplicated records.\n'
                '2. Ensure each %s has a unique value for its name and code.\n'
                '3. Once the duplicates are resolved, requeue the job or retry the action.\n\nDetails:\n'
            ) % (object_name, object_name) + '\n'.join(duplicate_message)

        return ''

    def _find_duplicated_objects(self, converted_and_orig_list):
        """
        Search for duplicates in a tuple list (converted_record, original_record)

        :param converted_and_orig_list: list of tuples
        :return: dictionary with duplicates
        :return format: {(converted_code, converted_name): [{'id', 'iso_code', 'name'}, [dict],...]}
        """

        transformed_unique_key_list = []
        group_unique_key_dict = defaultdict(list)

        code_name_mapping = {}
        for converted, original in converted_and_orig_list:
            converted_reference = converted['external_reference']
            converted_name = code_name_mapping.get(converted_reference)
            if not converted_name:
                converted_name = converted['name']
                code_name_mapping[converted_reference] = converted_name
            converted_key = (converted_reference, converted_name)
            transformed_unique_key_list.append((converted_key, original))

        [
            group_unique_key_dict[key].extend(list(i[1] for i in group))
            for key, group in itertools.groupby(
                transformed_unique_key_list,
                key=lambda tuple_: tuple_[0])
        ]

        return {key: val for key, val in group_unique_key_dict.items() if len(val) >= 2}

    def get_countries(self):
        countries = self._client.model('country').search_read(
            filters={'active': IS_TRUE},
            fields=['id', 'name', 'iso_code'],
        )

        converted_countries = []
        for external_country in countries:
            converted_countries.append({
                'id': external_country.get('id'),
                'name': external_country.get('name'),
                'external_reference': external_country.get('iso_code'),
            })

        converted_and_orig_list = [
            (obj_conv, obj_orig)for obj_conv, obj_orig in zip(converted_countries, countries)
        ]
        duplicates_dict = self._find_duplicated_objects(converted_and_orig_list)
        error_duplicate_message = self.create_error_message(duplicates_dict, 'countries')
        if error_duplicate_message:
            raise ApiImportError(error_duplicate_message)

        return converted_countries

    def get_states(self):
        countries = self._client.model('country').search_read(
            filters={'active': IS_TRUE},
            fields=['id', 'name', 'iso_code'],
        )

        original_state, converted_states = [], []
        state_endpoint = self._client.model('state')

        for external_country in countries:
            states = state_endpoint.search_read(
                filters={'id_country': external_country['id'], 'active': IS_TRUE},
                fields=['id', 'name', 'iso_code'],
            )

            original_state.extend(states)

            for external_state in states:
                state_code = external_state.get('iso_code')
                if '-' in state_code:
                    # In prestashop some states are defined in a strange way like (NL-DE)
                    # We need to have only state code
                    state_code = state_code.split('-')[1]
                state_reference = '{}_{}'.format(
                    external_country.get('iso_code'),
                    state_code
                )

                converted_states.append({
                    'id': external_state.get('id'),
                    'name': external_state.get('name'),
                    'external_reference': state_reference,
                })

        converted_and_orig_list = [
            (obj_conv, obj_orig) for obj_conv, obj_orig in zip(converted_states, original_state)
        ]
        duplicates_dict = self._find_duplicated_objects(converted_and_orig_list)
        error_duplicate_message = self.create_error_message(duplicates_dict, 'states')
        if error_duplicate_message:
            raise ApiImportError(error_duplicate_message)

        return converted_states

    def get_payment_methods(self):
        orders = self._client.model('order').search_read(
            fields=['id', 'payment'],
            sort='[id_DESC]',
            limit=1000,
        )
        return [{'id': x['payment']} for x in orders]

    def get_languages(self):  # TODO: not optimal, better to use id_shop: all
        # TODO: if there is only one records presta returns it as simple {} rather than
        #  list of dicts [{}]
        added_language_ids = []
        languages = []

        ext_languages = self._client.model('language').search_read(
            filters={'active': IS_TRUE},
            fields=['id', 'name', 'language_code'],
            with_translation=True,
        )

        for ext_language in ext_languages:
            if ext_language['id'] not in added_language_ids:
                language_code = ext_language.get('language_code', '').replace('-', '_')
                languages.append({
                    'id': ext_language.get('id'),
                    'name': ext_language.get('name'),
                    # Converting language code to Odoo Format
                    'external_reference': language_code,
                })
                added_language_ids.append(ext_language['id'])

        return languages

    def _exclude_broken_values(self, resource, group_field, values):
        exist_ids = []
        group_ids = list(set([x[group_field] for x in values]))
        Endpoint = self._client.model(resource)

        while group_ids:
            ids = '|'.join(group_ids[:IMPORT_EXTERNAL_BLOCK])
            records = Endpoint.search_read(
                filters={'id': f'[{ids}]'},
                fields=['id'],
            )
            group_ids = group_ids[IMPORT_EXTERNAL_BLOCK:]
            exist_ids.extend([x['id'] for x in records])

        result = filter(lambda x: x[group_field] in exist_ids, values)
        return list(result)

    def get_attributes(self):
        attributes = self._client.model('product_option').search_read(
            fields=['id', 'name'],
            with_translation=True,
        )
        return attributes

    def get_attribute_values(self):
        attribute_values = self._client.model('product_option_value').search_read(
            filters={'id_attribute_group': f'![{IS_FALSE}]'},
            fields=['id', 'name', 'id_attribute_group'],
            with_translation=True,
        )
        attribute_values_filter = self._exclude_broken_values(
            'product_option',
            'id_attribute_group',
            attribute_values,
        )
        for attr in attribute_values_filter:
            value = attr.pop('id_attribute_group')
            attr['id_group'] = value

        return attribute_values_filter

    def get_features(self):
        features = self._client.model('product_feature').search_read(
            fields=['id', 'name'],
            with_translation=True,
        )
        return features

    def get_feature_values(self):
        feature_values = self._client.model('product_feature_value').search_read(
            filters={'id_feature': f'![{IS_FALSE}]'},
            fields=['id', 'value', 'id_feature'],
            with_translation=True,
        )
        feature_values_filtered = self._exclude_broken_values(
            'product_feature',
            'id_feature',
            feature_values,
        )
        for feature in feature_values_filtered:
            value = feature.pop('id_feature')
            feature['id_group'] = value
            feature['name'] = feature['value']

        return feature_values_filtered

    def get_locations(self):
        _logger.info('Prestashop "%s": get_locations(). Not Implemented.', self._integration_name)
        return []

    def get_pricelists(self):
        _logger.info('Prestashop "%s": get_pricelists()', self._integration_name)
        groups = self._client.model('group').search_read(
            fields=['id', 'name'],
            with_translation=True,
        )
        return [{'id': IS_FALSE, 'name': _('All Groups')}, *groups]

    def get_product_tags(self, filter_ids=None, filter_names=None):
        _logger.info('Prestashop "%s": get_product_tags()', self._integration_name)
        filters = {}
        if filter_ids:
            filters['id'] = '[%s]' % '|'.join(filter_ids)
        if filter_names:
            filters['name'] = '[%s]' % '|'.join(filter_names)

        return self._client.model('tag').search_read(
            filters=filters,
            fields=['id', 'name', 'id_lang'],
            with_translation=True,
        )

    def create_product_tag(self, name, language_id):
        tag = self._client.model('product_tag').create(
            {
                'name': name,
                'id_lang': language_id or self._client.default_language_id,
            },
        )
        return tag.id

    @add_dynamic_kwargs
    def get_categories(self, **kw):
        # Filter out category with ID = 1. See below code form Presta
        # Core/Domain/CmsPageCategory/ValueObject/CmsPageCategoryId.php#L39
        # public const ROOT_CMS_PAGE_CATEGORY_ID = 1;
        filters = {
            'id': '![%s]' % ROOT_CMS_PAGE_CATEGORY_ID,
        }

        integration = self._get_integration(kw)
        if not integration.import_inactive_categories:
            filters['active'] = IS_TRUE

        categories = self._client.model('category').search_read(
            filters=filters,
            fields=['id', 'name', 'id_parent', 'is_root_category'],
            with_translation=True,
        )

        result_categories = []
        for cat in categories:
            if cat['id_parent'] == ROOT_CMS_PAGE_CATEGORY_ID:
                cat['id_parent'] = IS_FALSE
            result_categories.append(cat)

        return result_categories

    def get_sale_order_statuses(self):
        external_order_states = self._client.model('order_state').search_read(
            filters={'deleted': IS_FALSE},
            fields=['id', 'name', 'template'],
            with_translation=True,
        )

        order_states = []
        for ext_order_state in external_order_states:
            order_states.append({
                'id': ext_order_state.get('id'),
                'name': ext_order_state.get('name'),
                # We cannot add any unique internal reference as in Prestashop it doesn't exist
                'external_reference': False,
            })
        return order_states

    def get_product_template_ids(self):
        template_ids = self._client.model('product').search_read_by_blocks(
            filters=self._get_product_filter_hook(),
            fields=self._get_product_fields_hook(['id']),
        )
        template_ids = self._filter_templates_hook(template_ids)
        return template_ids and [x['id'] for x in template_ids] or []

    @add_dynamic_kwargs
    def get_product_templates(self, template_ids, **kw):
        _logger.info('Prestashop "%s": get_product_templates()', self._integration_name)

        if not template_ids:
            return dict(), list(), list()

        integration = self._get_integration(kw)

        template_reference = integration.template_reference_api_name
        variant_reference = integration.variant_reference_api_name
        template_barcode = integration.template_barcode_api_name
        variant_barcode = integration.variant_barcode_api_name

        external_templates = self._client.model('product').search_read(
            filters={'id': '[%s]' % '|'.join(template_ids)},
            fields=['id', 'name', template_reference, template_barcode],
        )

        result = {
            str(x['id']): {
                'id': str(x['id']),
                'name': x['name'],
                'barcode': x.get(template_barcode) or None,
                'external_reference': x.get(template_reference) or None,
                'variants': [],
            }
            for x in external_templates
        }

        product_variants = self._client.model('combination').search_read(
            filters={'id_product': '[%s]' % '|'.join(template_ids)},
        )
        for variant in product_variants:
            template_id = str(variant['id_product'])

            if template_id in result:
                result[template_id]['variants'].append({
                    'id': self._build_product_external_code(template_id, variant['id']),
                    'name': result[template_id]['name'],
                    'external_reference': variant.get(variant_reference) or None,
                    'barcode': variant.get(variant_barcode) or None,
                    'ext_product_template_id': template_id,
                    'attribute_value_ids': self._parse_attribute_value_ids(variant),
                })

        # TODO: Implement errors handling
        errors = list()
        failed_external_template_ids = list()

        return result, failed_external_template_ids, errors

    def _parse_attribute_value_ids(self, variant):
        value_list = variant \
            .get('associations', {}) \
            .get('product_option_values', {}) \
            .get('product_option_value', [])

        return [x['id'] for x in make_list_if_not(value_list)]

    def get_customer_ids(self, date_since=None):
        filters = {}

        if date_since:
            filters['date_upd'] = f'>[{date_since}]'

        shop_ids = self._client.shop_ids
        if shop_ids:
            filters['id_shop'] = f'[{"|".join(shop_ids)}]'

        customers = self._client.model('customer').search_read_by_blocks(
            filters=filters,
            fields=['id'],
            date='1',
        )

        return [customer['id'] for customer in customers]

    def get_customer_and_addresses(self, customer_id):
        customer = self._client.model('customer').read_one(customer_id)
        addresses = self._client.model('address').search_read(
            filters={'id_customer': customer_id},
        )

        # The last address added is the address of the invoice. Let's put it on the partner.
        if addresses:
            addresses.sort(key=lambda x: x['date_add'], reverse=True)
            addresses[0]['type'] = 'invoice'
            for address in addresses[1:]:
                address['type'] = 'other'

        parsed_customer = self._parse_customer(customer)
        parsed_addresses = [self._parse_address(customer, x) for x in addresses]
        return parsed_customer, parsed_addresses

    def get_customer_groups(self):
        records = self._client.model('group').search_read(
            filters={
                'id': '![0]',  # Exclude bad groups
            },
            fields=['id', 'name'],
        )

        groups = []
        for record in records:
            groups.append({
                'external_id': record['id'],
                'name': record['name'],
            })

        return groups

    def create_webhooks_from_routes(self, routes_dict):
        result = dict()

        for name_tuple, route in routes_dict.items():
            webhook = self._client.model('webhook')

            webhook.url = route
            webhook.hook = name_tuple[-1]  # --> technical_name
            webhook.real_time = IS_TRUE
            webhook.active = IS_TRUE
            webhook.retries = 0

            webhook.save()
            result[name_tuple] = str(webhook.id)

        return result

    def unlink_existing_webhooks(self, external_ids=None):
        if not external_ids:
            return False

        webhooks = self._client.model('webhook').search({
            'id': '[%s]' % '|'.join(external_ids)
        })
        result = webhooks.delete()
        return result

    def export_category(self, category):
        presta_category = self._client.model('category').create(category)
        return presta_category.id

    def find_existing_template(self, template: dict):
        products = template['products']
        variant_refs = [x['reference'] for x in products]
        reference_api_field = products[0]['reference_api_field']

        # Let's validate if all found products belong to the same product template

        templates, variants = self._get_products_and_variants(
            ['id', 'name', reference_api_field],
            ['id', 'id_product', reference_api_field],
            {reference_api_field: '[%s]' % '|'.join(variant_refs)},
        )
        ids_set = {str(x['id']) for x in templates}
        ids_set.update([str(x['id_product']) for x in variants])

        if not len(ids_set):
            return None

        if len(ids_set) > 1:
            error_message = _(
                'Product references "%s" found in multiple PrestaShop products: %s. '
                'This structure is not allowed because in Odoo, the same references already belong to '
                'a single product template and its variants. Please ensure the product structure in '
                'PrestaShop matches Odoo.'
            ) % (', '.join(variant_refs), ', '.join(list(ids_set)))
            raise UserError(error_message)

        external_template_id = list(ids_set)[0]

        external_template_record = next(
            (x for x in templates if str(x['id']) == external_template_id),
            None
        )

        external_template_name = (
            external_template_record.get('name', False)
            if external_template_record
            else False
        )

        # Validate the number of variants in Odoo and PrestaShop
        product_combinations = self._client.model('combination').search_read(
            filters={'id_product': f'[{external_template_id}]'},
        )
        # counting expected variants excluding "virtual" variant
        template_variants_count = len([x for x in products if x['attribute_values']])
        if template_variants_count != len(product_combinations):
            error_message = _(
                'The number of combinations in PrestaShop (%s) does not match the number in Odoo (%s). '
                'Please ensure the product with ID %s in PrestaShop has the same number of combinations '
                'as the variants in Odoo (integration: "%s").'
            ) % (
                len(product_combinations),
                template_variants_count,
                external_template_id,
                self._integration_name,
            )
            raise UserError(error_message)

        # Validate references on combinations in PrestaShop
        for variant in product_combinations:
            # Make sure that reference is set on the combination
            if variant['id'] != IS_FALSE and not variant[reference_api_field]:
                error_message = _(
                    'Product with ID "%s" in PrestaShop is missing references for some combinations. '
                    'Please add these references and relaunch the product export.'
                ) % external_template_id
                raise UserError(error_message)

            attribute_values_from_presta = self._parse_attribute_value_ids(variant)
            attribute_values_from_odoo = list(
                filter(lambda x: x['reference'] == variant[reference_api_field], products)
            )
            if not len(attribute_values_from_odoo):
                error_message = _(
                    'No corresponding variant in Odoo with %s "%s" for PrestaShop product ID %s. '
                    'Ensure variants in Odoo and PrestaShop match correctly.'
                ) % (reference_api_field, variant[reference_api_field], external_template_id)
                raise UserError(error_message)

            attribute_values_from_odoo = [
                x['external_id'] for x in attribute_values_from_odoo[0]['attribute_values']
            ]
            if Counter(attribute_values_from_odoo) != Counter(attribute_values_from_presta):
                error_message = _(
                    'Mismatch in attribute values for PrestaShop variant with %s "%s". '
                    'PrestaShop attributes: %s. Odoo attributes: %s. Ensure the combinations '
                    'of attributes in PrestaShop and Odoo match for products with the same %s.'
                ) % (
                    reference_api_field,
                    variant[reference_api_field],
                    attribute_values_from_presta,
                    attribute_values_from_odoo,
                    reference_api_field,
                )
                raise UserError(error_message)

        return {
            'id': external_template_id,
            'name': external_template_name,
        }

    def validate_template(self, template: dict) -> list:
        _logger.info('Prestashop "%s": validate_template().', self._integration_name)
        ext_records_to_delete = []

        # (1) if template with such external id exists?
        presta_product_id = template['external_id']
        if presta_product_id:
            presta_product = self._client.model('product').search_read(
                filters={'id': presta_product_id},
                fields=['id']
            )
            if len(presta_product) == 0:
                ext_records_to_delete.append({
                    'model': 'product.template',
                    'odoo_external_id': template['odoo_external_id'],
                    'external_id': str(presta_product_id),
                })

        # (2) if variant with such external id exists?
        for variant in template['products']:
            variant_ext_id = variant['external_id']
            if not variant_ext_id:
                continue

            __, presta_combination_id = self._parse_product_external_code(variant_ext_id)

            if presta_combination_id:
                presta_combination = self._client.model('combination').search_read(
                    filters={'id': presta_combination_id},
                    fields=['id']
                )
                if len(presta_combination) == 0:
                    ext_records_to_delete.append({
                        'model': 'product.product',
                        'odoo_external_id': variant['odoo_external_id'],
                        'external_id': str(variant_ext_id),
                    })

        return ext_records_to_delete

    def export_template(self, template):
        _logger.info('Presta: export_template(%s)', template['external_id'])

        product = self._client.model('product').get(template['external_id'])
        self._fill_product(product, template)

        variants = template['products']

        # List of external variant IDs.
        # Note: During the first import, variants may not yet have an 'external_id'.
        variant_external_ids = [
            rec['external_id'].split('-')[1]
            for rec in variants if rec['external_id']
        ]

        # Removes inactive internal variant-associated external variants from a template.
        product_combinations = product.get_combinations()
        for combination in product_combinations:
            if str(combination.id) not in variant_external_ids:
                combination.delete()

        # we save product type here, before save, because it
        # got overridden with incorrect type after save
        presta_product_type = product.type
        product.save()
        product_id = str(product.id)

        mappings = [{
            'model': 'product.template',
            'id': template['id'],
            'odoo_external_id': template['odoo_external_id'],
            'external_id': product_id,
        }]

        if presta_product_type == 'pack':
            stock = self._client.model('stock_available').search({
                'id_product': product_id,
            })

            # There can be multiple stocks if customer has multiple shops
            # We push the same quantity to all stocks
            for stock_item in stock:
                stock_item.save()

        default_combination_id = None
        has_attributes = template.get('has_attributes', False)

        for variant in variants:
            if has_attributes:
                combination_id = self._export_product(product.id, variant)
                if variant['is_default']:
                    default_combination_id = combination_id
            else:
                combination_id = IS_FALSE

            mappings.append({
                'model': 'product.product',
                'id': variant['id'],
                'odoo_external_id': variant['odoo_external_id'],
                'external_id': self._build_product_external_code(product_id, combination_id)
            })

        if default_combination_id:
            product.id_default_combination = default_combination_id
            product.save()

        return mappings

    def _fill_product(self, product, vals):
        # We do not update the product type during subsequent exports, as the product type
        # typically remains unchanged after the initial creation. This code is primarily
        # intended for setting initial product properties.
        if not product.type:
            product.type = 'simple'
            product.state = IS_TRUE
            product.is_virtual = IS_FALSE

            if vals['type'] == 'service':
                product.type = 'virtual'
                product.is_virtual = IS_TRUE

        # We do not support "Minimum quantity for sale" as a feature
        # This field will have None value during first export
        if product.minimal_quantity is None or product.minimal_quantity == '0':
            product.minimal_quantity = '1'

        tags_data = vals['fields'].pop('tags', None)
        if isinstance(tags_data, list):
            export_ids = self._prepare_product_tags(tags_data)
            product.tags = export_ids

        for field, value in vals['fields'].items():
            if self.is_translated_value(value):
                self._fill_translated_field(product, field, value)
            else:
                setattr(product, field, value)

        if vals['kits'] and vals['variants_count'] <= 1:
            product.type = 'pack'

            bundle_products = []
            for component in vals['kits']:
                product_id, combination_id = component['product_id'].split('-')
                bundle_products.append({
                    'id': product_id,
                    # Due to a bug in PrestaShop (1.7 and 8), 'id_product_attribute' attribute can be
                    # ignored when creating a bundle product. In this case first combination will be
                    # used automatically.
                    # https://github.com/PrestaShop/PrestaShop/issues/32954
                    'id_product_attribute': combination_id,
                    'quantity': component['qty'],
                })

            product.product_bundle = bundle_products

    def _prepare_product_tags(self, tags_data: list[dict]):
        external_tags_data = tags_data
        external_tag_names = [tag['name'] for tag in external_tags_data]
        shop_tag_names = self.get_product_tags(filter_names=external_tag_names)

        export_ids = []
        for external_tag in external_tags_data:
            shop_tag = next(
                (
                    tag for tag in shop_tag_names
                    if tag['name'] == external_tag['name']
                    and tag['id_lang'] == external_tag['language']
                ),
                None,
            )
            if shop_tag:
                export_ids.append(shop_tag['id'])
            else:
                created_tag_id = self.create_product_tag(external_tag['name'], external_tag['language'])
                export_ids.append(created_tag_id)

        return export_ids

    def _fill_translated_field(self, model, field, value):
        for lang_id, translation in value['language'].items():
            setattr(model.lang(lang_id), field, translation or '')

    def _export_product(self, presta_product_id, product):
        if product['external_id']:
            product_id, combination_id = self._parse_product_external_code(product['external_id'])
        else:
            product_id, combination_id = presta_product_id, None

        if combination_id:
            combination = self._client.model('combination').get(combination_id)
            self._fill_combination(combination, product, product_id)
            combination.save()
        else:
            combination = self._client.model('combination')
            prestashop_product = self._client.model('product').get(product_id)
            if product['attribute_values']:
                self._fill_combination(combination, product, product_id)
                combination = prestashop_product.add_combination(combination)
            else:
                combination.id = IS_FALSE  # update template with some values

        return combination.id

    def _fill_combination(self, combination, vals, product_id):
        combination.id_product = product_id

        for field, value in vals['fields'].items():
            if self.is_translated_value(value):
                self._fill_translated_field(combination, field, value)
            else:
                setattr(combination, field, value)

        # We do not support "Minimum quantity for sale" as a feature
        # We do not support "Minimum quantity for sale" as a feature
        # This field will have None value during first export
        if combination.minimal_quantity is None or combination.minimal_quantity == '0':
            combination.minimal_quantity = '1'

        if vals['attribute_values']:
            attribute_value_ids = [x['external_id'] for x in vals['attribute_values']]
            product_option_values = self._client.model('product_option_value').get(
                attribute_value_ids,
            )
            combination.product_option_values = product_option_values

    def get_special_prices(self, external_codes, **params):
        shops = self.get_shops()

        # Even if there is only one shop (e.g., id_shop=1),
        # PrestaShop gives us the possibility to create special prices with id_shop=0,
        # so we need to take it into account.
        if len(shops) == 1:
            join_shop_ids = f'{IS_FALSE}|{shops[0]["id"]}'
            join_group_ids = f'{IS_FALSE}|{shops[0]["id_shop_group"]}'
        else:
            join_shop_ids = '|'.join([
                IS_FALSE,
                *self._client.shop_ids,
            ])
            join_group_ids = '|'.join([
                IS_FALSE,
                *([self._client.id_group_shop] if self._client.id_group_shop else []),
            ])

        params.update(
            id_shop=f'[{join_shop_ids}]',
            id_shop_group=f'[{join_group_ids}]',
        )

        # 1. Fetch records for specific `id_group`
        record_list = self._client.model('specific_price') \
            .search_read_by_blocks(filters=params)

        # 2. Serialize data
        data = defaultdict(list)
        for record in record_list:
            id_product = record['id_product']
            if external_codes and id_product not in external_codes:
                continue

            vals = self._parse_prices_vals(record)
            key = (id_product, record['id_product_attribute'])
            data[key].append(vals)

        return data

    def _parse_prices_vals(self, record):
        price = record['price']
        if price.startswith('-'):
            price = False

        vals = {
            'id': int(record['id']),
            'fixed_price': float(price),
            'reduction': float(record['reduction']),
            'reduction_type': record['reduction_type'],
            'min_quantity': float(record['from_quantity']),
            'date_end': self._parse_price_rule_date(record['to']),
            'date_start': self._parse_price_rule_date(record['from']),
            'reduction_tax_included': record['reduction_tax'] == IS_TRUE,
        }
        return vals

    def export_pricelists(self, data, updating=False):
        tmpl_data, var_data_list = data

        # 1. Export `template` prices
        self._export_specific_price_multi(tmpl_data, updating)

        # 2. Export `variant` prices
        for variant_data in var_data_list:
            self._export_specific_price_multi(variant_data, updating)

        return tmpl_data, var_data_list

    def _export_specific_price_multi(self, data_class, updating):
        force_unlink = data_class.force_sync_pricelist or not updating
        tmpl_id, comb_id = data_class._parse_template_and_combination()
        external_group_ids = data_class.join_external_groups()

        existing_price_ids = self._client.model('specific_price').search({
            'id_product': f'[{tmpl_id}]',
            'id_product_attribute': f'[{comb_id}]',
            'id_group': f'[{external_group_ids}]',
        })
        if existing_price_ids:
            if force_unlink:
                res = existing_price_ids.delete()
            else:
                to_unlink_prices = self._find_to_unlink_prices(
                    data_class,
                    existing_price_ids,
                )
                to_unlink_prices_ids = to_unlink_prices.ids
                res = to_unlink_prices.delete()

                data_class.update_unlinked(to_unlink_prices_ids)

            if not res:
                data_class.update_unlinked([])
                return data_class

        for price_rule in data_class.prices:
            res = self._export_specific_price_one(tmpl_id, comb_id, price_rule)
            data_class.update_result((price_rule['_item_id'], res))

        return data_class

    def _export_specific_price_one(self, tmpl_id, comb_id, price_rule):
        key_value = self._prepare_specific_price_vals(tmpl_id, comb_id, price_rule)
        specific_price_id = self._client.model('specific_price')

        for key, value in key_value.items():
            setattr(specific_price_id, key, value)

        res = specific_price_id.save()
        return res and res.get('id') and int(res.get('id'))

    def _prepare_specific_price_vals(self, tmpl_id, comb_id, rule):
        vals = self._get_default_price_vals()
        extra_vals = {
            'id_product': tmpl_id,
            'id_product_attribute': comb_id,
            'price': str(rule['price'] or -1),  # Negative number is important for non `fixed-price`
            'reduction': str(rule['reduction']),
            'reduction_type': rule['reduction_type'],
            'id_group': rule['external_group_id'],
            'from_quantity': str(rule['min_quantity']),
            'to': self._format_price_rule_date(rule['date_end']),
            'from': self._format_price_rule_date(rule['date_start']),
            'reduction_tax': [IS_FALSE, IS_TRUE][rule['reduction_tax_included']],
        }
        vals.update(extra_vals)
        return vals

    def _find_to_unlink_prices(self, data_class, existing_item_ids):
        # 1. Filter previously added
        outdated_external_ids = data_class.parsed_external_items()
        ids_to_unlink = [
            x.id for x in existing_item_ids if x.id in outdated_external_ids
        ]
        # 2. Filter records with the same period of time
        twin_list = [
            (
                self._format_price_rule_date(x['date_start']),
                self._format_price_rule_date(x['date_end']),
            )
            for x in data_class.prices
        ]

        for rec in existing_item_ids:
            key = (getattr(rec, 'from'), getattr(rec, 'to'))
            if key in twin_list:
                ids_to_unlink.append(rec.id)

        ids_to_unlink.sort()
        existing_item_ids._ids = list(set(ids_to_unlink))
        return existing_item_ids

    def _format_price_rule_date(self, value):
        if not value:
            return NULL_DATETIME

        # If `value` is naive (without tzinfo), consider it as UTC
        if value.tzinfo is None:
            utc_tz = pytz.UTC
            value = utc_tz.localize(value)

        # Convert to PrestaShop timezone if configured
        ps_timezone = self.get_configuration('PS_TIMEZONE')
        if ps_timezone:
            local_tz = pytz.timezone(ps_timezone)

            # Convert from UTC to PrestaShop local timezone
            value = value.astimezone(local_tz)

        return datetime.strftime(value, self._datetime_format)

    def _parse_price_rule_date(self, value: str) -> Union[datetime, bool]:
        try:
            dt = datetime.strptime(value, self._datetime_format)
        except ValueError:
            return False

        ps_timezone = self.get_configuration('PS_TIMEZONE')
        local_timezone = datetime.now().astimezone().tzinfo

        if ps_timezone:
            try:
                ps_tz = pytz.timezone(ps_timezone)

                if dt.tzinfo is None:
                    dt = ps_tz.localize(dt)

                # Convert to server timezone
                dt = dt.astimezone(local_timezone)
                dt = dt.replace(tzinfo=None)
            except Exception:
                # If PS_TIMEZONE is invalid, simply consider the string already to be in the server's time zone
                pass

        return dt

    @staticmethod
    def _get_default_price_vals():
        return {
            'id_shop': IS_FALSE,
            'id_cart': IS_FALSE,
            'id_country': IS_FALSE,
            'id_currency': IS_FALSE,
            'id_customer': IS_FALSE,
            'id_shop_group': IS_FALSE,
            'id_specific_price_rule': IS_FALSE,
        }

    def export_template_images(
        self,
        external_template_id: str,
        datacls_list: List[ExternalImage],
        **kw,
    ) -> List[ExternalImage]:
        """
        1. All the product images stores on the template level.
        2. Product variant has the M2M keys to images from parent template (variant support several images).
        3. Variant has no property like "position" so no way to assign the master/slave variant cover.
        """
        _logger.info('Prestashop "%s": export_images()', self._integration_name)

        external_template = self._client.model('product').get(external_template_id)

        # 1. Get combinations after unlinking images
        combinations = external_template.get_combinations()
        combinations_dict = {str(x.id): x for x in combinations}

        # 2. Prepare images to create — grouped by checksum, preserving original sequence order
        to_create_by_checksum = defaultdict(list)
        for datacls in datacls_list:
            if datacls.to_create:
                to_create_by_checksum[datacls.checksum].append(datacls)
        assign_variants_images_dict = defaultdict(list)
        save_external_template = False

        # 2.1 Grouping images by checksum to avoid duplicates
        for checksum, group in to_create_by_checksum.items():
            image_id = external_template.add_image(group[0].b64_bytes)

            for external_variant_id in [x.variant_code for x in group if x.is_variant]:
                assign_variants_images_dict[external_variant_id].append(image_id)

            if any(x.is_template_cover for x in group):
                external_template.id_default_image = image_id
                save_external_template = True

            # 2.2 Update datacls with new image data to update Odoo mappings
            datacls_to_update = [x for x in datacls_list if (x.to_assign and x.checksum == checksum)]
            datacls_to_update.extend(group)

            for datacls in datacls_to_update:
                datacls.update(
                    code=image_id,
                    name=image_id,
                    src=f'{self._client._api_url}images/products/{external_template_id}/{image_id}',
                )

        # 3. Prepare images ids to reassign
        for datacls in [x for x in datacls_list if x.to_assign]:
            if datacls.is_template:
                if datacls.is_cover:
                    external_template.id_default_image = datacls.code
                    save_external_template = True
                continue

            assign_variants_images_dict[datacls.variant_code].append(datacls.code)

        # 4. Save variants with new assigned images
        for external_variant_id, image_ids in assign_variants_images_dict.items():
            if external_variant_id in combinations_dict:
                external_variant = combinations_dict[external_variant_id]
                external_variant._assign_images(image_ids)

        # 5. Save template if cover image was updated
        if save_external_template:
            external_template.save()

        # 6. Drop old images. Do it after the ALL PREVIOUS ACTIONS to avoid Presta error
        # when we unlinking the cover image and cover is undefined
        current_ids = [x.code for x in datacls_list if x.code]
        external_images = external_template.get_images()

        for image in external_images:
            if str(image.id) not in current_ids:
                image.delete()

        return datacls_list

    def export_attribute(self, attribute):
        product_option = self._client.model('product_option')

        self._fill_translated_field(
            product_option,
            'name',
            attribute['name'],
        )

        self._fill_translated_field(
            product_option,
            'public_name',
            attribute['name'],
        )

        product_option.group_type = 'select'
        product_option.save()

        return product_option.id

    def export_attribute_value(self, attribute_value):
        product_option_value = self._client.model('product_option_value')

        self._fill_translated_field(
            product_option_value,
            'name',
            attribute_value['name'],
        )

        product_option_value.id_attribute_group = attribute_value['attribute']
        product_option_value.save()

        return product_option_value.id

    def export_feature(self, feature):
        product_feature = self._client.model('product_feature')

        self._fill_translated_field(
            product_feature,
            'name',
            feature['name'],
        )

        product_feature.save()

        return product_feature.id

    def export_feature_value(self, feature_value):
        product_feature_value = self._client.model('product_feature_value')

        self._fill_translated_field(
            product_feature_value,
            'value',
            feature_value['name'],
        )

        product_feature_value.id_feature = feature_value['feature_id']
        product_feature_value.save()

        return product_feature_value.id

    def order_fetch_kwargs(self, page_token=None):
        limit = self.order_limit_value()
        integration = self.integration
        # The date filter stays fixed for the whole import run. We paginate by a keyset on the
        # immutable id (filter[id] > last_seen_id), not by `limit=offset,count`: offset over a
        # set that can shrink mid-run (an order leaving the status filter, or being deleted)
        # shifts later rows and would skip the one on a page boundary. A keyset by id is immune
        # to that, to reordering, and to same-second bursts. The resume date is
        # max(updated_at) across all pages, carried by the driver.
        receive_from = integration.last_receive_orders_datetime_str
        cut_off_datetime = integration.orders_cut_off_datetime_str

        options = {
            'date': IS_TRUE,
            'display': 'full',
            'sort': '[id_asc]',
            'limit': limit,
            'filter[date_upd]': f'>[{receive_from}]',
        }

        if page_token:  # keyset continuation: only orders with a higher id than the last page
            options['filter[id]'] = f'>[{page_token}]'

        if cut_off_datetime:
            options['filter[date_add]'] = f'>[{cut_off_datetime}]'

        # Update values from stored settings
        settings_filter = self.get_settings_value('receive_orders_filter')
        options.update(settings_filter)

        return {
            'options': options,
        }

    def receive_orders(self, page_token=None):
        _logger.info('Prestashop "%s": receive_orders()', self._integration_name)

        # For using the `search_read` instead of the `get` method need to migrate params:
        # filter[current_state] --> current_state, etc
        kwargs = self.order_fetch_kwargs(page_token=page_token)
        response = self._client.get('orders', **kwargs)['orders']
        orders = response['order'] if response else list()

        result = list()
        for order in make_list_if_not(orders):
            data = self._get_input_file_data(order)
            vals = dict(
                id=order['id'],
                data=data,
                updated_at=order['date_upd'],
                created_at=order['date_add'],
            )
            result.append(vals)

        # Full page -> more orders remain: next page starts after the last id; else done.
        next_page_token = None
        if len(result) == self.order_limit_value():
            next_page_token = result[-1]['id']

        return result, next_page_token

    def receive_order(self, order_id):
        order = self._client.model('order').read_one(order_id)
        if not order:
            return order

        order_data = self._get_input_file_data(order)
        return {
            'id': order_id,
            'data': order_data,
        }

    def _get_messages_list(self, order_id):
        # Old versions of PrestaShop (1.6) do not have the `message` endpoint,
        # so we need to be ready to get exception here
        try:
            messages = self._client.model('message').search_read(
                filters={'id_order': order_id},
                with_translation=True,
            )
            return messages
        except PrestaShopAPIError:
            return []

    def _get_input_file_data(self, order):
        customer = self._client.model('customer').read_one(order['id_customer'])

        address_endpoint = self._client.model('address')
        delivery_address = address_endpoint.read_one(order['id_address_delivery'])
        invoice_address = address_endpoint.read_one(order['id_address_invoice'])

        input_file_data = {
            'order': order,
            'customer': customer,
            'delivery_address': delivery_address,
            'invoice_address': invoice_address,
            'messages': self._get_messages_list(order['id']),
            'payment_transactions': self._fetch_order_payments(order['reference'])
        }
        return input_file_data

    def _get_carrier_tax_ids(self, carrier_id, country_id, state_id, postcode):
        if not carrier_id or carrier_id == IS_FALSE:
            return list(), IS_FALSE

        tax_rule_group = self._client.model('carrier').search_read(
            filters={'id': carrier_id},
            fields=['id_tax_rules_group'],
        )

        tax_rule_group_id = tax_rule_group and tax_rule_group[0]['id_tax_rules_group']['value']

        return self._get_taxes_by_tax_rule(tax_rule_group_id, country_id, state_id, postcode)

    def _get_taxes_by_tax_rule(self, tax_rule_group_id, country_id, state_id, postcode):
        # Based on https://github.com/
        #     PrestaShop/PrestaShop/blob/develop/classes/tax/TaxRulesTaxManager.php#L74

        # behavior:
        #     '0' - this tax only
        #     '1' - combine
        #     '2' - one after another
        first_row = True
        behavior = IS_FALSE
        tax_ids = list()

        if not tax_rule_group_id or not country_id \
                or tax_rule_group_id == IS_FALSE or country_id == IS_FALSE:
            return tax_ids, behavior

        tax_rules = self._client.get(
            'tax_rules',
            options={
                'filter[id_country]': f'[{country_id}]',
                'filter[id_state]': f'[0|{state_id}]',
                'filter[id_tax_rules_group]': f'[{tax_rule_group_id}]',
                'display': '[id,id_state,zipcode_from,zipcode_to,id_tax,behavior]',
                'sort': '[zipcode_from_DESC,zipcode_to_DESC,id_state_DESC]',
            }
        )

        tax_rules = tax_rules['tax_rules'] and tax_rules['tax_rules']['tax_rule']

        if not tax_rules:
            return tax_ids, behavior

        if isinstance(tax_rules, dict):
            tax_rules = [tax_rules]

        if not postcode:
            postcode = ''

        tax_rules = list(
            filter(
                lambda x: (x['zipcode_from'] <= postcode <= x['zipcode_to'])
                or (x['zipcode_to'] == IS_FALSE and x['zipcode_from'] in [IS_FALSE, postcode]),
                tax_rules,
            )
        )

        for rule in tax_rules:
            tax_ids.append(rule['id_tax'])

            if first_row:
                behavior = rule['behavior']
                first_row = False

            if rule['behavior'] == IS_FALSE:
                break

        return tax_ids, behavior

    def fetch_order_transactions(self, order_ref):
        transactions = self._fetch_order_payments(order_ref)
        return [self._parse_payment_transaction(x) for x in transactions]

    def _fetch_order_payments(self, order_ref):
        transactions = self._client.model('order_payment').search_read(
            filters={'order_reference': order_ref},
        )
        return transactions

    @add_dynamic_kwargs
    def parse_order(self, input_file, **kw):
        _logger.info('Prestashop "%s": parse_order() from input file.', self._integration_name)
        integration = self._get_integration(kw)

        order = input_file['order']
        customer = input_file['customer']
        delivery_address = input_file['delivery_address']
        invoice_address = input_file['invoice_address']
        messages = input_file['messages']
        transactions = input_file['payment_transactions']

        is_cancelled = False
        status_code = order['current_state']
        sub_status_id = kw['_env']['sale.order.sub.status'] \
            .from_external(integration, status_code)
        if integration.sub_status_cancel_id and integration.sub_status_cancel_id == sub_status_id:
            is_cancelled = True

        delivery_notes = ''
        if messages:
            delivery_notes_list = [
                msg.get('message') for msg in messages if msg.get('private') == IS_FALSE
            ]
            delivery_notes = '\n'.join(delivery_notes_list)

        order_rows = make_list_if_not(order['associations']['order_rows']['order_row'])

        presta_currency = self._client.model('currency').search_read(
            filters={
                'id': order['id_currency'],
            },
            fields=['iso_code'],
        )
        currency = presta_currency and presta_currency[0] or dict()

        carrier_tax_ids, carrier_tax_behavior = self._get_carrier_tax_ids(
            order['id_carrier'],
            delivery_address.get('id_country'),
            delivery_address.get('id_state'),
            delivery_address.get('postcode'),
        )
        wrapping_tax_ids, wrapping_tax_behavior = self._get_taxes_by_tax_rule(
            self.get_configuration('PS_GIFT_WRAPPING_TAX_RULES_GROUP'),
            delivery_address.get('id_country'),
            delivery_address.get('id_state'),
            delivery_address.get('postcode'),
        )

        carrier = {}
        carrier_id = order.get('id_carrier')
        if carrier_id and carrier_id != IS_FALSE:
            carrier = {
                'id': carrier_id,
                'name': '',
                'is_pickup_point': False,
            }

        paid_total = order.get('total_paid_tax_incl') or order.get('total_paid')
        computed_total = (
            float(order['total_products_wt'])
            + float(order['total_shipping_tax_incl'])
            + float(order['total_wrapping_tax_incl'])
            - float(order['total_discounts_tax_incl'])
        )
        amount_total = float(paid_total) if paid_total else computed_total

        parsed_order = {
            'id': order['id'],
            'ref': order['reference'],
            'current_order_state': order['current_state'],
            'date_order': order['date_add'],
            'integration_workflow_states': [order['current_state']],
            'currency': currency.get('iso_code', ''),
            'lines': [self._parse_order_row(order['id'], x) for x in order_rows],
            'payment_method': order['payment'],
            'payment_transactions': [self._parse_payment_transaction(x) for x in transactions],
            'amount_total': amount_total,
            'delivery_data': {
                'delivery_notes': delivery_notes,
                'shipping_cost_tax_excl': float(order['total_shipping_tax_excl']),
                'carrier': carrier,
                'shipping_cost': float(order['total_shipping']),
                'carrier_tax_rate': float(order['carrier_tax_rate']),
                'taxes': carrier_tax_ids,
                'carrier_tax_behavior': carrier_tax_behavior,  # TODO: what we have to do with that
                'discount': dict(),
            },
            'discount_data': {
                'total_discounts_tax_incl': float(order['total_discounts_tax_incl']),
                'total_discounts_tax_excl': float(order['total_discounts_tax_excl']),
                'discount_rules': self._fetch_order_cart_rules(order['id']),
            },
            'gift_data': {
                'do_gift_wrapping': order['gift'] == IS_TRUE,
                'gift_message': order['gift_message'],
                'wrapping_tax_ids': wrapping_tax_ids,
                'total_wrapping_tax_incl': float(order['total_wrapping_tax_incl']),
                'total_wrapping_tax_excl': float(order['total_wrapping_tax_excl']),
                'wrapping_tax_behavior': wrapping_tax_behavior,  # TODO: what we have to do with ?
                'recycled_packaging': order['recyclable'] == IS_TRUE,  # TODO: handle in future
            },
            'order_risks': list(),
            'order_transactions': list(),
            'external_tags': list(),
            'order_fulfillments': list(),
            'external_location_id': False,
            'is_cancelled': is_cancelled,
        }

        if customer:
            parsed_order['customer'] = self._parse_customer(customer)

        if delivery_address:
            parsed_order['shipping'] = self._parse_address(customer, delivery_address)

        if invoice_address:
            parsed_order['billing'] = self._parse_address(customer, invoice_address)

        return parsed_order

    def _fetch_order_cart_rules(self, order_id):
        """
        Fetch per-coupon discount breakdown for an order from PrestaShop.

        Returns:
          - list of dicts  when the endpoint is available (empty list = no rules on order)
          - None           when the endpoint is not available (old PS versions); the factory
                           will fall back to single-discount behaviour in that case

        Each dict in the list contains:
          - code                    : display label (rule name + coupon code)
          - total_discounts_tax_incl
          - total_discounts_tax_excl
        """
        try:
            order_cart_rules = self._client.model('order_cart_rule').search_read(
                filters={'id_order': order_id},
            )
        except PrestaShopAPIError as e:
            if e.error_code in (400, 404):
                _logger.warning(
                    'Prestashop "%s": order_cart_rule endpoint not available (HTTP %s). '
                    'Falling back to single discount line. '
                    'Consider disabling "Add Multiple Discount Lines" for this store.',
                    self._integration_name,
                    e.error_code,
                )
                return None
            raise

        if not order_cart_rules:
            return []

        # Enrich rules with the human-readable coupon code from cart_rule resource
        cart_rule_ids = [x['id_cart_rule'] for x in order_cart_rules]
        codes = {}
        try:
            cart_rules = self._client.model('cart_rule').search_read(
                filters={'id': f'[{"|".join(map(str, cart_rule_ids))}]'},
                fields=['id', 'code'],
            )
            codes = {str(x['id']): x['code'] for x in cart_rules}
        except PrestaShopAPIError as e:
            _logger.warning(
                'Prestashop "%s": could not fetch cart_rule codes (%s). '
                'Discount lines will be named without coupon codes.',
                self._integration_name, e,
            )

        result = []
        for rule in order_cart_rules:
            code = codes.get(rule['id_cart_rule']) or ''
            label = f'{rule["name"]} - {code}' if code else rule['name']
            result.append({
                'code': label,
                'total_discounts_tax_incl': float(rule['value']),
                'total_discounts_tax_excl': float(rule['value_tax_excl']),
            })

        return result

    @staticmethod
    def _parse_customer(customer):
        vals = {
            'id': customer['id'],
            'pricelist_id': customer['id_default_group'],
            'person_name': ' '.join([customer['firstname'], customer['lastname']]),
            'email': customer['email'],
            'language': customer['id_lang'],
            'newsletter': customer['newsletter'],
            'newsletter_date_add': customer['newsletter_date_add'],
            'customer_date_add': customer['date_add'],
            'default_customer_group_id': customer['id_default_group'],
        }

        # If person_name is empty, use email as a fallback in all connectors
        if not vals['person_name']:
            vals['person_name'] = vals['email']

        return vals

    @staticmethod
    def _parse_address(customer, presta_address):
        """
        we add customer id to address id to distinguish them from each other
        """

        if not presta_address:
            return {}

        company_name = presta_address['company']
        if company_name:
            # Use DNI field instead because for some countries (like Spain) there can be NIF
            # number for company
            company_reg_number = presta_address['vat_number'] or presta_address['dni']

            # There should be no personal tax ID
            person_id_number = ''
        else:
            company_reg_number = ''
            person_id_number = presta_address['dni']

        address = {
            'id': '',
            'person_name': ' '.join([presta_address['firstname'], presta_address['lastname']]),
            'email': customer.get('email', ''),
            'person_id_number': person_id_number,
            'company_name': company_name,
            'company_reg_number': company_reg_number,
            'street': presta_address['address1'],
            'street2': presta_address['address2'],
            'city': presta_address['city'],
            'country': presta_address['id_country'],
            'state': presta_address['id_state'] if presta_address['id_state'] != IS_FALSE else '',
            'phone': presta_address['phone'] or presta_address['phone_mobile'],
            'other': presta_address['other'],
            'type': presta_address.get('type', ''),
        }

        if presta_address.get('postcode'):
            address['zip'] = presta_address['postcode']

        if customer.get('id_lang'):
            address['language'] = customer.get('id_lang')

        return address

    def _parse_order_row(self, order_id, row):
        details = self._client.model('order_detail').read_one(row['id'])
        assert details

        tax = details['associations']['taxes'].get('tax')
        if not tax:
            taxes = []
        else:
            taxes = [x['id'] for x in make_list_if_not(tax) if x['id'] != IS_FALSE]

        product_id = self._build_product_external_code(
            row['product_id'],
            row['product_attribute_id'],
        )
        return {
            'id': row['id'],
            'name': row['product_name'] or '',
            'reference': row['product_reference'] or '',
            'product_id': product_id,
            'product_uom_qty': int(row['product_quantity']),
            'price_unit': float(row['unit_price_tax_excl']),
            'price_unit_tax_incl': float(row['unit_price_tax_incl']),
            'discount': dict(),
            'taxes': taxes,
        }

    @add_dynamic_kwargs
    def export_inventory(self, inventory: dict, **kw) -> list:
        _logger.info('Prestashop "%s": export_inventory()', self._integration_name)

        integration = self._get_integration(kw)
        filter_adds = {'id_shop': IS_FALSE} if integration.shared_stock else {}

        results = []
        for product_combination_id, inventory_item_list in inventory.items():
            product_id, combination_id = self._parse_product_external_code(product_combination_id)

            # Find stock for combination
            stock = self._client.model('stock_available').search(
                filters={
                    'id_product': product_id,
                    'id_product_attribute': combination_id,
                    **filter_adds,
                },
                shop_specific=not integration.shared_stock,
            )

            if stock:
                result = []
                # There can be multiple stocks if customer has multiple shops
                # We push the same quantity to all stocks
                for stock_item in stock:
                    inventory_item = inventory_item_list[0]
                    stock_item.quantity = int(inventory_item['qty'])

                    message = ''
                    result.append(stock_item.save())
            else:
                result, message = [], 'Stock resource not found'

            results.append((product_combination_id, result, message))

        return results

    def export_tracking(self, sale_order_id, tracking_data_list, **kw):
        tracking = ', '.join(set([x['tracking'] for x in tracking_data_list]))

        order_carrier = self._client.model('order_carrier').search({
            'id_order': sale_order_id,
        })

        # TODO: check with integrational test

        order_carrier.tracking_number = tracking
        result = order_carrier.save(sendemail=1)
        return result

    def send_picking(self, sale_order_id, tracking_data, *args, **kw):
        return list()

    def send_sale_order_status(self, external_order_id: str, vals: dict):
        _logger.info('%s: send_sale_order_status()', self._integration_name)

        history_list = self._client.model('order_history').search_read(
            filters={'id_order': external_order_id},
        )
        if history_list:
            mapping = {int(x['id']): x for x in history_list}
            key = max(mapping.keys())

            if vals['status'] == mapping[key]['id_order_state']:
                _logger.info('%s: send_sale_order_status() skipped', self._integration_name)
                return False

        # 1. Update delivery date for order
        if vals.get('delivery_date'):
            order = self._client.model('order').get(external_order_id)
            order.delivery_date = vals['delivery_date']
            order.save()

        # 2. Update order status through the order history
        order_history = self._client.model('order_history')

        order_history.id_order = external_order_id
        order_history.id_order_state = vals['status']
        order_history.id_employee = vals['user_id']

        return order_history.save(sendemail=1)

    def get_product_for_import(self, external_template_id: str, id_shop=False, **kw):
        shop_filter = {'id_shop': id_shop} if id_shop else {}

        # 1. Get product
        product_dict = self._client.model('product').search_read(
            filters={'id': external_template_id},
            with_translation=True,
            **shop_filter,
        )

        if not product_dict:
            raise UserError(
                _('Product with ID "%s" does not exist in PrestaShop. Please verify the ID and try again.')
                % external_template_id
            )

        if isinstance(product_dict, list):
            product_dict = product_dict[0]

        product_option_value = product_dict \
            .get('associations', {}) \
            .get('product_option_values', {}) \
            .get('product_option_value', [])

        product_dict['_attributes'] = [x['id'] for x in make_list_if_not(product_option_value)]

        # 2. Get combinations
        variant_list = self._client.model('combination').search_read(
            filters={'id_product': external_template_id},
            **shop_filter,
        )

        # Handle a variant marked as default firstly.
        variant_list = sorted(variant_list, key=lambda x: x['default_on'], reverse=True)
        for variant in variant_list:
            attribute_value_ids = variant \
                .get('associations', {}) \
                .get('product_option_values', {}) \
                .get('product_option_value', [])

            variant['_attribute_value_ids'] = [x['id'] for x in make_list_if_not(attribute_value_ids)]

        variant_image_dict = {}
        for variant in variant_list:
            variant_image_list = variant['associations']['images'].get('image', [])
            variant_image_ids = [
                x['id'] for x in make_list_if_not(variant_image_list) if (x['id'] and x['id'] != IS_FALSE)
            ]
            variant_image_dict[variant['id']] = variant_image_ids

        # 3. Parse images
        id_default_image = product_dict['id_default_image']['value']
        image_list = product_dict['associations']['images'].get('image', [])
        template_image_ids = [
            x['id'] for x in make_list_if_not(image_list) if (x['id'] and x['id'] != IS_FALSE)
        ]

        external_images = []
        root_src = f'{self._client._api_url}images/products/{external_template_id}'

        # 3.1 Serialize template images
        for image_id in template_image_ids:
            if image_id == id_default_image or (image_id not in sum(variant_image_dict.values(), [])):
                external_images.append(
                    ExternalImage(
                        code=image_id,
                        name=image_id,
                        ttype=ProductType.PRODUCT_TEMPLATE,
                        template_code=external_template_id,
                        src=f'{root_src}/{image_id}',
                        is_cover=(image_id == id_default_image),
                        integration_id=self._integration_id,
                    ),
                )

        # 3.2 Serialize variant images
        for variant_id, image_ids in variant_image_dict.items():
            for idx, image_id in enumerate(image_ids, start=1):
                external_images.append(
                    ExternalImage(
                        code=image_id,
                        name=image_id,
                        ttype=ProductType.PRODUCT_PRODUCT,
                        template_code=external_template_id,
                        variant_code=variant_id,
                        src=f'{root_src}/{image_id}',
                        is_cover=(idx == 1),
                        integration_id=self._integration_id,
                    ),
                )

        # 4. Parse BoM components
        bom_components = []
        external_components = product_dict['associations']['product_bundle'].get('product', [])

        for component in make_list_if_not(external_components):
            bundle_product_id = component['id']

            if 'id_product_attribute' not in component:
                raise ApiImportError(_(
                    'You are using PrestaShop 1.6, which has known issues with product packs. '
                    'Please check this article for more details: '
                    'https://ventortech.atlassian.net/servicedesk/customer/portal/1/article/634487313. '
                    'Affected product: "%s", bundle product: "%s".'
                ) % (external_template_id, bundle_product_id))

            complex_code = self._build_product_external_code(
                bundle_product_id,
                component['id_product_attribute'],
            )
            bom_components.append({
                'product_id': complex_code,
                'quantity': component['quantity'],
            })

        product_dict['_variants_count'] = len(variant_list)
        return product_dict, variant_list, bom_components, external_images

    def get_image_data(self, src):
        response = self._client._execute(src, 'GET')

        if response.ok:
            return base64.b64encode(response.content)

        raise PrestaShopAPIError(response.text)

    def _get_product_fields_hook(self, fields):
        # This method exists to extend amount of fields that are retrieved
        # from Prestashop API. So additional logic can be added
        assert isinstance(fields, list), 'Expected a list of the field names'
        if 'id' not in fields:
            fields.append('id')
        return fields

    def _get_product_filter_hook(self, search_filter=None):
        # This method exists to extend filter criteria for products
        # for Prestashop API. So additional logic can be added
        kwargs = search_filter or dict()
        import_products_filter = json.loads(self.get_settings_value('import_products_filter'))
        product_filter_dict = {
            **import_products_filter,
            **kwargs,
        }
        return product_filter_dict

    def _get_combination_fields_hook(self, fields):
        # This method exists to extend amount of fields that are retrieved
        # from Prestashop API. So additional logic can be added
        fields_list = fields
        if 'id' not in fields_list:
            fields_list.append('id')
        if 'id_product' not in fields_list:
            fields_list.append('id_product')
        return fields_list

    def _filter_templates_hook(self, templates):
        # This method is a hooks that allows to additionally filter products
        # by some non-standard logic. Designed for extension in sub-classes
        return templates

    def _get_products_and_variants(self, product_fields, combination_fields, product_filter):
        # The same criteria fetch the templates (`product` resource) and their
        # variants (`combination` resource). Both resources share most field
        # names, but a template's own `id` corresponds to `id_product` on its
        # combinations - so derive the combination filter from the product one.
        product_filter = dict(product_filter or dict())
        combination_filter = dict(product_filter)
        if 'id' in combination_filter:
            combination_filter['id_product'] = combination_filter.pop('id')

        template_ids = self._client.model('product').search_read_by_blocks(
            filters=self._get_product_filter_hook(product_filter),
            fields=self._get_product_fields_hook(product_fields),
        )

        variant_ids = self._client.model('combination').search_read_by_blocks(
            filters=combination_filter,
            fields=self._get_combination_fields_hook(combination_fields),
        )

        if variant_ids and not template_ids:
            product_ids = set([x['id_product'] for x in variant_ids])
            template_ids = self._client.model('product').search_read_by_blocks(
                filters={'id': '[%s]' % '|'.join(product_ids)},
                fields=self._get_product_fields_hook(product_fields),
            )

        template_ids = self._filter_templates_hook(template_ids)

        active_template_ids = [x['id'] for x in template_ids]

        # If we were searching by some criteria we have to double check now if found combinations
        # correspond to product template search criteria (usually it is {'active': 1})
        if product_filter and variant_ids:
            tmpl_ids_filter = {'id': '[%s]' % '|'.join([x['id_product'] for x in variant_ids])}
            active_templates = self._client.model('product').search_read(
                filters=self._get_product_filter_hook(tmpl_ids_filter),
                fields=self._get_product_fields_hook(['id']),
            )
            active_templates = self._filter_templates_hook(active_templates)
            # create list of ids
            active_template_ids = [x['id'] for x in active_templates]

        variant_ids = [x for x in variant_ids if x['id_product'] in active_template_ids]

        return template_ids, variant_ids

    @add_dynamic_kwargs
    def get_templates_and_products_for_validation_test(self, product_refs=None, **kw):
        """Presta allows different references for template and its single variant."""
        _logger.info('Prestashop "%s": get_templates_and_products_for_validation_test()', self._integration_name)
        integration = self._get_integration(kw)
        TH_Class = integration.get_template_hub_class()
        return TH_Class(self.get_validation_tuples(product_refs=product_refs, **kw))

    def get_validation_tuples(self, ids=None, product_refs=None, **kw):
        """Presta allows different references for template and its single variant."""
        _logger.info('Prestashop "%s": get_validation_tuples(%s ids)',
                     self._integration_name, len(ids) if ids else 'all')
        if product_refs and not isinstance(product_refs, list):
            product_refs = [str(product_refs)]

        integration = self._get_integration(kw)

        template_reference = integration.template_reference_api_name
        variant_reference = integration.variant_reference_api_name
        template_barcode = integration.template_barcode_api_name
        variant_barcode = integration.variant_barcode_api_name

        def serialize_variant(v):
            return {
                'id': v['id'],
                'name': v['name'],
                'barcode': v.get(variant_barcode) or '',
                'ref': v.get(variant_reference) or '',
                'parent_id': v['id_product'],
                'skip_ref': False,
                'joint_namespace': False,
            }

        def serialize_template(t):
            return {
                'id': t['id'],
                'name': t['name'],
                'barcode': t.get(template_barcode) or '',
                'ref': t.get(template_reference) or '',
                'parent_id': '',
                'skip_ref': False,
                'joint_namespace': False,
            }

        product_filter = dict()
        if product_refs:
            product_filter[template_reference] = '[%s]' % '|'.join(product_refs)
        if ids:
            # Scope the fetch to a batch of template ids (background validation).
            # `_get_products_and_variants` maps this template `id` to `id_product`
            # for the combinations query.
            product_filter['id'] = '[%s]' % '|'.join(str(x) for x in ids)

        template_ids, variant_ids = self._get_products_and_variants(
            ['id', 'name', template_reference, template_barcode],
            ['id', 'id_product', variant_reference, variant_barcode],
            product_filter,
        )

        products_data = defaultdict(list)
        for tmpl in template_ids:
            products_data[tmpl['id']].append(
                serialize_template(tmpl)
            )

        for variant in variant_ids:
            tmpl_id = variant['id_product']
            variant['name'] = products_data[tmpl_id][0]['name']
            products_data[tmpl_id].append(
                serialize_variant(variant)
            )

        # If there is at least one variant, template reference is not essential.
        for product_list in products_data.values():
            if len(product_list) > 1:
                for tmpl_dict in filter(lambda x: not x['parent_id'], product_list):
                    tmpl_dict['skip_ref'] = True

        return list(itertools.chain.from_iterable(products_data.values()))

    def get_products_for_related_products_sync(self, external_codes):
        """Fetch full product data (including associations) for a specific
        set of products identified by their PS IDs.

        Uses internal sub-batches of ACCESSORIES_FETCH_BLOCK to keep the PS
        API URL within safe limits for any server configuration (Apache,
        Nginx, Cloudflare, etc.).

        Note: the PS API does not support selective fetching of the
        'associations' sub-object via display=[field,...]; it is only
        included with display=full (the default when no fields are given).
        """
        result = []
        codes = list(external_codes)
        while codes:
            id_filter = '[%s]' % '|'.join(str(code) for code in codes[:ACCESSORIES_FETCH_BLOCK])
            result.extend(
                self._client.model('product').search_read(
                    filters={'id': id_filter},
                )
            )
            codes = codes[ACCESSORIES_FETCH_BLOCK:]
        return result

    def get_stock_levels(self, *args, **kw):
        stock_available = self._client.model('stock_available').search_read_by_blocks(
            filters=None,
            fields=['id_product', 'id_product_attribute', 'quantity'],
        )

        stock_available = {
            x['id_product'] + '-' + x['id_product_attribute']: x['quantity']
            for x in stock_available
        }

        return stock_available

    def _get_url_pattern(self, wrap_li=True):
        pattern = f'<a href="{self.admin_url}/sell/catalog/products/%s" target="_blank">%s</a>'
        if wrap_li:
            return f'<li>{pattern}</li>'
        return pattern

    def _prepare_url_args(self, record):
        return ((record.parent_id or record.id), record.format_name)

    def _convert_to_html(self, id_list):
        pattern = self._get_url_pattern()
        arg_list = [self._prepare_url_args(x) for x in id_list]
        return ''.join([pattern % args for args in arg_list])

    def export_out_of_stock_option(self, data):
        """Export out of stock option to Prestashop."""
        _logger.info('Prestashop "%s": export_out_of_stock_option()', self._integration_name)
        stock_available_ids = self._client.model('stock_available').search({
            'id_product': data['external_id'],
        })
        out_of_stock = data['out_of_stock']
        for stock_available in stock_available_ids:
            stock_available.out_of_stock = out_of_stock
            stock_available.save()
        return True

    def import_out_of_stock_option(self, product_id):
        """Import out of stock option from Prestashop."""
        _logger.info('Prestashop "%s": import_out_of_stock_option()', self._integration_name)
        stock_available = self._client.model('stock_available').search_read(
            filters={'id_product': product_id},
            fields=['out_of_stock'],
        )
        out_of_stock = [x['out_of_stock'] for x in stock_available]
        return int(out_of_stock[0]) if out_of_stock else IS_FALSE

    def _parse_payment_transaction(self, payment: dict) -> dict:
        presta_currency = self._client.model('currency').search_read(
            filters={'id': payment['id_currency']},
            fields=['iso_code'],
        )
        currency = presta_currency and presta_currency[0] or dict()
        transaction = payment.get('transaction_id') or False

        return dict(
            name=f'[ID={payment["id"]}] {payment["payment_method"]}',
            kind='other',
            amount=payment['amount'],
            gateway=payment['payment_method'],
            currency=currency.get('iso_code', ''),
            external_status='success' if transaction else 'pending',
            external_str_id=str(payment['id']),
            external_process_date=payment['date_add'],
            transaction=transaction,
        )

    @staticmethod
    def _parse_product_external_code(code):
        """
        Redefined method for Presta flow.

        The external code may be formatted as:
            - (1) "100" (just template)
            - (2) "100-0" (template with the single variant)
            - (3) "100-99" (template with the one of its variants)
        """
        # A: handle the (1) case
        if '-' not in code:
            return code, None

        template_id, variant_id = code.rsplit('-', maxsplit=1)

        # B: handle the (2) case
        if variant_id == IS_FALSE:
            return template_id, None

        # C: handle the (3) case
        return template_id, variant_id

    def get_order_url(self, external_order_id):
        """
        Get the order URL for the given external order ID.
        """
        return f'{self.admin_url}/sell/orders/{external_order_id}/view'

    def get_product_url(self, external_product_code):
        """
        Get the product URL for the given external product code.
        """
        return f'{self.admin_url}/sell/catalog/products/{external_product_code}'

    def _check_active_categories(self, external_category_ids: list) -> list:
        if external_category_ids:
            external_categories = self._client.model('category').search_read(
                filters={'id': '[%s]' % '|'.join(external_category_ids),
                         'active': IS_TRUE},
                fields=['id'],
            )

            external_category_ids = [
                x['id'] for x in external_categories if x['id'] not in [IS_TRUE, IS_FALSE]
            ]

        return external_category_ids
