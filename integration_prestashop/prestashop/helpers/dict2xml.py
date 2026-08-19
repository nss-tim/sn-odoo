from typing import Any, Dict, List, Tuple, Union
from xml.dom.minidom import getDOMImplementation, Attr, Document, Element


class Dict2Xml:
    """
    A class for converting a dictionary to an XML string using xml.dom.minidom.
    """

    @classmethod
    def _build_node(cls, doc: Document, tag_name: str,
                    tag_value: Any) -> Union[Element, List[Element]]:
        """
        Generate a DOM object for a given tag and its value.

        :param doc: The XML document.
        :param tag_name: The tag name.
        :param tag_value: The value for the tag.
        :return: A DOM Element or a list of Elements.
        :raises TypeError: If tag_value is of an unsupported type.
        """
        # Unwrap a dict that only contains the key 'value'
        if isinstance(tag_value, dict) and len(tag_value) == 1 and 'value' in tag_value:
            tag_value = tag_value['value']

        if tag_value is None:
            tag_value = ''

        # For simple types, create a text node
        if isinstance(tag_value, (float, int, str)):
            return cls._build_text_node(doc, tag_name, tag_value)

        # For lists, create a node for each item
        if isinstance(tag_value, list):
            nodes, _ = cls._build_children(doc, [(tag_name, item) for item in tag_value])
            return nodes

        # For dict values, process further
        if isinstance(tag_value, dict):
            if set(tag_value.keys()) == {'attrs', 'value'}:
                # Process an element with both value and attributes
                node = cls._build_node(doc, tag_name, tag_value['value'])
                attributes = cls._build_attributes(doc, tag_value['attrs'])

                for attr in attributes:
                    node.setAttributeNode(attr)

                return node

            # Create a node and process its children
            node = doc.createElement(tag_name)
            children_nodes, attributes = cls._build_children(doc, list(tag_value.items()))

            for child in children_nodes:
                node.appendChild(child)

            for attr in attributes:
                node.setAttributeNode(attr)

            return node

        raise TypeError(
            f'Unsupported type {type(tag_value).__name__} for XML tag <{tag_name}>: {tag_value!r}'
        )

    @classmethod
    def _build_children(
        cls,
        doc: Document,
        children: List[Tuple[str, Any]]
    ) -> Tuple[List[Element], List[Attr]]:
        """
        Process multiple children nodes from a list of (tag, value) pairs.

        :param doc: The XML document.
        :param children: A list of tuples (tag, value).
        :return: A tuple (list of child Elements, list of attribute Attr nodes).
        """
        node_list = []
        attributes = []
        for tag_name, tag_value in children:
            if tag_name == 'attrs':
                attributes = cls._build_attributes(doc, tag_value)
                continue

            result = cls._build_node(doc, tag_name, tag_value)

            if not isinstance(result, list):
                result = [result]

            node_list.extend(result)

        return node_list, attributes

    @classmethod
    def _build_attributes(cls, doc: Document, attrs_dict: Dict[str, Any]) -> List[Attr]:
        """
        Generate attribute nodes for an element.

        :param doc: The XML document.
        :param attrs_dict: A dictionary of attributes.
        :return: A list of attribute nodes.
        """
        attributes = []
        for attr_name, attr_value in attrs_dict.items():
            if isinstance(attr_value, dict):
                attr = doc.createAttributeNS(attr_value.get('xmlns', ''), attr_name)
                attr.nodeValue = attr_value.get('value', '')
            else:
                attr = doc.createAttribute(attr_name)
                attr.nodeValue = str(attr_value)

            attributes.append(attr)

        return attributes

    @classmethod
    def _build_text_node(cls, doc: Document, tag_name: str, tag_value: Any) -> Element:
        """
        Create an XML element with text content.

        :param doc: The XML document.
        :param tag_name: The tag name.
        :param tag_value: The text content.
        :return: A DOM Element with text.
        """
        node = doc.createElement(tag_name)
        node.appendChild(doc.createTextNode(str(tag_value)))
        return node

    @classmethod
    def to_xml(cls, data: Dict[str, Any], encoding: str = 'UTF-8') -> str:
        """
        Generate an XML string from a dictionary.

        The dictionary must have exactly one root element.

        :param data: A dictionary containing XML data.
        :param encoding: The encoding for the XML string.
        :return: An XML string.
        :raises TypeError: If data is not a dictionary.
        :raises ValueError: If data does not have exactly one root element or
            no nodes are generated.
        """
        if not isinstance(data, dict):
            raise TypeError('Data must be a dictionary')

        if len(data) != 1:
            raise ValueError('Only one root node allowed')

        doc = getDOMImplementation().createDocument(None, None, None)
        children, _ = cls._build_children(doc, list(data.items()))
        if not children:
            raise ValueError('No nodes generated from data')

        doc.appendChild(children[0])
        return doc.toxml(encoding)
