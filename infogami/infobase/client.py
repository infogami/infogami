"""Infobase client."""

import common

import httplib, urllib
import _json as simplejson
import web
import socket
import datetime

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
    def __init__(self, status, msg):
        self.status = status
        Exception.__init__(self, msg)

class NotFound(ClientException):
    def __init__(self, msg):
        ClientException.__init__(self, "404 Not Found", msg)
    
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
        try:
            out = server.request(path, method, data)
            if 'infobase_auth_token' in web.ctx:
                self.set_auth_token(web.ctx.infobase_auth_token)
        except common.InfobaseException, e:
            raise ClientException(e.status, str(e))
        return out
        
class RemoteConnection(Connection):
    """Connection to remote Infobase server."""
    def __init__(self, base_url):
        Connection.__init__(self)
        self.base_url = base_url

    def request(self, sitename, path, method='GET', data=None):
        url = self.base_url + '/' + sitename + path
        path = '/' + sitename + path
        if isinstance(data, dict):
            for k in data.keys():
                if data[k] is None: del data[k]
        
        if DEBUG: 
            print >>web.debug, path, data
        
        if data:
            if isinstance(data, dict):
                data = urllib.urlencode(data)
            if method == 'GET':
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
            raise ClientException("503 Service Unavailable", "Unable to connect to infobase server")

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
            raise ClientException("%d %s" % (response.status, response.reason), response.read())

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
        return storify(out)
        
    def _get(self, key, revision=None):
        """Returns properties of the thing with the specified key."""
        revision = revision and int(revision)
        
        if (key, revision) not in self._cache:
            data = dict(key=key, revision=revision)
            try:
                result = self._request('/get', data=data)
            except ClientException, e:
                if e.status.startswith('404'):
                    raise NotFound, key
                else:
                    raise
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
            
    def _process_dict(self, data):
        for k, v in data.items():
            data[k] = self._process(v)
        return data
            
    def _load(self, key, revision=None):
        data = self._get(key, revision)
        data = self._process_dict(data)
        return data
        
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

            backreferences[p.name] = LazyObject(lambda q=q: [self.get(key, lazy=True) for key in self.things(q)])
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
        result = self._request('/get_many', data=data)
        things = []
        
        import copy        
        for key, data in result.items():
            data = web.storage(common.parse_query(data))
            self._cache[key, None] = data
            things.append(Thing(self, key, self._process_dict(copy.deepcopy(data))))
        return things

    def new_key(self, type):
        data = {'type': type}
        result = self._request('/new_key', data=data)
        return result

    def things(self, query, details=False):
        query = simplejson.dumps(query)
        return self._request('/things', 'GET', {'query': query, "details": str(details)})
                
    def versions(self, query):
        def process(v):
            v = web.storage(v)
            v.created = parse_datetime(v.created)
            v.author = v.author and self.get(v.author, lazy=True)
            return v
        query = simplejson.dumps(query)
        versions =  self._request('/versions', 'GET', {'query': query})
        return [process(v) for v in versions]

    def write(self, query, comment=None, action=None):
        self._run_hooks('before_new_version', query)
        _query = simplejson.dumps(query)
        result = self._request('/write', 'POST', dict(query=_query, comment=comment, action=action))
        self._run_hooks('on_new_version', query)
        self._invalidate_cache(result.created + result.updated)
        return result
    
    def save(self, query, comment=None):
        query = dict(query)
        self._run_hooks('before_new_version', query)
        
        query['_comment'] = comment
        key = query['key']
        
        #@@ save sends payload of application/json instead of form data
        data = simplejson.dumps(query)
        result = self._request('/save' + key, 'POST', data)
        if result:
            self._invalidate_cache([result['key']])
            self._run_hooks('on_new_version', query)
        return result
        
    def save_many(self, query, comment=None, action=None):
        _query = simplejson.dumps(query)
        #for q in query:
        #    self._run_hooks('before_new_version', q)
        result = self._request('/save_many', 'POST', dict(query=_query, comment=comment, action=action))
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
        perms = self._request('/permission', 'GET', dict(key=key))
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
        data = dict(username=username, displayname=displayname, email=email, password=password)
        _run_hooks("before_register", data)
        return self._request('/account/register', 'POST', data)
            
    def update_user(self, old_password, new_password, email):
        return self._request('/account/update_user', 'POST', 
            dict(old_password=old_password, new_password=new_password, email=email))
            
    def get_reset_code(self, email):
        """Returns the reset code for user specified by the email.
        This called to send forgot password email. 
        This should be called after logging in as admin.
        """
        return self._request('/account/get_reset_code', 'GET', dict(email=email))
        
    def get_user_email(self, username):
        return self._request('/account/get_user_email', 'GET', dict(username=username))
        
    def reset_password(self, username, code, password):
        return self._request('/account/reset_password', 'POST', dict(username=username, code=code, password=password))
        
    def get_user(self):
        # avoid hitting infobase when there is no cookie.
        from infogami import config
        if web.cookies().get(config.login_cookie_name) is None:
            return None
        try:
            data = self._request('/account/get_user')
        except ClientException:
            return None
        user = data and Thing(self, data['key'], data)
        return user

    def new(self, key, data=None):
        """Creates a new thing in memory.
        """
        data = common.parse_query(data)
        data = self._process_dict(data or {})
        return Thing(self, key, data)
        
def parse_datetime(datestring):
    """Parses from isoformat.
    Is there any way to do this in stdlib?
    """
    import re, datetime
    tokens = re.split('-|T|:|\.| ', datestring)
    return datetime.datetime(*map(int, tokens))

class Nothing:
    """For representing missing values.
    
    >>> n = Nothing()
    >>> str(n)
    ''
    >>> web.utf8(n)
    ''
    """
    def __getattr__(self, name):
        if name.startswith('__') or name == 'next':
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
        self._revision = revision
        
        assert data is None or isinstance(data, dict)
        
        self._data = data
        self._backreferences = None
        
        # no back-references for embeddable objects
        if self.key is None:
            self._backreferences = {}
        
    def _getdata(self):
        if self._data is None:
            self._data = self._site._load(self.key, self._revision)
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
            if 'type' not in self._data:
                return default
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
        
    def _format(self, d):
        if isinstance(d, dict):
            return dict((k, self._format(v)) for k, v in d.iteritems())
        elif isinstance(d, list):
            return [self._format(v) for v in d]
        elif isinstance(d, common.Text):
            return {'type': '/type/text', 'value': web.safeunicode(d)}
        elif isinstance(d, Thing):
            return d._dictrepr()
        elif isinstance(d, datetime.datetime):
            return {'type': '/type/datetime', 'value': d.isoformat()}
        else:
            return d
    
    def dict(self):
        return self._format(self._getdata())
    
    def _dictrepr(self):
        if self.key is None:
            return self.dict()
        else:
            return {'key': self.key}
    
    def update(self, data):
        data = common.parse_query(data)
        data = self._site._process_dict(data)
        self._data.update(data)

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
        if self.key:
            return "<Thing: %s>" % repr(self.key)
        else:
            return "<Thing: %s>" % repr(self._data)
            
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
