# See LICENSE file for full copyright and licensing details.

from copy import deepcopy

from .storage import STORAGE

from ...prestashop import Client, BaseModel
from ...prestashop_api import PrestaShopApiClient
from ...prestashop.category import Category
from ...prestashop.product import Product
from ...prestashop.combination import Combination
from ...prestashop.image import Image


class PatchMixinTest:

    def read_one(self, item_id: str):
        return deepcopy(STORAGE[self._name][item_id])

    def search_read(self, filters: dict, **kw):
        if 'id' in filters:
            item_id = filters['id']
        elif 'id_product' in filters:
            item_id = filters['id_product']
        elif 'id_order' in filters:
            item_id = filters['id_order']
        elif 'order_reference' in filters:
            item_id = filters['order_reference']
        elif 'id_reference' in filters:
            item_id = filters['id_reference']
        else:
            raise NotImplementedError

        if item_id.startswith('['):
            item_id = item_id[1:-1].split('|')
        else:
            item_id = [item_id]

        result = [self.read_one(x) for x in item_id]
        if any(isinstance(x, list) for x in result):
            return sum(result, [])
        return result


class BaseModelPatchTest(PatchMixinTest, BaseModel):

    def __init__(self, *args, **kw):
        BaseModel.__init__(self, *args, **kw)


class CategoryPatchTest(PatchMixinTest, Category):

    def __init__(self, *args, **kw):
        Category.__init__(self, *args, **kw)

    def read_one(self, item_id: str):
        return super().read_one(item_id)


class ProductPatchTest(PatchMixinTest, Product):

    def __init__(self, *args, **kw):
        Product.__init__(self, *args, **kw)


class CombinationPatchTest(PatchMixinTest, Combination):

    def __init__(self, *args, **kw):
        Combination.__init__(self, *args, **kw)


class ImagePatchTest(PatchMixinTest, Image):

    def __init__(self, *args, **kw):
        Image.__init__(self, *args, **kw)


class PrestashopClientPatchTest(Client):

    classes = {
        'category': CategoryPatchTest,
        'product': ProductPatchTest,
        'combination': CombinationPatchTest,
        'image': ImagePatchTest,
    }

    def __init__(self, *args, **kw):
        self._api_url = 'https://myprestashop-test.io/api/'

    def model(self, name):
        cls = self.classes.get(name)
        if not cls:
            cls = BaseModelPatchTest

        instance = cls(
            self,
            id_group_shop=self.id_group_shop,
            shop_ids=self.shop_ids,
            default_language_id=self.default_language_id,
            data_block_size=self.data_block_size,
        )
        instance._name = name

        return instance


class PrestashopAPIClientPatchTest(PrestaShopApiClient):

    def __init__(self, settings):
        self._integration_id = None
        self._integration_name = None
        self._settings = settings

        self._client = PrestashopClientPatchTest()

        self.admin_url = 'https://myprestashop-test.io/admin/index.php'

        self._language_id = '1'
        self._weight_uom = 'kg'
        self._default_shop_id = None

        self._client.default_language_id = self._language_id
        self._client.id_group_shop = ''
        self._client.shop_ids = []
        self._client.data_block_size = 100

    def get_payment_methods(self):
        return [
            {'id': 'Bank wire'},
            {'id': 'Bank transfer'},
            {'id': 'Card via Stripe'},
            {'id': 'Payment by check'},
        ]

    def get_configuration(self, name):
        if name == 'PS_GIFT_WRAPPING_TAX_RULES_GROUP':
            return []
        raise NotImplementedError

    def _get_carrier_tax_ids(self, *args, **kw):
        return ['25'], '0'

    def _get_taxes_by_tax_rule(self, *args, **kw):
        return [], '0'

    def get_taxes(self):
        return [
            {
                'id': '100',
                'rate': '23.000',
                'name': 'PTU PL 23%',
                'tax_groups': [
                    {
                        'id': '10',
                        'name': 'PL Standard Rate (23%)',
                    },
                ],
            },
        ]

    def get_languages(self):
        return [
            {
                'id': '1',
                'name': 'Netherlands (Netherlands)',
                'external_reference': 'nl_nl',
            },
            {
                'id': '2',
                'name': 'Polski (Polish)',
                'external_reference': 'pl_pl',
            },
        ]

    def get_categories(self):
        return [
            {
                'id': '2',
                'id_parent': '0',
                'is_root_category': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1',
                            },
                            'value': 'Home-wexrwetest',
                        },
                        {
                            'attrs': {
                                'id': '2',
                            },
                            'value': 'Strona-główna-wexrwetest',
                        },
                    ],
                },
            },
            {
                'id': '6',
                'id_parent': '2',
                'is_root_category': '0',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1',
                            },
                            'value': 'Accessories-tesakjsex',
                        },
                        {
                            'attrs': {
                                'id': '2',
                            },
                            'value': 'Produkty-powiązane-tesakjsex',
                        },
                    ],
                },
            },
            {
                'id': '8',
                'id_parent': '6',
                'is_root_category': '0',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1',
                            },
                            'value': 'Home-Accessories-xwzkRtest',
                        },
                        {
                            'attrs': {
                                'id': '2',
                            },
                            'value': 'Produkty-domowe-xwzkRtest',
                        },
                    ],
                },
            },
        ]

    def get_sale_order_statuses(self):
        return [
            {
                'id': '1',
                'name': {
                    'language': {
                        'attrs': {
                            'id': '1',
                        },
                        'value': 'Awaiting check payment',
                    },
                },
                'external_reference': False,
            },
            {
                'id': '2',
                'name': {
                    'language': {
                        'attrs': {
                            'id': '1',
                        },
                        'value': 'Payment accepted',
                    },
                },
                'external_reference': False,
            },
            {
                'id': '3',
                'name': {
                    'language': {
                        'attrs': {
                            'id': '1',
                        },
                        'value': 'Processing in progress',
                    },
                },
                'external_reference': False,
            },
        ]

    def get_features(self):
        return [
            {
                'id': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1',
                            },
                            'value': 'Composition',
                        },
                        {
                            'attrs': {
                                'id': '2',
                            },
                            'value': 'Composition',
                        },
                    ],
                },
            },
            {
                'id': '2',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1',
                            },
                            'value': 'Property',
                        },
                        {
                            'attrs': {
                                'id': '2',
                            },
                            'value': 'Property',
                        },
                    ],
                },
            },
        ]

    def get_feature_values(self):
        return [
            {
                'id': '1',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Polyester',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Poliester',
                        }
                    ]
                },
                'id_group': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1',
                            },
                            'value': 'Polyester',
                        },
                        {
                            'attrs': {
                                'id': '2',
                            },
                            'value': 'Poliester',
                        }
                    ]
                }
            },
            {
                'id': '2',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Wool',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Wełna',
                        }
                    ]
                },
                'id_group': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Wool',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Wełna',
                        }
                    ]
                }
            },
            {
                'id': '3',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Ceramic',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Ceramic',
                        }
                    ]
                },
                'id_group': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Ceramic',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Ceramic',
                        }
                    ]
                }
            },
            {
                'id': '4',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Cotton',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Bawełna',
                        }
                    ]
                },
                'id_group': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Cotton',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Bawełna',
                        }
                    ]
                }
            },
            {
                'id': '5',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Recycled cardboard',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Recycled cardboard',
                        }
                    ]
                },
                'id_group': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Recycled cardboard',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Recycled cardboard',
                        }
                    ]
                }
            },
            {
                'id': '6',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Matt paper',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Matt paper',
                        }
                    ]
                },
                'id_group': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Matt paper',
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Matt paper',
                        }
                    ]
                }
            },
            {
                'id': '7',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Long sleeves'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Long sleeves'
                        }
                    ]
                },
                'id_group': '2',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Long sleeves'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Long sleeves'
                        }
                    ]
                }
            },
            {
                'id': '8',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Short sleeves'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Short sleeves'
                        }
                    ]
                },
                'id_group': '2',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Short sleeves'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Short sleeves'
                        }
                    ]
                }
            },
            {
                'id': '9',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Removable cover'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Removable cover'
                        }
                    ]
                },
                'id_group': '2',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Removable cover'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Removable cover'
                        }
                    ]
                }
            },
            {
                'id': '10',
                'value': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': '120 pages'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': '120 pages'
                        }
                    ]
                },
                'id_group': '2',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': '120 pages'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': '120 pages'
                        }
                    ]
                }
            }
        ]

    def get_attributes(self):
        return [
            {
                'id': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Sizeee'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Rozmiar'
                        }
                    ]
                }
            },
            {
                'id': '2',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Colorrr'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Kolor'
                        }
                    ]
                }
            },
            {
                'id': '3',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Dimensionnn'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Dimension'
                        }
                    ]
                }
            },
            {
                'id': '4',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Paper Typeee'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Paper Type'
                        }
                    ]
                }
            }
        ]

    def get_attribute_values(self):
        return [
            {
                'id': '1',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'S'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'S'
                        }
                    ]
                },
                'id_group': '1'
            },
            {
                'id': '2',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'M'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'M'
                        }
                    ]
                },
                'id_group': '1'
            },
            {
                'id': '3',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'L'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'L'
                        }
                    ]
                },
                'id_group': '1'
            },
            {
                'id': '4',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'XL'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'XL'
                        }
                    ]
                },
                'id_group': '1'
            },
            {
                'id': '5',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Gray'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Szary'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '6',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Taupe'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Szarobrązowy'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '7',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Beige'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Beżowy'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '8',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Whiteee'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Biały'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '9',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Off White'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Złamana biel'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '10',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Red'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Czerwony'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '11',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Blackkko'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'czarny'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '12',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Camel'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Wielbłąd'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '13',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Orange'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Pomarańczowy'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '14',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Blue'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Niebieski'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '15',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Green'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Zielony'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '16',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Yellow'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Żółty'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '17',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Brown'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Brązowy'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '18',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Pink'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Różowy'
                        }
                    ]
                },
                'id_group': '2'
            },
            {
                'id': '19',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': '40x60cm'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': '40x60cm'
                        }
                    ]
                },
                'id_group': '3'
            },
            {
                'id': '20',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': '60x90cm'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': '60x90cm'
                        }
                    ]
                },
                'id_group': '3'
            },
            {
                'id': '21',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': '80x120cm'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': '80x120cm'
                        }
                    ]
                },
                'id_group': '3'
            },
            {
                'id': '22',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Ruled'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Ruled'
                        }
                    ]
                },
                'id_group': '4'
            },
            {
                'id': '23',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Plain'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Plain'
                        }
                    ]
                },
                'id_group': '4'
            },
            {
                'id': '24',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Squarred'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Squarred'
                        }
                    ]
                },
                'id_group': '4'
            },
            {
                'id': '25',
                'name': {
                    'language': [
                        {
                            'attrs': {
                                'id': '1'
                            },
                            'value': 'Doted'
                        },
                        {
                            'attrs': {
                                'id': '2'
                            },
                            'value': 'Doted'
                        }
                    ]
                },
                'id_group': '4'
            }
        ]
