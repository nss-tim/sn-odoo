# See LICENSE file for full copyright and licensing details.
# flake8: noqa
# pylint: skip-file

import json


STORAGE_STR = """
{
    "order": {
        "100501": {
            "id": "100501",
            "id_address_delivery": "6",
            "id_address_invoice": "6",
            "id_cart": "15",
            "id_currency": "1",
            "id_lang": "1",
            "id_customer": "3",
            "id_carrier": "10",
            "current_state": "3",
            "module": "ps_wirepayment",
            "invoice_number": "7",
            "invoice_date": "2024-10-17 10:58:48",
            "delivery_number": "6",
            "delivery_date": "2024-10-17 10:58:48",
            "valid": "1",
            "date_add": "2024-10-17 10:58:48",
            "date_upd": "2024-10-17 10:58:48",
            "shipping_number": {
                "attrs": {
                    "notFilterable": "true"
                },
                "value": ""
            },
            "note": "",
            "id_shop_group": "1",
            "id_shop": "1",
            "secure_key": "eac343d8d432c4f154e105acce203252",
            "payment": "Bank transfer",
            "recyclable": "0",
            "gift": "0",
            "gift_message": "",
            "mobile_theme": "0",
            "total_discounts": "66.550000",
            "total_discounts_tax_incl": "66.550000",
            "total_discounts_tax_excl": "55.000000",
            "total_paid": "1435.060000",
            "total_paid_tax_incl": "1435.060000",
            "total_paid_tax_excl": "1186.000000",
            "total_paid_real": "1435.060000",
            "total_products": "1234.000000",
            "total_products_wt": "1493.140000",
            "total_shipping": "8.470000",
            "total_shipping_tax_incl": "8.470000",
            "total_shipping_tax_excl": "7.000000",
            "carrier_tax_rate": "21.000",
            "total_wrapping": "0.000000",
            "total_wrapping_tax_incl": "0.000000",
            "total_wrapping_tax_excl": "0.000000",
            "round_mode": "2",
            "round_type": "2",
            "conversion_rate": "1.000000",
            "reference": "QIUZKILRV",
            "associations": {
                "order_rows": {
                    "attrs": {
                        "nodeType": "order_row",
                        "virtualEntity": "true"
                    },
                    "order_row": [
                        {
                            "id": "16",
                            "product_id": "9154587918001",
                            "product_attribute_id": "0",
                            "product_quantity": "2",
                            "product_name": "Guitar Pro3",
                            "product_reference": "gtp3-ref-1-prestashop-test",
                            "product_ean13": "",
                            "product_isbn": "",
                            "product_upc": "",
                            "product_price": "131.000000",
                            "id_customization": "0",
                            "unit_price_tax_incl": "158.510000",
                            "unit_price_tax_excl": "131.000000"
                        },
                        {
                            "id": "17",
                            "product_id": "8991067530001",
                            "product_attribute_id": "0",
                            "product_quantity": "3",
                            "product_name": "Guitar1",
                            "product_reference": "guit1-sku-bl-prestashop-test",
                            "product_ean13": "",
                            "product_isbn": "",
                            "product_upc": "",
                            "product_price": "324.000000",
                            "id_customization": "0",
                            "unit_price_tax_incl": "392.040000",
                            "unit_price_tax_excl": "324.000000"
                        }
                    ]
                }
            }
        }
    },
    "customer": {
        "3": {
            "id": "3",
            "id_default_group": "3",
            "id_lang": "1",
            "newsletter_date_add": "0000-00-00 00:00:00",
            "ip_registration_newsletter": "",
            "last_passwd_gen": "2021-03-23 06:03:05",
            "secure_key": "eac343d8d432c4f154e105acce203252",
            "deleted": "0",
            "passwd": "$2y$10$mEYsgDu0wvoC7MwyCSsLd.LMMg7an/NoszYD1GHzjo4I6.l2B8Mzi",
            "lastname": "Customer",
            "firstname": "TestPresta",
            "email": "test_prestashop_nl@prestashop.com",
            "id_gender": "1",
            "birthday": "1985-10-22",
            "newsletter": "0",
            "optin": "0",
            "website": "",
            "company": "",
            "siret": "",
            "ape": "",
            "outstanding_allow_amount": "0.000000",
            "show_public_prices": "0",
            "id_risk": "0",
            "max_payment_days": "0",
            "active": "1",
            "note": "",
            "is_guest": "0",
            "id_shop": "1",
            "id_shop_group": "1",
            "date_add": "2021-03-23 12:03:05",
            "date_upd": "2021-03-23 17:37:32",
            "reset_password_token": "",
            "reset_password_validity": "0000-00-00 00:00:00",
            "associations": {
                "groups": {
                    "attrs": {
                        "nodeType": "group",
                        "api": "groups"
                    },
                    "group": {
                        "id": "3"
                    }
                }
            }
        }
    },
    "address": {
        "6": {
            "id": "6",
            "id_customer": "3",
            "id_manufacturer": "0",
            "id_supplier": "0",
            "id_warehouse": "0",
            "id_country": "13",
            "id_state": "0",
            "alias": "NL Address",
            "company": "",
            "lastname": "Customer",
            "firstname": "TestPresta",
            "vat_number": "",
            "address1": "Buitenruststraat 117",
            "address2": "",
            "postcode": "4337 EL",
            "city": "Middelburg",
            "other": "",
            "phone": "1000034563",
            "phone_mobile": "1100034563",
            "dni": "",
            "deleted": "0",
            "date_add": "2021-03-23 12:16:39",
            "date_upd": "2021-03-23 12:23:42"
        }
    },
    "message": {
        "100501": [
            {
                "id": "7",
                "id_cart": "15",
                "id_order": "100501",
                "id_customer": "3",
                "id_employee": "0",
                "message": "Manual order -- Employee: V. Tech",
                "private": "1",
                "date_add": "2024-10-17 10:58:48"
            }
        ]
    },
    "order_payment": {
        "QIUZKILRV": []
    },
    "currency": {
        "1": [{"iso_code": "EUR"}]
    },
    "order_detail": {
        "16": {
            "associations": {
                "taxes": {
                    "attrs": {
                        "api": "taxes",
                        "nodeType": "tax"
                    },
                    "tax": {
                        "id": "25"
                    }
                }
            },
            "discount_quantity_applied": "0",
            "download_deadline": "0000-00-00 00:00:00",
            "download_hash": "",
            "download_nb": "0",
            "ecotax": "0.000000",
            "ecotax_tax_rate": "0.000",
            "group_reduction": "0.00",
            "id": "16",
            "id_customization": "0",
            "id_order": "12",
            "id_order_invoice": "7",
            "id_shop": "1",
            "id_tax_rules_group": "6",
            "id_warehouse": "0",
            "original_product_price": "131.000000",
            "original_wholesale_price": "0.000000",
            "product_attribute_id": "0",
            "product_ean13": "",
            "product_id": "68",
            "product_isbn": "",
            "product_mpn": "",
            "product_name": "Guitar Pro3",
            "product_price": "131.000000",
            "product_quantity": "2",
            "product_quantity_discount": "0.000000",
            "product_quantity_in_stock": "2",
            "product_quantity_refunded": "0",
            "product_quantity_reinjected": "0",
            "product_quantity_return": "0",
            "product_reference": "gtp3-ref-1-presta-test",
            "product_supplier_reference": "",
            "product_upc": "",
            "product_weight": "0.000000",
            "purchase_supplier_price": "0.000000",
            "reduction_amount": "0.000000",
            "reduction_amount_tax_excl": "0.000000",
            "reduction_amount_tax_incl": "0.000000",
            "reduction_percent": "0.00",
            "tax_computation_method": "0",
            "total_price_tax_excl": "262.000000",
            "total_price_tax_incl": "317.020000",
            "total_refunded_tax_excl": "0.000000",
            "total_refunded_tax_incl": "0.000000",
            "total_shipping_price_tax_excl": "0.000000",
            "total_shipping_price_tax_incl": "0.000000",
            "unit_price_tax_excl": "131.000000",
            "unit_price_tax_incl": "158.510000"
        },
        "17": {
            "associations": {
                "taxes": {
                    "attrs": {
                        "api": "taxes",
                        "nodeType": "tax"
                    },
                    "tax": {
                        "id": "25"
                    }
                }
            },
            "discount_quantity_applied": "0",
            "download_deadline": "0000-00-00 00:00:00",
            "download_hash": "",
            "download_nb": "0",
            "ecotax": "0.000000",
            "ecotax_tax_rate": "0.000",
            "group_reduction": "0.00",
            "id": "17",
            "id_customization": "0",
            "id_order": "12",
            "id_order_invoice": "7",
            "id_shop": "1",
            "id_tax_rules_group": "6",
            "id_warehouse": "0",
            "original_product_price": "324.000000",
            "original_wholesale_price": "0.000000",
            "product_attribute_id": "0",
            "product_ean13": "",
            "product_id": "69",
            "product_isbn": "",
            "product_mpn": "",
            "product_name": "Guitar1",
            "product_price": "324.000000",
            "product_quantity": "3",
            "product_quantity_discount": "0.000000",
            "product_quantity_in_stock": "3",
            "product_quantity_refunded": "0",
            "product_quantity_reinjected": "0",
            "product_quantity_return": "0",
            "product_reference": "guit1-sku-bl-presta-test",
            "product_supplier_reference": "",
            "product_upc": "",
            "product_weight": "0.000000",
            "purchase_supplier_price": "0.000000",
            "reduction_amount": "0.000000",
            "reduction_amount_tax_excl": "0.000000",
            "reduction_amount_tax_incl": "0.000000",
            "reduction_percent": "0.00",
            "tax_computation_method": "0",
            "total_price_tax_excl": "972.000000",
            "total_price_tax_incl": "1176.120000",
            "total_refunded_tax_excl": "0.000000",
            "total_refunded_tax_incl": "0.000000",
            "total_shipping_price_tax_excl": "0.000000",
            "total_shipping_price_tax_incl": "0.000000",
            "unit_price_tax_excl": "324.000000",
            "unit_price_tax_incl": "392.040000"
        }
    },
    "carrier": {
        "10": {
            "id": "10",
            "name": "My carrier Prestashop Test",
            "id_reference": "10"
        }
    },
    "product": {
        "9100500": {
            "id": "9100500",
            "id_manufacturer": "1",
            "id_supplier": "2",
            "id_category_default": "8",
            "new": "",
            "cache_default_attribute": "22",
            "id_default_image": {
                "attrs": {
                    "notFilterable": "true"
                },
                "value": "9"
            },
            "id_default_combination": {
                "attrs": {
                    "notFilterable": "true"
                },
                "value": "22100500"
            },
            "id_tax_rules_group": "10",
            "position_in_category": {
                "attrs": {
                    "notFilterable": "true"
                },
                "value": "4"
            },
            "manufacturer_name": {
                "attrs": {
                    "notFilterable": "true"
                },
                "value": "Studio Design"
            },
            "quantity": {
                "attrs": {
                    "notFilterable": "true"
                },
                "value": "0"
            },
            "type": {
                "attrs": {
                    "notFilterable": "true"
                },
                "value": "simple"
            },
            "id_shop_default": "1",
            "reference": "demo_15_jqhxz3_test_main",
            "supplier_reference": "",
            "location": "",
            "width": "0.000000",
            "height": "0.000000",
            "depth": "0.000000",
            "weight": "0.300000",
            "quantity_discount": "0",
            "ean13": "432432432432",
            "isbn": "",
            "upc": "",
            "mpn": "",
            "cache_is_pack": "0",
            "cache_has_attachments": "0",
            "is_virtual": "0",
            "state": "1",
            "additional_delivery_times": "1",
            "delivery_in_stock": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": ""
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": ""
                    }
                ]
            },
            "delivery_out_stock": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": ""
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": ""
                    }
                ]
            },
            "product_type": "combinations",
            "on_sale": "0",
            "online_only": "0",
            "ecotax": "0.000000",
            "minimal_quantity": "1",
            "low_stock_threshold": "",
            "low_stock_alert": "0",
            "price": "18.900000",
            "wholesale_price": "0.000000",
            "unity": "",
            "unit_price_ratio": "0.000000",
            "additional_shipping_cost": "0.000000",
            "customizable": "0",
            "text_fields": "0",
            "uploadable_files": "0",
            "active": "1",
            "redirect_type": "301-category",
            "id_type_redirected": "0",
            "available_for_order": "1",
            "available_date": "0000-00-00",
            "show_condition": "0",
            "condition": "new",
            "show_price": "1",
            "indexed": "1",
            "visibility": "both",
            "advanced_stock_management": "0",
            "date_add": "2025-10-08 15:59:30",
            "date_upd": "2025-10-08 15:59:30",
            "pack_stock_type": "3",
            "meta_description": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": ""
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": ""
                    }
                ]
            },
            "meta_keywords": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": ""
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": ""
                    }
                ]
            },
            "meta_title": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": ""
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": ""
                    }
                ]
            },
            "link_rewrite": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": "mountain-fox-cushion-nl"
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": "mountain-fox-cushion-pl"
                    }
                ]
            },
            "name": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": "Mountain fox cushion kjhz2n31_test-nl"
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": "Mountain fox cushion kjhz2n31_test-pl"
                    }
                ]
            },
            "description": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": "<p>The mountain fox cushion will add a graphic and colorful touch to your sofa, armchair or bed. Create a modern and zen atmosphere that inspires relaxation. Cover 100% cotton, machine washable at 60° / Filling 100% hypoallergenic polyester NL.</p>"
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": "<p>The mountain fox cushion will add a graphic and colorful touch to your sofa, armchair or bed. Create a modern and zen atmosphere that inspires relaxation. Cover 100% cotton, machine washable at 60° / Filling 100% hypoallergenic polyester PL.</p>"
                    }
                ]
            },
            "description_short": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": "<p>Cushion with removable cover and invisible zip on the back. 32x32cm NL.</p>"
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": "<p>Cushion with removable cover and invisible zip on the back. 32x32cm PL.</p>"
                    }
                ]
            },
            "available_now": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": ""
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": ""
                    }
                ]
            },
            "available_later": {
                "language": [
                    {
                        "attrs": {
                            "id": "1"
                        },
                        "value": ""
                    },
                    {
                        "attrs": {
                            "id": "2"
                        },
                        "value": ""
                    }
                ]
            },
            "associations": {
                "categories": {
                    "attrs": {
                        "nodeType": "category",
                        "api": "categories"
                    },
                    "category": [
                        {
                            "id": "2"
                        },
                        {
                            "id": "6"
                        },
                        {
                            "id": "8"
                        }
                    ]
                },
                "images": {
                    "attrs": {
                        "nodeType": "image",
                        "api": "images"
                    },
                    "image": [
                        {
                            "id": "9"
                        },
                        {
                            "id": "10"
                        }
                    ]
                },
                "combinations": {
                    "attrs": {
                        "nodeType": "combination",
                        "api": "combinations"
                    },
                    "combination": [
                        {
                            "id": "23100500"
                        },
                        {
                            "id": "22100500"
                        }
                    ]
                },
                "product_option_values": {
                    "attrs": {
                        "nodeType": "product_option_value",
                        "api": "product_option_values"
                    },
                    "product_option_value": [
                        {
                            "id": "11"
                        },
                        {
                            "id": "8"
                        }
                    ]
                },
                "product_features": {
                    "attrs": {
                        "nodeType": "product_feature",
                        "api": "product_features"
                    },
                    "product_feature": [
                        {
                            "id": "1",
                            "id_feature_value": "1"
                        },
                        {
                            "id": "2",
                            "id_feature_value": "9"
                        }
                    ]
                },
                "tags": {
                    "attrs": {
                        "nodeType": "tag",
                        "api": "tags"
                    },
                    "value": ""
                },
                "stock_availables": {
                    "attrs": {
                        "nodeType": "stock_available",
                        "api": "stock_availables"
                    },
                    "stock_available": [
                        {
                            "id": "9100500",
                            "id_product_attribute": "0"
                        },
                        {
                            "id": "41",
                            "id_product_attribute": "22100500"
                        },
                        {
                            "id": "42",
                            "id_product_attribute": "23100500"
                        }
                    ]
                },
                "attachments": {
                    "attrs": {
                        "nodeType": "attachment",
                        "api": "attachments"
                    },
                    "value": ""
                },
                "accessories": {
                    "attrs": {
                        "nodeType": "product",
                        "api": "products"
                    },
                    "value": ""
                },
                "product_bundle": {
                    "attrs": {
                        "nodeType": "product",
                        "api": "products"
                    },
                    "value": ""
                }
            },
            "_attributes": [
                "11",
                "8"
            ]
        }
    },
    "combination": {
        "9100500": [
            {
                "id": "22100500",
                "id_product": "9100500",
                "location": "",
                "ean13": "432432432433",
                "isbn": "",
                "upc": "",
                "mpn": "",
                "quantity": "300",
                "reference": "demo_15_jqhxz3_test_main_22",
                "supplier_reference": "",
                "wholesale_price": "0.000000",
                "price": "0.000000",
                "ecotax": "0.000000",
                "weight": "0.000000",
                "unit_price_impact": "0.000000",
                "minimal_quantity": "1",
                "low_stock_threshold": "",
                "low_stock_alert": "0",
                "default_on": "1",
                "available_date": "0000-00-00",
                "associations": {
                    "product_option_values": {
                        "attrs": {
                            "nodeType": "product_option_value",
                            "api": "product_option_values"
                        },
                        "product_option_value": {
                            "id": "8"
                        }
                    },
                    "images": {
                        "attrs": {
                            "nodeType": "image",
                            "api": "images/products"
                        },
                        "image": {
                            "id": "10"
                        }
                    }
                },
                "_attribute_value_ids": [
                    "8"
                ]
            },
            {
                "id": "23100500",
                "id_product": "9100500",
                "location": "",
                "ean13": "432432432434",
                "isbn": "",
                "upc": "",
                "mpn": "",
                "quantity": "300",
                "reference": "demo_15_jqhxz3_test_main_23",
                "supplier_reference": "",
                "wholesale_price": "0.000000",
                "price": "0.000000",
                "ecotax": "0.000000",
                "weight": "0.000000",
                "unit_price_impact": "0.000000",
                "minimal_quantity": "1",
                "low_stock_threshold": "",
                "low_stock_alert": "0",
                "default_on": "",
                "available_date": "0000-00-00",
                "associations": {
                    "product_option_values": {
                        "attrs": {
                            "nodeType": "product_option_value",
                            "api": "product_option_values"
                        },
                        "product_option_value": {
                            "id": "11"
                        }
                    },
                    "images": {
                        "attrs": {
                            "nodeType": "image",
                            "api": "images/products"
                        },
                        "image": {
                            "id": "9"
                        }
                    }
                },
                "_attribute_value_ids": [
                    "11"
                ]
            }
        ]
    },
    "category": {
        "2": {"id": "2"},
        "6": {"id": "6"},
        "8": {"id": "8"}
    },
    "order_cart_rule": {
        "100501": []
    }
}
"""


STORAGE = json.loads(STORAGE_STR)
