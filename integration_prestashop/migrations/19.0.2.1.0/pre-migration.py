# See LICENSE file for full copyright and licensing details.


def migrate(cr, version):
    """
    Several window actions were moved from the `integration` module to
    `integration_prestashop`. Re-assign the ir_model_data records so Odoo
    UPDATEs the existing ir_act_window rows instead of attempting new INSERTs
    that would collide on the unique path constraint.
    """
    cr.execute("""
        UPDATE ir_model_data
           SET module = 'integration_prestashop'
         WHERE module = 'integration'
           AND model  = 'ir.actions.act_window'
           AND name   IN (
               'product_feature_action',
               'product_feature_value_action',
               'integration_product_feature_external_action',
               'integration_product_feature_value_external_action',
               'integration_product_feature_mapping_action',
               'integration_product_feature_value_mapping_action'
           )
    """)
