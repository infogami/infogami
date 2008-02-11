"""Infobase client."""
import httplib, urllib
import simplejson
import web

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
            if data and method == 'GET':
                path += '?' + urllib.urlencode(data)
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
        import web
        if out['status'] == 'fail':
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

    def write(self, query):
        query = simplejson.dumps(query)
        return self.request('/write', 'POST', query)

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
    
    def new(self, key, type):
        return Thing(self, key, {'type': type})
        
    def things(self, query):
        return self.client.things(query)
        
    def versions(self, query):
        return self.client.versions(query)

    def write(self, query):
        import web
        return self.client.write(query)
    
    def new(self, path, data):
        """Creates a new thing in memory.
        """
        return Thing(self, path, data=data)      

if __name__ == "__main__":
    import web
    web.config.db_parameters = dict(dbn='postgres', db='infobase', user='anand', pw='') 
    web.config.db_printing = True
    web.load()
    site = Site(Client(None, 'infogami.org'))
    print site.client.get('', 2)
