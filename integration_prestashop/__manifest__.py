# See LICENSE file for full copyright and licensing details.

{
    'name': 'Odoo PrestaShop Connector PRO',
    'summary': '''Export products and your current stock from Odoo to PrestaShop, and
seamlessly import orders from your PrestaShop store into Odoo. Update order status and provide
tracking numbers to your customers automatically and instantly!

This connector streamlines your e-commerce operations by automating data transfer between
PrestaShop and Odoo. Reduce manual work, eliminate errors, and improve efficiency with
real-time synchronization of products, stock levels, and orders.

Keywords: PrestaShop, PrestaShop Odoo Connector, PrestaShop Integration, Odoo PrestaShop Connector,
Sync PrestaShop with Odoo, PrestaShop Product Import, PrestaShop Product Export,
PrestaShop Inventory Sync, PrestaShop Order Import, Odoo PrestaShop Integration,
Multi-Channel Sales Management, Seamless E-commerce Integration, Odoo for PrestaShop,
Multi-Store Management, E-commerce Integration, Odoo E-commerce Solution,
Connect PrestaShop to Odoo, PrestaShop Odoo Bridge, Odoo PrestaShop Bridge''',
    'category': 'Sales',
    'version': '19.0.2.3.0',
    'images': [
        'static/description/images/banner.gif',
    ],
    'author': 'VentorTech',
    'website': 'https://ecosystem.ventor.tech/product/odoo-prestashop-connector-pro/',
    'support': 'support@ventor.tech',
    'license': 'OPL-1',
    'live_test_url': 'https://demo.ventor.tech',
    'price': 449.00,
    'currency': 'EUR',
    'depends': [
        'integration',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/product_ecommerce_fields.xml',
        'data/integration_import_entity_data.xml',
        'views/sale_integration.xml',
        'views/product_feature_views.xml',
        'views/product_feature_value_views.xml',
        'views/external/external_integration_tag_views.xml',
        'views/external/integration_res_users_external_views.xml',
        'views/external/integration_ecommerce_product_category_external_views.xml',
        'views/external/integration_customer_group_external_views.xml',
        'views/external/integration_product_feature_external_views.xml',
        'views/external/integration_product_feature_value_external_views.xml',
        'views/mappings/integration_res_users_mapping_views.xml',
        'views/mappings/integration_product_feature_mapping_views.xml',
        'views/mappings/integration_product_feature_value_mapping_views.xml',
        'views/mappings/integration_customer_group_mapping_views.xml',
        'views/mappings/integration_product_pricelist_mapping_views.xml',
        'views/product_pricelist_views.xml',
        'wizard/integration_auth_prestashop_views.xml',
        'wizard/configuration_wizard_prestashop.xml',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'views/external/menu.xml',
        'views/mappings/menu.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'application': True,
    "cloc_exclude": [
        "**/*",
    ]
}
