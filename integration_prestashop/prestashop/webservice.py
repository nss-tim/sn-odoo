import mimetypes
import requests
import warnings
import uuid

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode
from xml.parsers.expat import ExpatError
from xml.etree import ElementTree

from .helpers import Dict2Xml, Xml2Dict


HTTP_CODE_TO_MESSAGE = {
    204: 'No Content',
    400: 'Bad Request',
    401: 'Unauthorized',
    404: 'Not Found',
    405: 'Method Not Allowed',
    500: 'Internal Server Error',
}

SUPPORTED_PARAMETERS = {
    'filter', 'display', 'sort', 'ws_key', 'limit',
    'schema', 'date', 'id_shop', 'id_group_shop', 'sendemail',
}

DEFAULT_HEADERS = {'Content-Type': 'text/xml'}


@dataclass
class RequestContext:
    """Request context information for debugging purposes."""
    url: str
    method: str
    headers: Dict[str, str]
    data: Optional[Union[str, bytes]] = None


def get_content_type(filename: str) -> str:
    """
    Retrieve the MIME type for a given filename.

    :param filename: The file name.
    :return: MIME type as a string.
    """
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


class PrestaShopAPIError(Exception):
    """
    Generic PrestaShop API error class.
    """
    def __init__(self, msg: str, error_code: Optional[int] = None,
                 ps_error_msg: str = '', ps_error_code: Optional[int] = None,
                 request_context: Optional[RequestContext] = None,
                 response_content: Optional[bytes] = None) -> None:
        self.msg = msg
        self.error_code = error_code
        self.ps_error_msg = ps_error_msg
        self.ps_error_code = ps_error_code
        self.request_context = request_context
        self.response_content = response_content

    def __str__(self) -> str:
        error_msg = self.ps_error_msg or self.msg

        # Add debugging information for better error tracking
        debug_info = []
        if self.request_context:
            debug_info.append(f"Request URL: {self.request_context.url}")
            debug_info.append(f"Request Method: {self.request_context.method}")
            if self.request_context.headers:
                # Filter out sensitive headers
                safe_headers = {
                    k: v
                    for k, v in self.request_context.headers.items()
                    if k.lower() not in ['authorization', 'cookie']
                }
                if safe_headers:
                    debug_info.append(f"Request Headers: {safe_headers}")
            if self.request_context.data and len(str(self.request_context.data)) < 1000:  # Only show small data
                debug_info.append(f"Request Data: {self.request_context.data}")
        if self.error_code:
            debug_info.append(f"HTTP Status Code: {self.error_code}")
        if self.response_content and len(self.response_content) < 1000:  # Only show small responses
            try:
                debug_info.append(f"Response Content: {self.response_content.decode('utf-8', errors='ignore')}")
            except Exception:
                debug_info.append(f"Response Content (bytes): {self.response_content}")

        if debug_info:
            debug_str = "\n".join(debug_info)
            return f"{error_msg}\n\nDebug Information:\n{debug_str}"

        return error_msg


class PrestaShopInternalError(Exception):
    """
    Internal error class for simple error handling within the API client.
    """
    def __init__(self, msg: str, error_code: Optional[int] = None,
                 ps_error_msg: str = '', ps_error_code: Optional[int] = None,
                 response_content: Optional[bytes] = None) -> None:
        self.msg = msg
        self.error_code = error_code
        self.ps_error_msg = ps_error_msg
        self.ps_error_code = ps_error_code
        self.response_content = response_content


class PrestaShopAPIClient:
    """
    Interact with the PrestaShop API using XML for messages.
    """
    def __init__(self, store_url: str, api_key: str,
                 session: Optional[requests.Session] = None) -> None:
        self._api_url = store_url.rstrip('/') + '/api/'
        self._api_key = api_key

        self.client = session or requests.Session()

        if not self.client.auth:
            self.client.auth = (api_key, '')

    def _parse(self, content: bytes) -> Dict[str, Any]:
        """
        Parse the XML response from the API and convert it to a dict.

        :param content: Response content.
        :return: A dictionary representation of the XML.
        :raises PrestaShopInternalError: If the content is empty or not parsable.
        """
        if not content:
            raise PrestaShopInternalError('HTTP response is empty', response_content=content)

        # PrestaShop (PHP) sometimes emits whitespace before the XML declaration,
        # which makes the parser fail with "not at start of entity". Strip it defensively.
        content = content.lstrip()

        try:
            parsed_content = ElementTree.fromstring(content)
        except (ExpatError, ElementTree.ParseError) as err:
            raise PrestaShopInternalError(
                f'HTTP XML response is not parsable: {err}',
                response_content=content
            )

        return Xml2Dict.from_xml(parsed_content)

    def _parse_error(self, xml_content: bytes) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract the PrestaShop error from the XML content.

        :param xml_content: XML content returned by the PS server.
        :return: Tuple (prestashop_error_code, prestashop_error_message)
        """
        code, message = None, None

        try:
            error_response = self._parse(xml_content)
        except PrestaShopInternalError:
            # If parsing fails, return None values - the original error will be raised
            return (None, None)

        if isinstance(error_response, dict):
            error_content = error_response.get('prestashop', {}).get('errors', {}).get('error', {})

            if isinstance(error_content, list):
                error_content = error_content[0]

            code = error_content.get('code')
            message = error_content.get('message')

        return (code, message)

    def _check_status_code(self, status_code: int, content: bytes) -> bool:
        """
        Check the HTTP status code and raise an exception if necessary.

        :param status_code: Status code returned by the server.
        :param content: Content of the response.
        :return: True if status code is OK; otherwise, raises an exception.
        :raises PrestaShopInternalError: If the status code indicates an error.
        """
        if status_code in (200, 201):
            return True

        if status_code == 401:
            raise PrestaShopInternalError(
                HTTP_CODE_TO_MESSAGE[status_code],
                status_code,
                response_content=content
            )

        ps_error_code, ps_error_msg = self._parse_error(content)
        raise PrestaShopInternalError(
            HTTP_CODE_TO_MESSAGE.get(status_code, 'Unknown Error'),
            status_code,
            ps_error_msg=ps_error_msg,
            ps_error_code=ps_error_code,
            response_content=content
        )

    def _execute_and_parse(self, url: str, method: str,
                           data: Optional[Union[str, bytes]] = None,
                           add_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Execute a request and parse the XML response, raising PrestaShopAPIError
        with full request context on any failure (HTTP error or parse error).

        :param url: Full URL to call.
        :param method: HTTP method: GET, POST, PUT, DELETE, HEAD.
        :param data: For PUT and POST requests, the XML sent to PrestaShop.
        :param add_headers: Additional headers to merge onto the default headers.
        :return: A dict representing the parsed response.
        :raises PrestaShopAPIError: If the request fails or the response is not parsable.
        """
        response = self._execute(url, method, data=data, add_headers=add_headers)
        try:
            return self._parse(response.content)
        except PrestaShopInternalError as e:
            request_context = RequestContext(url=url, method=method,
                                             headers=add_headers or {}, data=data)
            raise PrestaShopAPIError(
                e.msg,
                error_code=e.error_code,
                ps_error_msg=e.ps_error_msg,
                ps_error_code=e.ps_error_code,
                request_context=request_context,
                response_content=e.response_content,
            )

    def _execute(self, url: str, method: str,
                 data: Optional[Union[str, bytes]] = None,
                 add_headers: Optional[Dict[str, str]] = None) -> requests.Response:
        """
        Execute a request on the PrestaShop API.

        :param url: Full URL to call.
        :param method: HTTP method: GET, POST, PUT, DELETE, HEAD.
        :param data: For PUT and POST requests, the XML sent to PrestaShop.
        :param add_headers: Additional headers to merge onto the default headers.
        :return: The response object.
        :raises PrestaShopAPIError: If the request fails with detailed debugging information.
        """
        headers = self.client.headers.copy()
        headers.update(add_headers or {})

        try:
            response = self.client.request(method, url, data=data, headers=headers)
            self._check_status_code(response.status_code, response.content)
            return response
        except PrestaShopInternalError as e:
            # Re-raise internal errors with full debugging context
            request_context = RequestContext(url=url, method=method, headers=headers, data=data)
            raise PrestaShopAPIError(
                e.msg,
                error_code=e.error_code,
                ps_error_msg=e.ps_error_msg,
                ps_error_code=e.ps_error_code,
                request_context=request_context,
                response_content=e.response_content
            )

    def _validate_query_options(self, options: Dict[str, Any]) -> bool:
        """
        Check options against supported parameters.

        :param options: Dict of options to use for the request.
        :return: True if valid; otherwise, raises an error.
        """
        if not isinstance(options, dict):
            raise PrestaShopAPIError('Parameters must be a dict')

        unsupported = {
            param.split('[')[0] for param in options
        }.difference(SUPPORTED_PARAMETERS)

        if unsupported:
            raise PrestaShopAPIError(f'Unsupported parameters: {unsupported}')

        return True

    def add(self, resource: str,
            content: Optional[Union[str, Dict[Any, Any]]] = None,
            files: Optional[List[Tuple[str, str, Union[str, bytes]]]] = None,
            options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Add (POST) a resource.

        :param resource: Resource type to create.
        :param content: Full XML string or dict of new resource values.
        :param files: Sequence of (fieldname, filename, value) tuples for file uploads.
        :param options: Optional dict of parameters.
        :return: A dict representing the response.
        """
        full_url = self._api_url + resource

        if options is not None:
            self._validate_query_options(options)
            full_url += f'?{urlencode(options)}'

        return self.add_with_url(full_url, content, files)

    def add_with_url(self, url: str,
                     content: Optional[Union[str, Dict[Any, Any]]] = None,
                     files: Optional[List[Tuple[str, str, Union[str, bytes]]]] = None
                     ) -> Dict[str, Any]:
        """
        Add (POST) a resource using a full URL.

        If files are provided, a multipart/form-data POST is built for file uploads.
        In that case, any XML parameter is ignored.

        :param url: Full URL for the resource creation.
        :param content: Full XML string or dict of new resource values.
        :param files: A sequence of file tuples (fieldname, filename, value).
        :return: A dict representing the parsed response.
        """
        if files is not None:
            if content is not None:
                warnings.warn("Content parameter is ignored when files are provided", UserWarning)

            multipart_fields = []
            for file_field in files:
                if len(file_field) != 3:
                    raise PrestaShopAPIError(f'Invalid file tuple: {file_field}')

                fieldname, filename, value = file_field
                content_type = get_content_type(filename)

                multipart_fields.append((fieldname, filename, value, content_type))

            headers, body = self.encode_multipart_formdata(multipart_fields)
            return self._execute_and_parse(url, 'POST', data=body, add_headers=headers)

        if content is not None:
            if isinstance(content, dict):
                content = Dict2Xml.to_xml({'prestashop': content})

            return self._execute_and_parse(url, 'POST', data=content, add_headers=DEFAULT_HEADERS)

        raise PrestaShopAPIError('Undefined Data')

    def search(self, resource: str,
               options: Optional[Dict[str, Any]] = None) -> List[int]:
        """
        Retrieve (GET) a resource and return a list of its IDs.

        :param resource: Resource type (e.g. 'addresses', 'products').
        :param options: Optional dict of parameters to filter the search.
        :return: List of IDs as integers.
        """
        response = self.get(resource, options=options)

        if not response:
            return []

        # Expected response format from self.get() is as follows:
        #
        # For multiple resources:
        #     {
        #         'products': {
        #             'product': [
        #                 { 'attrs': {'id': '1'}, 'value': '' },
        #                 { 'attrs': {'id': '2'}, 'value': '' },
        #                 { 'attrs': {'id': '3'}, 'value': '' }
        #             ]
        #         }
        #     }
        #
        # For a single resource:
        #     {
        #         'products': {
        #             'product': { 'attrs': {'id': '1'}, 'value': '' }
        #         }
        #     }

        records = list(response.values())[0]

        if isinstance(records, dict) and len(records) == 1:
            records = list(records.values())[0]

        if isinstance(records, list):
            return [int(record['attrs']['id']) for record in records]

        if isinstance(records, dict):
            return [int(records['attrs']['id'])]

        return []

    def get(self, resource: str,
            resource_id: Optional[Union[int, str]] = None,
            options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retrieve (GET) a resource.

        :param resource: Resource type to retrieve.
        :param resource_id: Optional resource ID.
        :param options: Optional dict of parameters.
        :return: A dict representing the response.
        """
        full_url = self._api_url + resource

        if resource_id is not None:
            full_url += f'/{resource_id}'

        if options is not None:
            self._validate_query_options(options)
            full_url += f'?{urlencode(options)}'

        return self.get_with_url(full_url)

    def get_with_url(self, url: str) -> Dict[str, Any]:
        """
        Retrieve (GET) a resource from a full URL.

        :param url: Full URL specifying the resource.
        :return: A dict representing the response.
        """
        response = self._execute_and_parse(url, 'GET')

        if isinstance(response, dict) and 'prestashop' in response:
            return response['prestashop']

        return response

    def head(self, resource: str,
             resource_id: Optional[Union[int, str]] = None,
             options: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Retrieve headers (HEAD) for a resource.

        :param resource: Resource type.
        :param resource_id: Optional resource ID.
        :param options: Optional dict of parameters.
        :return: Headers of the response as a dict.
        """
        full_url = self._api_url + resource

        if resource_id is not None:
            full_url += f'/{resource_id}'

        if options is not None:
            self._validate_query_options(options)
            full_url += f'?{urlencode(options)}'

        return self.head_with_url(full_url)

    def head_with_url(self, url: str) -> Dict[str, str]:
        """
        Retrieve headers (HEAD) for a resource from a full URL.

        :param url: Full URL specifying the resource.
        :return: Headers of the response as a dict.
        """
        return self._execute(url, 'HEAD').headers

    def edit(self, resource: str,
             content: Union[str, Dict[Any, Any]],
             options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Edit (PUT) a resource.

        :param resource: Resource type to edit.
        :param content: Full XML string or dict of new resource values.
        :param options: Optional dict of parameters.
        :return: A dict representing the response.
        """
        full_url = self._api_url + resource

        if options:
            self._validate_query_options(options)
            full_url += f'?{urlencode(options)}'

        return self.edit_with_url(full_url, content)

    def edit_with_url(self, url: str, content: Union[str, Dict[Any, Any]]) -> Dict[str, Any]:
        """
        Edit (PUT) a resource using a full URL.

        :param url: Full URL for editing the resource.
        :param content: Full XML string or dict of new resource values.
        :return: A dict representing the response.
        """
        headers = DEFAULT_HEADERS.copy()

        if isinstance(content, dict):
            content = Dict2Xml.to_xml({'prestashop': content})

        return self._execute_and_parse(url, 'PUT', data=content, add_headers=headers)

    def delete(self, resource: str,
               resource_ids: Union[int, List[Union[int, str]]]) -> bool:
        """
        Delete (DELETE) a resource.

        :param resource: Resource type.
        :param resource_ids: Integer or list of IDs to delete.
        :return: True if deletion is successful.
        """
        full_url = self._api_url + resource

        if isinstance(resource_ids, (tuple, list)):
            merged_ids = ','.join([str(resource_id) for resource_id in resource_ids])
            full_url += f'/?id=[{merged_ids}]'
        else:
            full_url += f'/{resource_ids}'

        return self.delete_with_url(full_url)

    def delete_with_url(self, url: str) -> bool:
        """
        Delete (DELETE) a resource using a full URL.

        :param url: Full URL for deleting the resource.
        :return: True if deletion is successful.
        """
        self._execute(url, 'DELETE')
        return True

    def encode_multipart_formdata(self, fields: List[Tuple[str, str, Union[str, bytes], str]]
                                  ) -> Tuple[Dict[str, str], bytes]:
        """
        Encode fields for an HTTP multipart/form-data request.

        This method builds the multipart body using a dynamically generated boundary
        that mimics common browser boundaries (e.g. WebKitFormBoundary...) which may help
        bypass strict firewall filters.

        :param fields: A list of 4-tuples: (fieldname, filename, value, content_type)
        :return: A tuple (headers, body) where headers is a dict with the appropriate
                 Content-Type header and body is a bytes object.
        """
        boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
        boundary_bytes = boundary.encode('utf-8')

        lines = []
        for fieldname, filename, value, content_type in fields:
            lines.append(b'--' + boundary_bytes)

            disposition = f'Content-Disposition: form-data; name="{fieldname}"; filename="{filename}"'  # NOQA
            lines.append(disposition.encode('utf-8'))

            ct_header = f'Content-Type: {content_type}'
            lines.append(ct_header.encode('utf-8'))

            lines.append(b'')

            if isinstance(value, str):
                lines.append(value.encode('utf-8'))
            else:
                lines.append(value)

        lines.append(b'--' + boundary_bytes + b'--')
        lines.append(b'')
        body = b'\r\n'.join(lines)

        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}'
        }

        return headers, body
