#  See LICENSE file for full copyright and licensing details.

from .base_model import BaseModel, PRESTASHOP
from odoo.addons.integration.tools import IS_TRUE


class ProductTag(BaseModel):
    """Prestashop product-tag (product.tag)"""

    def create(self, vals):
        tags_schema = self._client.get('tags', options={'schema': 'blank'})
        tag_data = tags_schema['tag']

        tag_data['active'] = IS_TRUE

        if isinstance(tag_data['name'], dict) and 'language' in tag_data['name']:
            BaseModel._fill_translated_field(vals['name'], tag_data['name'])
        else:
            tag_data['name'] = vals['name']

        if 'id_lang' in vals:
            tag_data['id_lang'] = str(vals['id_lang'])

        result = self._client.add('tags', tags_schema)
        return self.get(result[PRESTASHOP]['tag']['id'])
