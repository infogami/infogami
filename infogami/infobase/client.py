"""Infobase client."""

import common

import httplib, urllib
import _json as simplejson
import web
import socket

DEBUG = False

def storify(d):
    if isinstance(d, dict):
        for k, v in d.items():
            d[k] = storify(v)
        return web.storage(d)
    elif isinstance(d, list):
        return [storify(x) for x in d]
    else:
        return d

class ClientException(Exception):
    pass

class NotFound(ClientException):
    pass
    
class HTTPError(ClientException):
    pass

def connect(type, **params):
    """Connect to infobase server using the given params.
    """
    for t in _connection_types:
        if type == t:
            return _connection_types[t](**params)
    raise Exception('Invalid connection type: ' + type)
                
class Connection:
    def __init__(self):
        self.auth_token = None
        
    def set_auth_token(self, token):
        self.auth_token = token

    def get_auth_token(self):
        return self.auth_token

    def request(self, path, method='GET', data=None):
        raise NotImplementedError
        
class LocalConnection(Connection):
    """LocalConnection assumes that db_parameters are set in web.config."""
    def __init__(self, **params):
        Connection.__init__(self)
        pass
        
    def request(self, sitename, path, method='GET', data=None):
        import server
        path = "/" + sitename + path
        web.ctx.infobase_auth_token = self.get_auth_token()
        out = server.request(path, method, data)
        if 'infobase_auth_token' in web.ctx:
            self.set_auth_token(web.ctx.infobase_auth_token)
        return out
                
class RemoteConnection(Connection):
    """Connection to remote Infobase server."""
    def __init__(self, base_url):
        Connection.__init__(self)
        self.base_url = base_url

    def request(self, sitename, path, method='GET', data=None):
        url = self.base_url + '/' + sitename + path
        path = '/' + sitename + path
        if data:
            for k in data.keys():
                if data[k] is None: del data[k]
        
        if DEBUG: 
            print >>web.debug, path, data
        
        data = data and urllib.urlencode(data)
        if data and method == 'GET':
            path += '?' + data
            data = None
        
        conn = httplib.HTTPConnection(self.base_url)
        env = web.ctx.get('env') or {}
        
        if self.auth_token:
            import Cookie
            c = Cookie.SimpleCookie()
            c['infobase_auth_token'] = self.auth_token
            cookie = c.output(header='').strip()
            headers = {'Cookie': cookie}
        else:
            headers = {}
            
        # pass the remote ip to the infobase server
        headers['X-REMOTE-IP'] = web.ctx.ip
        
        try:
            conn.request(method, path, data, headers=headers)
            response = conn.getresponse()
        except socket.error:
            return simplejson.dumps({'status': 'fail', 'message': 'unable to connect to the infobase server'})

        cookie = response.getheader('Set-Cookie')
        if cookie:
            import Cookie
            c = Cookie.SimpleCookie()
            c.load(cookie)
            if 'infobase_auth_token' in c:
                self.set_auth_token(c['infobase_auth_token'].value)                
        if response.status == 200:
            return response.read()
        else:
            return simplejson.dumps({'status': 'fail', 'message': 'HTTP Error: %d - %s' % (response.status, response.reason)})    

_connection_types = {
    'local': LocalConnection,
    'remote': RemoteConnection
}
        
class LazyObject:
    """LazyObject which creates the required object on demand.
        >>> o = LazyObject(lambda: [1, 2, 3])
        >>> o
        [1, 2, 3]
    """
    def __init__(self, creator):
        self.__dict__['_creator'] = creator
        self.__dict__['_o'] = None
        
    def _get(self):
        if self._o is None:
            self._o = self._creator()
        return self._o
        
    def __getattr__(self, key):
        return getattr(self._get(), key)
            
class Site:
    def __init__(self, conn, sitename):
        self._conn = conn
        self.name = sitename
        # cache for storing pages requested in this HTTP request
        self._cache = {}
        
    def _request(self, path, method='GET', data=None):
        out = self._conn.request(self.name, path, method, data)
        out = simplejson.loads(out)
        out = storify(out)
        if out.status == 'fail':
            raise ClientException(out['message'])
        else:
            return out
        
    def _get(self, key, revision=None):
        """Returns properties of the thing with the specified key."""
        revision = revision and int(revision)
        
        if (key, revision) not in self._cache:
            data = dict(key=key, revision=revision)
            result = self._request('/get', data=data)['result']
            if result is None:
                raise NotFound, key
            else:
                self._cache[key, revision] = web.storage(common.parse_query(result))
        import copy
        return copy.deepcopy(self._cache[key, revision])
        
    def _process(self, value):
        if isinstance(value, list):
            return [self._process(v) for v in value]
        elif isinstance(value, dict):
            d = {}
            for k, v in value.items():
                d[k] = self._process(v)
            return Thing(self, None, d)
        elif isinstance(value, common.Reference):
            return Thing(self, unicode(value), None)
        else:
            return value
            
    def _load(self, key, revision=None):
        data = self._get(key, revision)
        for k, v in data.items():
            data[k] = self._process(v)
        return data
        
    def _fill_backreferences(self, key, data):
        def safeint(x):
            try: return int(x)
            except ValueError: return 0
            
        if 'env' in web.ctx:
            i = web.input(_method='GET')
        else:
            i = web.storage()
        page_size = 20
        for p in data.type.backreferences:
            offset = page_size * safeint(i.get(p.name + '_page') or '0')
            q = {
                p.property_name: key, 
                'offset': offset,
                'limit': page_size
            }
            if p.expected_type:
                q['type'] = p.expected_type.key
            data['_backreferences'][p.name] = LazyObject(lambda: [self.get(key, lazy=True) for key in self.things(q)])
            
    def _get_backreferences(self, thing):
        def safeint(x):
            try: return int(x)
            except ValueError: return 0
            
        if 'env' in web.ctx:
            i = web.input(_method='GET')
        else:
            i = web.storage()
        page_size = 20
        backreferences = {}
    
        for p in thing.type._getdata().get('backreferences', []):
            offset = page_size * safeint(i.get(p.name + '_page') or '0')
            q = {
                p.property_name: thing.key, 
                'offset': offset,
                'limit': page_size
            }
            if p.expected_type:
                q['type'] = p.expected_type.key
            backreferences[p.name] = LazyObject(lambda: [self.get(key, lazy=True) for key in self.things(q)])
        return backreferences
            
    def get(self, key, revision=None, lazy=False):
        assert key.startswith('/')
        try:
            thing = Thing(self, key, data=None, revision=revision)
            if not lazy:
                thing._getdata()
            return thing
        except NotFound:
            return None

    def get_many(self, keys):
        data = dict(keys=simplejson.dumps(keys))
        result = self._request('/get_many', data=data)['result']
        things = []
        
        import copy        
        for key, data in result.items():
            data = web.storage(common.parse_query(data))
            self._cache[key, None] = data
            things.append(Thing(self, key, self._process(copy.deepcopy(data))))
        return things

    def new_key(self, type):
        data = {'type': type}
        result = self._request('/new_key', data=data)['result']
        return result

    def things(self, query):
        query = simplejson.dumps(query)
        return self._request('/things', 'GET', {'query': query})['result']
                
    def versions(self, query):
        def process(v):
            v = web.storage(v)
            v.created = parse_datetime(v.created)
            v.author = v.author and self.get(v.author, lazy=True)
            return v
        query = simplejson.dumps(query)
        versions =  self._request('/versions', 'GET', {'query': query})['result']
        return [process(v) for v in versions]

    def write(self, query, comment=None):
        self._run_hooks('before_new_version', query)
        _query = simplejson.dumps(query)
        result = self._request('/write', 'POST', dict(query=_query, comment=comment))['result']
        self._run_hooks('on_new_version', query)
        self._invalidate_cache(result.created + result.updated)
        return result
    
    def save(self, query, comment=None):
        _query = simplejson.dumps(query)
        result = self._request('/save', 'POST', dict(key=query['key'], data=_query, comment=comment))['result']
        self._invalidate_cache([result['key']])
        self._run_hooks('on_new_version', query)
        return result
        
    def save_many(self, query, comment=None):
        _query = simplejson.dumps(query)
        result = self._request('/save_many', 'POST', dict(query=_query, comment=comment))['result']
        self._invalidate_cache([r['key'] for r in result])
        for q in query:
            self._run_hooks('on_new_version', q)
        return result
    
    def _invalidate_cache(self, keys):
        for k in keys:
            try:
                del self._cache[k, None]
            except KeyError:
                pass
    
    def can_write(self, key):
        perms = self._request('/permission', 'GET', dict(key=key))['result']
        return perms['write']

    def _run_hooks(self, name, query):
        if isinstance(query, dict) and 'key' in query:
            key = query['key']
            type = query.get('type')
            # type is none when saving permission
            if type is not None:
                if isinstance(type, dict):
                    type = type['key']
                type = self.get(type)
                data = query.copy()
                data['type'] = type
                t = self.new(key, data)
                # call the global _run_hooks function
                _run_hooks(name, t)
        
    def login(self, username, password, remember=False):
        return self._request('/account/login', 'POST', dict(username=username, password=password))
        
    def register(self, username, displayname, email, password):
        return self._request('/account/register', 'POST', 
            dict(username=username, displayname=displayname, email=email, password=password))
            
    def update_user(self, old_password, new_password, email):
        return self._request('/account/update_user', 'POST', 
            dict(old_password=old_password, new_password=new_password, email=email))
            
    def get_reset_code(self, email):
        """Returns the reset code for user specified by the email.
        This called to send forgot password email. 
        This should be called after logging in as admin.
        """
        return self._request('/account/get_reset_code', 'GET', dict(email=email))['result']
        
    def get_user_email(self, username):
        return self._request('/account/get_user_email', 'GET', dict(username=username))['result']
        
    def reset_password(self, username, code, password):
        return self._request('/account/reset_password', 'POST', dict(username=username, code=code, password=password))
        
    def get_user(self):
        # avoid hitting infobase when there is no cookie.
        from infogami import config
        if web.cookies().get(config.login_cookie_name) is None:
            return None
        try:
            data = self._request('/account/get_user')['result']
        except ClientException:
            return None
        user = data and Thing(self, data['key'], data)
        return user

    def new(self, key, data=False):
        """Creates a new thing in memory.
        """
        return Thing(self, key, data)
        
def parse_datetime(datestring):
    """Parses from isoformat.
    Is there any way to do this in stdlib?
    """
    import re, datetime
    tokens = re.split('-|T|:|\.| ', datestring)
    return datetime.datetime(*map(int, tokens))

class Nothing:
    """For representing missing values."""
    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError, name
        else:
            return self

    def __getitem__(self, name):
        return self

    def __call__(self, *a, **kw):
        return self

    def __add__(self, a):
        return a 

    __radd__ = __add__
    __mul__ = __rmul__ = __add__

    def __iter__(self):
        return iter([])

    def __hash__(self):
        return id(self)

    def __len__(self):
        return 0
        
    def __bool__(self):
        return False
        
    def __eq__(self, other):
        return isinstance(other, Nothing)
    
    def __ne__(self, other):
        return not (self == other)

    def __str__(self): return ""
    def __repr__(self): return ""

nothing = Nothing()

class Thing:
    def __init__(self, site, key, data=None, revision=None):
        self._site = site
        self.key = key
        self.revision = revision
        
        self._data = data
        self._backreferences = None
        
    def _getdata(self):
        if self._data is None:
            self._data = self._site._load(self.key, self.revision)
        return self._data
        
    def _get_backreferences(self):
        if self._backreferences is None:
            self._backreferences = self._site._get_backreferences(self)
        return self._backreferences
    
    def keys(self):
        special = ['revision', 'latest_revision', 'last_modified', 'created']
        return [k for k in self._getdata() if k not in special]

    def get(self, key, default=None):
        try:
            return self._getdata()[key]
        except KeyError:
            return self._get_backreferences().get(key, default) 

    def __getitem__(self, key):
        return self.get(key, nothing)
    
    def __setitem__(self, key, value):
        self._getdata()[key] = value
    
    def __setattr__(self, key, value):
        if key in ['key', 'revision', 'latest_revision', 'last_modified', 'created'] or key.startswith('_'):
            self.__dict__[key] = value
        else:
            self._getdata()[key] = value

    def __iter__(self):
        return iter(self._data)
        
    def _save(self, comment=None):
        d = self.dict()
        return self._site.save(d, comment)
        
    def dict(self):
        return common.format_data(self._getdata(), Thing)
        
    def __getattr__(self, key):
        if key.startswith('__'):
            raise AttributeError, key

        return self[key]
            
    
    def __eq__(self, other):
        return isinstance(other, Thing) and other.key == self.key
        
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __str__(self):
        return web.utf8(self.key)
    
    def __repr__(self):
        return "<Thing: %s>" % repr(self.key)
            
# hooks can be registered by extending the hook class
hooks = []
class metahook(type):
    def __init__(self, name, bases, attrs):
        hooks.append(self())
        type.__init__(self, name, bases, attrs)

class hook:
    __metaclass__ = metahook

#remove hook from hooks    
hooks.pop()

def _run_hooks(name, thing):
    for h in hooks:
        m = getattr(h, name, None)
        if m:
            m(thing)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
