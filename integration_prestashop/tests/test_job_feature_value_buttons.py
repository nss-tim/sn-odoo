# See LICENSE file for full copyright and licensing details.

from unittest.mock import patch

from odoo.tests import tagged
from odoo.addons.integration.tests.config.integration_init import OdooIntegrationBase, load_xml


@tagged('post_install', '-at_install', 'test_integration_prestashop')
class TestJobFeatureValueButtons(OdooIntegrationBase):
    """A product import fails on a feature value that is not mapped: the buttons of the failed job must work.

    Features and their values belong to the PrestaShop module, so the core cannot know their actions.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        load_xml(
            cls.env,
            module='integration_prestashop',
            path_file='tests/data/',
            filename='init_sale_integration_prestashop.xml',
        )
        cls.integration = cls.env.ref('integration_prestashop.integration_prestashop_test_1')

    def _job(self, model_name):
        return self.env['queue.job'].new({
            'integration_id': self.integration.id,
            'integration_model_name': model_name,
        })

    def test_all_buttons_available_for_feature_value(self):
        job = self._job('integration.product.feature.value.mapping')

        self.assertEqual(job.get_model_from_integration_model_name(), 'product.feature.value')
        self.assertTrue(job.is_open_external_available)
        self.assertTrue(job.is_open_mapping_available)
        self.assertTrue(job.is_import_from_external_available)

    def test_open_buttons_open_feature_value_records(self):
        job = self._job('integration.product.feature.value.mapping')

        self.assertEqual(job.action_open_external_view()['res_model'], 'integration.product.feature.value.external')
        self.assertEqual(job.action_open_mapping_view()['res_model'], 'integration.product.feature.value.mapping')

    def test_import_runs_feature_values_import_in_foreground(self):
        job = self._job('integration.product.feature.value.mapping')

        with patch.object(type(self.integration), 'integrationApiImportFeatureValues') as import_values:
            action = job.action_import_from_external_system()

        import_values.assert_called_once_with()
        self.assertEqual(action['res_model'], 'message.wizard')

    def test_feature_buttons_work_too(self):
        job = self._job('integration.product.feature.external')

        self.assertTrue(job.is_open_external_available)
        self.assertTrue(job.is_open_mapping_available)
        self.assertTrue(job.is_import_from_external_available)

    def test_feature_value_import_is_not_offered_for_other_store(self):
        """The PrestaShop declaration must not make the button visible for the stores of other types."""
        job = self.env['queue.job'].new({
            'integration_id': self.env.ref('integration.integration_no_api_1').id,
            'integration_model_name': 'integration.product.feature.value.mapping',
        })

        self.assertFalse(job.is_import_from_external_available)
