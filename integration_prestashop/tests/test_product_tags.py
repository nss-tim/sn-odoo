# See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.addons.integration.tests.config.integration_init import OdooIntegrationBase, load_xml


class TestProductTagsCommon(OdooIntegrationBase):

    @classmethod
    def setUpClass(cls):
        super(TestProductTagsCommon, cls).setUpClass()

        # Load data
        load_xml(
            cls.env,
            module='integration_prestashop',
            path_file='tests/data/',
            filename='init_sale_integration_prestashop.xml',
        )

        # Activate Dutch language (nl_NL) for tests
        lang_nl = cls.env.ref('base.lang_nl')
        if not lang_nl.active:
            wizard_vals = dict(lang_ids=[(6, 0, [lang_nl.id])])
            wizard = cls.env['base.language.install'].create(wizard_vals)
            wizard.lang_install()

        # Get integration
        cls.integration = cls.env.ref('integration_prestashop.integration_prestashop_test_1')
        cls.Tag = cls.env['external.integration.tag']

        # Get external language for tests
        cls.external_lang_nl = cls.env.ref('integration_prestashop.integration_prestashop_res_lang_external_nl')


@tagged('post_install', '-at_install')
class TestProductTags(TestProductTagsCommon):

    def test_get_or_create_external_tag_basic(self):
        """Test that _get_or_create_external_tag correctly creates and retrieves tags."""
        language_code = self.external_lang_nl.code

        tag1 = self.Tag._get_or_create_external_tag(
            name='Test Tag',
            ttype='product',
            integration_id=self.integration.id,
            external_language_code=language_code,
        )

        self.assertEqual(tag1.name, 'Test Tag')
        self.assertEqual(tag1.ttype, 'product')
        self.assertEqual(tag1.integration_id.id, self.integration.id)
        self.assertEqual(tag1.external_language_id.id, self.external_lang_nl.id)

        # Try to get the same tag - should return existing
        tag2 = self.Tag._get_or_create_external_tag(
            name='Test Tag',
            ttype='product',
            integration_id=self.integration.id,
            external_language_code=language_code,
        )

        self.assertEqual(tag1.id, tag2.id, 'Should return the same tag when name, ttype, integration, language match')

        # Create a tag with same name but different type - should create new tag
        tag3 = self.Tag._get_or_create_external_tag(
            name='Test Tag',
            ttype='order',
            integration_id=self.integration.id,
            external_language_code=language_code,
        )

        self.assertNotEqual(tag1.id, tag3.id, 'Should create a new tag when ttype is different')
        self.assertEqual(tag3.ttype, 'order')
        self.assertEqual(tag3.name, 'Test Tag')

    def test_get_or_create_external_tag_without_language_code(self):
        """Test that _get_or_create_external_tag works without external_language_code."""
        tag = self.Tag._get_or_create_external_tag(
            name='Test Tag',
            ttype='product',
            integration_id=self.integration.id,
        )

        self.assertEqual(tag.name, 'Test Tag')
        self.assertEqual(tag.ttype, 'product')
        self.assertEqual(tag.integration_id.id, self.integration.id)
        self.assertFalse(tag.external_language_id)

    def test_get_or_create_external_tag_different_integrations(self):
        """Test that tags are scoped by integration_id."""
        language_code = self.external_lang_nl.code
        integration2 = self.integration.copy({'name': 'Test Integration 2'})

        # Create external language for integration2
        self.env['integration.res.lang.external'].create({
            'code': self.external_lang_nl.code,
            'name': self.external_lang_nl.name,
            'external_reference': self.external_lang_nl.external_reference,
            'integration_id': integration2.id,
        })

        tag1 = self.Tag._get_or_create_external_tag(
            name='Shared Tag Name',
            ttype='product',
            integration_id=self.integration.id,
            external_language_code=language_code,
        )

        tag2 = self.Tag._get_or_create_external_tag(
            name='Shared Tag Name',
            ttype='product',
            integration_id=integration2.id,
            external_language_code=language_code,
        )

        self.assertNotEqual(tag1.id, tag2.id, 'Different integrations should have separate tags')
        self.assertEqual(tag1.name, tag2.name)
        self.assertEqual(tag1.ttype, tag2.ttype)

    def test_send_product_tags_no_tags(self):
        """Test export script with no tags."""
        product = self.env['product.template'].create({
            'name': 'Test Product',
        })

        # Get the tags field mapping
        field = self.env.ref('integration_prestashop.prestashop_ecommerce_field_product_tags')

        # Test export with no tags
        result = field.calculate_export_value(self.integration.id, product.id)

        self.assertIn('tags', result)
        self.assertEqual(result['tags'], [])

    def test_send_product_tags_without_language(self):
        """Test export script with tags that have no language."""
        # Create a product template
        product = self.env['product.template'].create({
            'name': 'Test Product',
        })

        # Create tag without language
        tag = self.Tag.create({
            'name': 'Tag Without Language',
            'ttype': 'product',
            'integration_id': self.integration.id,
        })

        # Create tag group without language
        self.env['product.template.external.tag.group'].create({
            'product_tmpl_id': product.id,
            'integration_id': self.integration.id,
            'tag_ids': [(6, 0, [tag.id])],
        })

        # Get the tags field mapping
        field = self.env.ref('integration_prestashop.prestashop_ecommerce_field_product_tags')

        # Test export with tag without language
        result = field.calculate_export_value(self.integration.id, product.id)

        self.assertIn('tags', result)
        self.assertEqual(len(result['tags']), 1)
        self.assertEqual(result['tags'][0]['name'], 'Tag Without Language')
        # When no language, external_language_id.code should be False/empty
        self.assertFalse(result['tags'][0].get('language'))

    def test_send_product_tags_with_language(self):
        """Test export script with tags that have language."""
        # Create a product template
        product = self.env['product.template'].create({
            'name': 'Test Product',
        })

        # Create tag with language
        tag = self.Tag.create({
            'name': 'Tag With Language',
            'ttype': 'product',
            'integration_id': self.integration.id,
            'external_language_id': self.external_lang_nl.id,
        })

        # Create tag group with language
        self.env['product.template.external.tag.group'].create({
            'product_tmpl_id': product.id,
            'integration_id': self.integration.id,
            'external_language_id': self.external_lang_nl.id,
            'tag_ids': [(6, 0, [tag.id])],
        })

        # Get the tags field mapping
        field = self.env.ref('integration_prestashop.prestashop_ecommerce_field_product_tags')

        # Test export with tag with language
        result = field.calculate_export_value(self.integration.id, product.id)

        self.assertIn('tags', result)
        self.assertEqual(len(result['tags']), 1)
        self.assertEqual(result['tags'][0]['name'], 'Tag With Language')
        # Language code should match external_language_id.code
        self.assertEqual(result['tags'][0]['language'], self.external_lang_nl.code)

    def test_send_product_tags_multiple_tags(self):
        """Test export script with multiple tags."""
        # Create a product template
        product = self.env['product.template'].create({
            'name': 'Test Product',
        })

        TagGroup = self.env['product.template.external.tag.group']

        # Create tag without language
        tag1 = self.Tag.create({
            'name': 'Tag 1',
            'ttype': 'product',
            'integration_id': self.integration.id,
        })

        # Create tag group without language
        TagGroup.create({
            'product_tmpl_id': product.id,
            'integration_id': self.integration.id,
            'tag_ids': [(6, 0, [tag1.id])],
        })

        # Create tag with language
        tag2 = self.Tag.create({
            'name': 'Tag 2',
            'ttype': 'product',
            'integration_id': self.integration.id,
            'external_language_id': self.external_lang_nl.id,
        })

        # Create tag group with language
        TagGroup.create({
            'product_tmpl_id': product.id,
            'integration_id': self.integration.id,
            'external_language_id': self.external_lang_nl.id,
            'tag_ids': [(6, 0, [tag2.id])],
        })

        # Get the tags field mapping
        field = self.env.ref('integration_prestashop.prestashop_ecommerce_field_product_tags')

        # Test export with multiple tags
        result = field.calculate_export_value(self.integration.id, product.id)

        self.assertIn('tags', result)
        self.assertEqual(len(result['tags']), 2)

        # Check first tag (no language)
        tag1_data = next((t for t in result['tags'] if t['name'] == 'Tag 1'), None)
        self.assertIsNotNone(tag1_data, 'Tag 1 should be found in result tags')
        self.assertFalse(tag1_data.get('language'))

        # Check second tag (with language)
        tag2_data = next((t for t in result['tags'] if t['name'] == 'Tag 2'), None)
        self.assertIsNotNone(tag2_data, 'Tag 2 should be found in result tags')
        self.assertEqual(tag2_data['language'], self.external_lang_nl.code)
