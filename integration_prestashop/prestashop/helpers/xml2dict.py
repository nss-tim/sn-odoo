import re
import xml.etree.ElementTree as ET

from typing import Any, Dict, Union


# Regular expression to match a namespace in an XML tag
NAMESPACE_REGEX = re.compile(r'\{(.*) \}(.*)')


class Xml2Dict:
    """
    A class for converting XML data to a dictionary.

    This class encapsulates the functionality of parsing XML using Python's
    ElementTree and converting it into a nested dictionary. Tags with namespaces
    are handled by extracting the namespace and including it in the dictionary.
    """

    @classmethod
    def _create_xml_mapping(cls, key: str, value: Any) -> Dict[str, Any]:
        """
        Build a dictionary entry mapping an XML key to a value.

        If the key is in the form '{namespace}name', the namespace is extracted
        and included in the value as a dictionary with keys 'value' and 'xmlns'.

        :param key: The XML key (tag or attribute name, possibly with a namespace).
        :param value: The value associated with the key.
        :return: A dictionary {name: value} (with namespace information if applicable).
        """
        mapping_value = value

        result = NAMESPACE_REGEX.search(key)
        if result:
            namespace, key = result.groups()
            mapping_value = {'value': value, 'xmlns': namespace}

        return {key: mapping_value}

    @classmethod
    def _element_to_dict(cls, node: ET.Element) -> Union[str, Dict[str, Any]]:
        """
        Recursively convert an ElementTree node into a dictionary.

        :param node: An ElementTree node.
        :return: A dictionary representing the node, or a string if only a text value exists.
        """
        element_dict = {}
        attributes = {}

        # Process attributes, skipping the xlink:href attribute.
        for attr_key, attr_value in node.attrib.items():
            if attr_key == '{http://www.w3.org/1999/xlink}href':
                continue

            attributes.update(cls._create_xml_mapping(attr_key, attr_value))

        text_value = node.text.strip() if node.text is not None else ''

        if attributes:
            element_dict['attrs'] = attributes

        children = list(node)
        has_child = bool(children)

        for child in children:
            child_tag = child.tag
            child_data = cls._element_to_dict(child)
            child_mapping = cls._create_xml_mapping(child_tag, child_data)

            # If the child node produced a non-empty structure, ignore the current node text
            if child_data:
                text_value = ''

            if child_tag not in element_dict:
                # First occurrence of this tag
                element_dict.update(child_mapping)
                continue

            # Multiple occurrences of the same tag: ensure the value is a list
            current_value = element_dict[child_tag]
            if not isinstance(current_value, list):
                element_dict[child_tag] = [current_value]

            element_dict[child_tag].append(child_data)

        if not has_child:
            element_dict['value'] = text_value

        # If the only key is 'value', return the text directly
        if len(element_dict) == 1 and 'value' in element_dict:
            return element_dict['value']

        return element_dict

    @classmethod
    def from_xml(cls, xml_input: Union[ET.Element, str]) -> Dict[str, Any]:
        """
        Convert an XML input to a dictionary. The input can be either an XML string
        or an ElementTree element.

        :param xml_input: XML input as a string or an ElementTree element.
        :return: A dictionary representation of the XML.
        :raises TypeError: If xml_input is neither a string nor an ElementTree.Element.
        """
        if not isinstance(xml_input, (ET.Element, str)):
            raise TypeError('Input must be an XML string or an ElementTree.Element')

        if isinstance(xml_input, str):
            xml_input = ET.fromstring(xml_input)

        return cls._create_xml_mapping(xml_input.tag, cls._element_to_dict(xml_input))
