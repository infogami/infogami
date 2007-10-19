"""
Infogami read/write API.
"""

import simplejson
import httplib
import urllib

class _Storage(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError, key

    def __setattr__(self, key, value):
        self[key] = value
    
def _storify(d):
    """Recursively converts dict to web.storage object.

        >>> d = _storify({'x: 1, y={'z': 2}})
        >>> d.x
        1
        >>> d.y.z
        2
    """
    if isinstance(d, dict):
        return _Storage([(k, _storify(v)) for k, v in d.items()])
    elif isinstance(d, list):
        return [_storify(x) for x in d]
    else:
        return d

class InfogamiException(Exception):
    pass
    
class NotFound(Exception):
    pass
    
class PermissionDenied(Exception):
    pass

class Infogami:
    """Infogami API.
    
    i = Infogami('0.0.0.0', 8080)
    i.login('ibot', 'secret')
    page = i.get_page('infogami_api')
    page.d.title = 'spam spam'
    i.save_page(page)
    
    i.new_page('newpath', 'type/page', 
        dict(title='New Page', body='Demonstration of creating new page using infogami api'))
    """
    def __init__(self, host, port=8080, homepath=''):
        self.host = host
        self.port = port
        self.homepath = homepath
        self.credentials = None
        
    def _request(self, method, url, body=None, headers={}):
        conn = httplib.HTTPConnection(self.host, self.port)
        if self.credentials:
            headers['Cookie'] = self.credentials
        
        conn.request(method, url, body, headers)
        response = conn.getresponse()
        if response.status == 200:
            return response
        else:
            raise InfogamiException('HTTP Error: %d %s' % (response.status,response.reason))
        
    def _get(self, path, query, headers={}):
        return self._request('GET', path + '?' + urllib.urlencode(query), headers)
        
    def _post(self, path, body=None, headers={}):
        return self._request('POST', path, body, headers)

    def _readquery(self, queries):
        queries = simplejson.dumps(queries)
        response = self._get('/api/service/read', {'queries': queries})
        return _storify(simplejson.loads(response.read()))

    def _writequery(self, queries):
        queries = simplejson.dumps(queries)
        response = self._post('/api/service/write', queries)
        return _storify(simplejson.loads(response.read()))

    def login(self, username, password):
        """Login to infogami server using the specified username and password.
        """
        response = self._post('/api/account/login', 
                            urllib.urlencode({'username': username, 'password': password}),
                            {'Content-type': 'application/x-www-form-urlencoded'})
        
        body = simplejson.loads(response.read())
        if not body['code'].startswith('/api/status/ok'):
            raise InfogamiException("Login failed")

        self.credentials = response.getheader('set-cookie')
        
    def get_page(self, name):
        """Get the page with specified name from the server.
        """
        q = {'q': {'name': name}}
        result = self._readquery(q)
        status_code = result['q']['code']
        
        if status_code == '/api/status/ok':
            return result['q']['result']
        elif status_code == '/api/status/notfound':
            raise NotFound, name
        elif status_code == '/api/status/permission_denied':
            raise PermissionDenied, name
        else:
            raise InfogamiException(result)
    
    def save_page(self, page):
        """Creates a new version of page on the server.
        """
        q = {'q': dict(page, create=True)}
        result = self._writequery(q)
        return result['q']

    def new_page(self, name, type, d):
        """Creates a new page on the server with the specified name.
        Use save_page, if you want to add a new version of an existing page.
        """
        if isinstance(type, basestring):
            type = dict(name=type)
        return save_page(dict(name=name, type=type, d=d))
