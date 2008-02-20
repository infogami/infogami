"""Infobase client."""
import httplib, urllib
import simplejson
import web

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
    def __init__(self, host, sitename):
        self.host = host
        self.sitename = sitename
        
    def request(self, path, method='GET', data=None):
        path = "/%s%s" % (self.sitename, path)
        if self.host:
            data = data and urllib.urlencode(data)
            if data and method == 'GET':
                path += '?' + data
                data = None
            conn = httplib.HTTPConnection(self.host)
            conn.request(method, path, data)
            response = conn.getresponse()
            if response.status == 200:
                out = response.read()
            else:
                raise HTTPError("%d: %s" % (response.status, response.reason))
        else:
            import server
            out = server.request(path, method, data)
        
        import web
        out = simplejson.loads(out)
        out = storify(out)
        import web
        if out.status == 'fail':
            raise ClientException(out['message'])
        else:
            return out
        
    def get(self, key, revision=None):
        """Returns properties of the thing with the specified key."""
        if revision: 
            data = {'revision': revision}
        else:
            data = None
        result = self.request('/get/' + key, data=data)['result']
        if result is None:
            raise NotFound, key
        else:
            return result
    
    def things(self, query):
        web.ctx.infobase_localmode = True
        query = simplejson.dumps(query)
        return self.request('/things', 'GET', {'query': query})['result']
                
    def versions(self, query):
        query = simplejson.dumps(query)
        versions =  self.request('/versions', 'GET', {'query': query})['result']
        
        for i in range(len(versions)):
            versions[i] = web.storage(versions[i])
            versions[i].created = parse_datetime(versions[i].created)
        return versions

    def write(self, query, comment):
        query = simplejson.dumps(query)
        return self.request('/write', 'POST', dict(query=query, comment=comment))['result']
        
    def login(self, username, password, remember):
        return self.request('/account/login', 'POST', dict(username=username, password=password))
        
    def register(self, username, displayname, email, password):
        return self.request('/account/register', 'POST', 
            dict(username=username, displayname=displayname, email=email, password=password))

    def get_user(self):
        return self.request('/account/get_user')['result']

def parse_datetime(datestring):
    """Parses datetime from isoformat.
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
        try:
            return getattr(self, name)
        except AttributeError:
            raise KeyError, name

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

    def __str__(self): return ""
    def __repr__(self): return ""

nothing = Nothing()

class Thing:
    def __init__(self, site, key, data=None, revision=None):
        self._site = site
        self.key = key
        self._data = data
        self.revision = revision
        
    def _getdata(self):
        if self._data is None:
            self._data = self._site._load(self.key, self.revision)
            self.revision = self._data['revision']
        return self._data
        
    def __getitem__(self, key):
        return self._getdata().get(key, nothing)
        
    def __setitem__(self, key, value):
        self._data[key] = value
        
    def __iter__(self):
        return iter(self._data)
        
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
    
    def __str__(self):
        return self.key
    
    def __repr__(self):
        return "<Thing: %s>" % repr(self.key)
        
class Site:
    def __init__(self, client):
        self.client = client
        self.name = client.sitename
        self.cache = {}
        
    def _load(self, key, revision=None):
        def process(value):
            if isinstance(value, list):
                return [process(v) for v in value]
            elif isinstance(value, dict):
                return Thing(self, value['key'], None)
            else:
                return value
                
        if (key, revision) not in self.cache:                
            data = self.client.get(key, revision)
            for k, v in data.items():
                data[k] = process(v)
            
            data['last_modified'] = parse_datetime(data['last_modified'])
            self.cache[key, revision] = data
        return self.cache[key, revision]
        
    def get(self, key, revision=None, lazy=False):
        try:
            thing = Thing(self, key, data=None, revision=revision)
            if not lazy:
                thing._getdata()
            return thing
        except NotFound:
            return None
    
    def new(self, key, data):
        """Creates a new thing in memory.
        """
        return Thing(self, key, data)
        
    def things(self, query):
        return self.client.things(query)
        
    def versions(self, query):
        versions = self.client.versions(query)
        for v in versions:
            author = v.author
            v.author = v.author and self.get(v.author, lazy=True)
        return versions
        
    def login(self, username, password, remember=False):
        return self.client.login(username, password, remember)
    
    def register(self, username, displayname, email, password):
        return self.client.register(username, displayname, email, password)
        
    def get_user(self):
        u = self.client.get_user()
        return u and self.get(u)
        
    def write(self, query, comment=None):
        #@@ quick hack to run hooks on save
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
                _run_hooks('before_new_version', t)

        result = self.client.write(query, comment)

        if isinstance(query, dict) and type is not None:
            _run_hooks('on_new_version', t)
        return result

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
    import web
    web.config.db_parameters = dict(dbn='postgres', db='infobase', user='anand', pw='') 
    web.config.db_printing = True
    web.load()
    site = Site(Client(None, 'infogami.org'))
    print site.client.get('', 2)
