"""Infobase client."""
import httplib, urllib
import simplejson
import web

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
    
class Client:
    """Client to connect to infobase server. 
    """
    def __init__(self, host, sitename):
        self.host = host
        self.sitename = sitename
        self.cookie = None
        
    def do_request(self, path, method='GET', data=None):
        path = "/%s%s" % (self.sitename, path)
        if self.host:
            # don't send nulls
            for k in data.keys():
                if data[k] is None: del data[k]
            
            if DEBUG: print >>web.debug, path, data
            data = data and urllib.urlencode(data)
            if data and method == 'GET':
                path += '?' + data
                data = None
            
            conn = httplib.HTTPConnection(self.host)
            env = web.ctx.get('env') or {}
            
            cookie = self.cookie or env.get('HTTP_COOKIE')
            if cookie:
                headers = {'Cookie': cookie}
            else:
                headers = {}
            
            conn.request(method, path, data, headers=headers)
            response = conn.getresponse()
            
            cookie = response.getheader('Set-Cookie')
            self.cookie = cookie
            # forgot password is executed in as admin user. 
            # So, the cookie for the admin user should not be sent to the requested user.
            if cookie and not web.ctx.get('admin_mode'):
                web.header('Set-Cookie', cookie)
            
            if response.status == 200:
                out = response.read()
            else:
                raise HTTPError("%d: %s" % (response.status, response.reason))
        else:
            import server
            out = server.request(path, method, data)
        return out
        
    def request(self, path, method='GET', data=None):
        """Sends request to the server.
        data should be a dictonary. For GET request, it is passed as query string
        and for POST requests, it is passed as POST data.
        """
        out = self.do_request(path, method, data)
        out = simplejson.loads(out)
        out = storify(out)
        if out.status == 'fail':
            raise ClientException(out['message'])
        else:
            return out
            
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
    def __init__(self, client):
        self._client = client
        self.name = client.sitename
        # cache for storing pages requested in this HTTP request
        self._cache = {}
        
    def _get(self, key, revision=None):
        """Returns properties of the thing with the specified key."""
        revision = revision and int(revision)
        data = dict(key=key, revision=revision)
        result = self._client.request('/get', data=data)['result']
        if result is None:
            raise NotFound, key
        else:
            return result
            
    def _load(self, key, revision=None):
        def process(value):
            if isinstance(value, list):
                return [process(v) for v in value]
            elif isinstance(value, dict):
                return Thing(self, value['key'], None)
            else:
                return value
            
        if (key, revision) not in self._cache:      
            data = self._get(key, revision)
            data = web.storage(data)
            for k, v in data.items():
                data[k] = process(v)
        
            data['last_modified'] = parse_datetime(data['last_modified'])
            self._cache[key, revision] = data
            # it is important to call _fill_backreferences after updating the cache.
            # otherwise, _fill_backreferences is called recursively for type/type.
            self._fill_backreferences(key, data)
        return self._cache[key, revision].copy()
        
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
            data[p.name] = LazyObject(lambda: [self.get(key, lazy=True) for key in self.things(q)])
            
    def get(self, key, revision=None, lazy=False):
        assert key.startswith('/')
        try:
            thing = Thing(self, key, data=None, revision=revision)
            if not lazy:
                thing._getdata()
            return thing
        except NotFound:
            return None

    def things(self, query):
        query = simplejson.dumps(query)
        return self._client.request('/things', 'GET', {'query': query})['result']
                
    def versions(self, query):
        def process(v):
            v = web.storage(v)
            v.created = parse_datetime(v.created)
            v.author = v.author and self.get(v.author, lazy=True)
            return v
        query = simplejson.dumps(query)
        versions =  self._client.request('/versions', 'GET', {'query': query})['result']
        return [process(v) for v in versions]

    def write(self, query, comment=None):
        self._run_hooks('before_new_version', query)
        _query = simplejson.dumps(query)
        result = self._client.request('/write', 'POST', dict(query=_query, comment=comment))['result']
        self._run_hooks('on_new_version', query)
        return result
        
    def can_write(self, key):
        perms = self._client.request('/permission', 'GET', dict(key=key))['result']
        return perms['write']

    def _run_hooks(self, name, query):
        if isinstance(query, dict):
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
        return self._client.request('/account/login', 'POST', dict(username=username, password=password))
        
    def register(self, username, displayname, email, password):
        return self._client.request('/account/register', 'POST', 
            dict(username=username, displayname=displayname, email=email, password=password))
            
    def update_user(self, old_password, new_password, email):
        return self._client.request('/account/update_user', 'POST', 
            dict(old_password=old_password, new_password=new_password, email=email))
            
    def get_reset_code(self, email):
        """Returns the reset code for user specified by the email.
        This called to send forgot password email. 
        This should be called after logging in as admin.
        """
        return self._client.request('/account/get_reset_code', 'GET', dict(email=email))['result']
        
    def reset_password(self, username, code, password):
        return self._client.request('/account/reset_password', 'POST', dict(username=username, code=code, password=password))
        
    def get_user(self):
        data = self._client.request('/account/get_user')['result']
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
    tokens = re.split('-|T|:|\.', datestring)
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
        if data is False:
            self._data = {}
        else:
            self._data = data
        self.revision = revision
        
    def _getdata(self):
        if self._data is None:
            self._data = self._site._load(self.key, self.revision)
            self.revision = self._data.pop('revision')
        return self._data
        
    def keys(self):
        return self._getdata().keys()
        
    def __getitem__(self, key):
        return self._getdata().get(key, nothing)
        
    def __setitem__(self, key, value):
        self._getdata()[key] = value
    
    def __setattr__(self, key, value):
        if key in ['key', 'revision'] or key.startswith('_'):
            self.__dict__[key] = value
        else:
            self._getdata()[key] = value
        
    def __iter__(self):
        return iter(self._data)
        
    def get(self, key, default=None):
        return self._getdata().get(key, default)
    
    def save(self, comment=None):
        d = self.dict()
        d['create'] = 'unless_exists'
        d['key'] = self.key
        result = self._site.write(d, comment)
        if self.key in result.created:
            return 'created'
        elif self.key in result.updated:
            return 'updated'
        else:
            return result
        
    def dict(self):
        def unthingify(thing):
            if isinstance(thing, list):
                return [unthingify(x) for x in thing]
            elif isinstance(thing, Thing):
                return {'key': thing.key}
            else:
                return thing

        d = {}
        for k, v in self._data.items():
            d[k] = unthingify(v)
            
        d.pop('last_modified', None)
        return d
        
    def __getattr__(self, key):
        if key.startswith('__'):
            raise AttributeError, key

        return self[key]
    
    def __eq__(self, other):
        return isinstance(other, Thing) and other.key == self.key
        
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __str__(self):
        return self.key
    
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
