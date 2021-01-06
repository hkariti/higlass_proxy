import os
import getpass

from notebook.utils import url_path_join
from notebook.base.handlers import IPythonHandler
from tornado import web, httpclient, curl_httpclient, httputil
from tornado.netutil import Resolver
from urllib.parse import quote

import pycurl

class HiGlassProxyHandler(IPythonHandler):
    """
    A jupyter-to-unix-socket proxy, meant to forward to a higlass instance on the same machine.

    Heavily based on https://github.com/jupyterhub/jupyter-server-proxy
    """
    def __init__(self, *args, **kwargs):
        self.sockets_dir = kwargs.pop('sockets_dir', '/tmp/higlass')
        super().__init__(*args, **kwargs)

    def proxy_request_options(self):
        '''A dictionary of options to be used when constructing
        a tornado.httpclient.HTTPRequest instance for the proxy request.'''
        return dict(follow_redirects=True, connect_timeout=250.0, request_timeout=300.0)

    def get_client_uri(self, protocol, proxied_path):
        client_path = quote(proxied_path, safe=":/?#[]@!$&'()*+,;=-._~")

        client_uri = f'{protocol}://localhost/{client_path}'
        if self.request.query:
            client_uri += '?' + self.request.query

        return client_uri

    def _build_proxy_request(self, port, proxied_path, body):
        headers = self.request.headers.copy()

        client_uri = self.get_client_uri('http', proxied_path)
        # Some applications check X-Forwarded-Context and X-ProxyContextPath
        # headers to see if and where they are being proxied from.
        context_path = url_path_join(self.base_url, f'/higlass/{port}')
        headers['X-Forwarded-Context'] = context_path
        headers['X-ProxyContextPath'] = context_path
        # to be compatible with flask/werkzeug wsgi applications
        headers['X-Forwarded-Prefix'] = context_path

        sock = os.path.join(self.sockets_dir, str(port))
        req = httpclient.HTTPRequest(
            client_uri, method=self.request.method, body=body,
            headers=headers, **self.proxy_request_options(),
            prepare_curl_callback=lambda curl: curl.setopt(pycurl.UNIX_SOCKET_PATH, sock))
        print(client_uri)
        return req

    @web.authenticated
    async def get(self, port, proxied_path):
        httpclient.AsyncHTTPClient.configure('tornado.curl_httpclient.CurlAsyncHTTPClient')
        client = httpclient.AsyncHTTPClient(force_instance=True)

        req = self._build_proxy_request(port, proxied_path, None)
        try:
            response = await client.fetch(req, raise_error=False)
        except httpclient.HTTPError as err:
            # We need to capture the timeout error even with raise_error=False,
            # because it only affects the HTTPError raised when a non-200 response
            # code is used, instead of suppressing all errors.
            # Ref: https://www.tornadoweb.org/en/stable/httpclient.html#tornado.httpclient.AsyncHTTPClient.fetch
            if err.code == 599:
                self.set_status(599)
                self.write(str(err))
                return
            else:
                raise
        # For all non http errors...
        if response.error and type(response.error) is not httpclient.HTTPError:
            self.set_status(500)
            self.write(str(response.error))
        else:
            self.set_status(response.code, response.reason)
            # clear tornado default header
            self._headers = httputil.HTTPHeaders()

            for header, v in response.headers.get_all():
                if header not in ('Content-Length', 'Transfer-Encoding',
                                  'Content-Encoding', 'Connection'):
                    # some header appear multiple times, eg 'Set-Cookie'
                    self.add_header(header, v)

            if response.body:
                self.write(response.body)

def load_jupyter_server_extension(nb_server_app):
    """
    Called when the extension is loaded.

    Args:
        nb_server_app (NotebookWebApplication): handle to the Notebook webserver instance.
    """
    web_app = nb_server_app.web_app
    host_pattern = '.*$'
    route_pattern = url_path_join(web_app.settings['base_url'], 'higlass/([0-9]+)/(.*)')
    sockets_dir = os.path.join('/tmp', getpass.getuser(), 'higlass')
    web_app.add_handlers(host_pattern, [(route_pattern, HiGlassProxyHandler, dict(sockets_dir=sockets_dir))])
