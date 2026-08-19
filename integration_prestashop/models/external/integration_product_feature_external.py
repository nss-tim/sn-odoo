# See LICENSE file for full copyright and licensing details.

import logging

from odoo import models, fields, _
from odoo.exceptions import UserError
from odoo.tools.sql import escape_psql

from odoo.addons.integration.models.mixins.integration_external_mixin import (
    RESULT_CREATED,
    RESULT_ALREADY_MAPPED,
    RESULT_MAPPED,
    RESULT_EXISTS,
    RESULT_NOT_IN_EXTERNAL,
)

_logger = logging.getLogger(__name__)


class IntegrationProductFeatureExternal(models.Model):
    _name = 'integration.product.feature.external'
    _inherit = 'integration.external.mixin'
    _description = 'Integration Product Feature External'
    _odoo_model = 'product.feature'
    _map_field = 'name'

    external_feature_value_ids = fields.One2many(
        comodel_name='integration.product.feature.value.external',
        inverse_name='external_feature_id',
        string='External Feature Values',
        readonly=True,
    )

    def run_import_features(self):
        return self._run_import_features()

    # -- Import of features and their values -----------------------------------
    # PrestaShop features mirror the attribute import flow, but features never
    # create product variants, so there is no Variant Creation mode handling.

    def _run_import_features(self, link_to_existing=False):
        res_element = {}
        res_values = {}

        features_by_integration = {}
        for external_feature in self:
            integration = external_feature.integration_id
            features_by_integration[integration] = \
                features_by_integration.get(integration, self.browse()) | external_feature

        for integration, external_features in features_by_integration.items():
            adapter = integration.adapter

            ext_features = adapter.get_features()
            ext_values = adapter.get_feature_values()

            features_dict = {
                external_feature.code: {
                    'ext_feature': {},
                    'ext_values': [],
                    'external_feature': external_feature,
                }
                for external_feature in external_features
            }

            for ext_feature in ext_features:
                if ext_feature['id'] in features_dict:
                    features_dict[ext_feature['id']]['ext_feature'] = ext_feature

            for ext_value in ext_values:
                if ext_value['id_group'] in features_dict:
                    features_dict[ext_value['id_group']]['ext_values'].append(ext_value)

            for item in features_dict.values():
                external_feature = item['external_feature']

                if not item['ext_feature']:
                    result = {'element': RESULT_NOT_IN_EXTERNAL, 'values': {}}
                else:
                    result = external_feature._import_feature_and_values(
                        item['ext_feature'],
                        item['ext_values'],
                        link_to_existing=link_to_existing,
                    )

                if result['element'] in (RESULT_ALREADY_MAPPED, RESULT_CREATED):
                    res_element[result['element']] = res_element.get(result['element'], 0) + 1
                else:
                    res_element[result['element']] = \
                        res_element.get(result['element'], []) + [external_feature.name]

                for code, value_result in result['values'].items():
                    res_values[code] = res_values.get(code, 0) + value_result

        return self._build_import_elements_action(_('Feature'), res_element, res_values)

    def _import_feature_and_values(self, ext_feature, ext_values, link_to_existing=False):
        self.ensure_one()

        result = {
            'element': 0,
            'values': {RESULT_ALREADY_MAPPED: 0, RESULT_MAPPED: 0, RESULT_CREATED: 0},
        }

        Mapping = self.env['integration.product.feature.mapping']
        MappingValue = self.env['integration.product.feature.value.mapping']
        ExternalValue = self.env['integration.product.feature.value.external']

        # Important! These models carry the integration language for the searches below.
        context_lang_code = self.integration_id.get_integration_lang_code()
        ProductFeature = self.env['product.feature'].with_context(lang=context_lang_code)
        ProductFeatureValue = self.env['product.feature.value'].with_context(lang=context_lang_code)

        feature_mapping = Mapping.get_mapping(self.integration_id, self.code)
        odoo_feature = feature_mapping.feature_id if feature_mapping else None

        matched_feature = ProductFeature.search([('name', '=ilike', escape_psql(self.name))])

        if matched_feature and not odoo_feature and not link_to_existing:
            result['element'] = RESULT_EXISTS
            return result

        if len(matched_feature) > 1 and not odoo_feature:
            raise UserError(_(
                'Multiple Odoo Feature records share the name "%s" (IDs: %s). '
                'Please ensure each Feature name is unique in Odoo before running the import, '
                'or manually create the mapping in the integration settings.'
            ) % (
                self.name,
                ', '.join(str(record.id) for record in matched_feature),
            ))

        if odoo_feature:
            result['element'] = RESULT_ALREADY_MAPPED
        else:
            name = self.env['integration.res.lang.mapping'] \
                .convert_external_translations(self.integration_id.id, ext_feature['name'])

            odoo_feature = self.create_or_update_with_translations(
                self.integration_id.id,
                matched_feature,
                {'name': name},
            )

            self.create_or_update_mapping(odoo_id=odoo_feature.id)

            existing_mappings = Mapping.search([
                ('integration_id', '=', self.integration_id.id),
                ('feature_id', '=', odoo_feature.id),
            ])
            if len(existing_mappings) > 1:
                _logger.warning(
                    'Multiple external feature records mapped to the same Odoo feature '
                    '"%s" (id=%s) for integration "%s". External codes: %s.',
                    odoo_feature.name, odoo_feature.id, self.integration_id.name,
                    [mapping.external_feature_id.code for mapping in existing_mappings],
                )

            result['element'] = RESULT_CREATED

        for ext_value in ext_values:
            value_mapping = MappingValue.get_mapping(self.integration_id, ext_value['id'])
            if value_mapping and value_mapping.feature_value_id:
                result['values'][RESULT_ALREADY_MAPPED] += 1
                continue

            name = ext_value['name']
            if isinstance(name, dict) and name.get('language'):
                name = self.get_original_name(name)

            feature_value = ProductFeatureValue.search([
                ('feature_id', '=', odoo_feature.id),
                ('name', '=ilike', escape_psql(name)),
            ])

            if feature_value:
                result['values'][RESULT_MAPPED] += 1
            else:
                name = self.env['integration.res.lang.mapping'] \
                    .convert_external_translations(self.integration_id.id, ext_value['name'])

                feature_value = self.create_or_update_with_translations(
                    self.integration_id.id,
                    ProductFeatureValue,
                    {
                        'name': name,
                        'sequence': odoo_feature._get_next_sequence(),
                        'feature_id': odoo_feature.id,
                    },
                )
                result['values'][RESULT_CREATED] += 1

            external_value = ExternalValue.get_external_by_code(
                self.integration_id,
                ext_value['id'],
                raise_error=False,
            )
            if not external_value:
                external_value = ExternalValue.create({
                    'code': ext_value['id'],
                    'name': feature_value.name,
                    'integration_id': self.integration_id.id,
                })

            external_value.create_or_update_mapping(odoo_id=feature_value.id)

        return result
