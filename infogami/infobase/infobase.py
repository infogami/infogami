"""
Infobase: structured database.

Infobase contains multiple sites and each site can store any number of objects. 
Each object has a key, that is unique to the site it belongs.
"""
import web
from multiple_insert import multiple_insert
from cache import LRU
import logger

KEYWORDS = ["id", 
    "action", "create", "update", "insert", "delete", 
    "limit", "offset", "index", "sort", 
    "revision", "version", "history", 
    "value", "metadata"
]

hooks = []
    
TYPES = {}
TYPES['/type/key'] = 1
TYPES['/type/string'] = 2
TYPES['/type/text'] = 3
TYPES['/type/uri'] = 4
TYPES['/type/boolean'] = 5
TYPES['/type/int'] = 6
TYPES['/type/float'] = 7
TYPES['/type/datetime'] = 8

DATATYPE_REFERENCE = 0
TYPE_REFERENCE = 0
TYPE_KEY = 1
TYPE_STRING = 2
TYPE_TEXT = 3
TYPE_URI = 4
TYPE_BOOLEAN = 5
TYPE_INT = 6
TYPE_FLOAT = 7
TYPE_DATETIME = 8

MAX_INT = (2 ** 31) - 1
MAX_REVISION = MAX_INT - 1

class InfobaseException(Exception):
    pass
    
class SiteNotFound(InfobaseException):
    pass
    
class NotFound(InfobaseException):
    pass

class AlreadyExists(InfobaseException):
    pass
    
class PermissionDenied(InfobaseException):
    pass
    
def loadhook():
    ctx = web.storage()
    ctx.dirty = []
    web.ctx.infobase_ctx = ctx
            
web.loadhooks['infobase_hook'] = loadhook

def transactify(f):
    def g(*a, **kw):
        web.transact()
        try:
            result = f(*a, **kw)
        except:
            web.rollback()
            raise
        else:
            web.commit()
        return result
    return g
    
class BaseCache:
    """Base class for Infobase cache.
    Different kind of values can be stored in the cache. The kind of the value is specified by the tag.
    The cache implementation can choose to have individual storage for each tag or a unified storage.
    """
    def get(self, tag, key, default=None):
        """Returns a value with the specified tag and key. Returns default, if key is not found.
        """
        raise NotImplementedError
        
    def set(self, tag, key, value):
        """Sets a value of a new entry.
        """
        raise NotImplementedError
        
    def remove(self, tag, key):
        """Removes an element from the cache."""
        raise NotImplementedError
        
    def keys(self, tag):
        """Return keys for all the values in the cache with the specified tag."""
        raise NotImplementedError
        
    def clear(self):
        """Clears the cache."""
        raise NotImplementedError
        
    def __getitem__(self, key):
        tag, key = key
        return self.get(tag, key)
        
    def __setitem__(self, key, value):
        tag, key = key
        self.set(tag, key, value)
    
    def __delitem__(self, key):
        tag, key = key
        self.remove(tag, key)
        
    def __contains__(self, key):
        tag, key = key
        return self.get(tag, key) is not None
        
class LRUCache(BaseCache):
    """An LRU implementation of cache, which uses a separate LRU cache for every tag.
    """
    def __init__(self):
        self.cache = {}
        
    def get_cache(self, tag):
        if tag not in self.cache:
            size = web.config.get('infobase_%s_cache_size' % tag) or web.config.get('infobase_default_cache_size') or 1000
            self.cache[tag] = LRU(size)
        return self.cache[tag]
        
    def clear(self):
        self.cache = {}
        
    def get(self, tag, key, default=None):
        return self.get_cache(tag).get(key, default)
        
    def set(self, tag, key, value):
        self.get_cache(tag)[key] = value
        
    def remove(self, tag, key):
        del self.get_cache(tag)[key]
        
    def keys(self, tag):
        return self.get_cache(tag).keys()
    
class Infobase:
    def __init__(self):
        self.cache = LRUCache()        

    def get_site(self, name):
        if ('site', name) not in self.cache:
            d = web.select('site', where='name=$name', vars=locals())
            if d:
                s = d[0]
                self.cache['site', name] = Infosite(s.id, s.name, s.secret_key)
            else:
                raise SiteNotFound(name)
        
        return self.cache['site', name]

    def create_site(self, name, admin_password):
        import bootstrap
        secret_key = self.randomkey()
        try:
            web.transact()
            id = web.insert('site', name=name, secret_key=secret_key)
            site = Infosite(id, name, secret_key)
            bootstrap.bootstrap(site, admin_password)
        except:
            import traceback
            traceback.print_exc()
            web.rollback()
            raise
        else:
            web.commit()
            return site

    def randomkey(self):
        import string, random
        chars = string.letters + string.digits
        return "".join(random.choice(chars) for i in range(25))

    def delete_site(self, name):
        pass
        
class ThingList(list):
    def get(self, key, default=None):
        for t in self:
            if t.key == key:
                return t
        return default

    def _get_value(self):
        return [t._get_value() for t in self]

class Datum(object):
    __slots__ = ['value', 'datatype']
    def __init__(self, value, datatype):
        self.value = value
        self.datatype = datatype

    def _get_value(self):
        return self.value
    
    def _get_datatype(self):
        return self.datatype
        
    def __repr__(self):
        return repr(self.value)
    __str__ = __repr__
        
class Thing:
    """Thing: an object in infobase."""
    def __init__(self, site, id, key, last_modified=None, latest_revision=None, revision=None):
        self._site = site
        self.id = id
        self.key = key
        self.last_modified = last_modified and last_modified.isoformat()
        self.latest_revision = latest_revision
        self.revision = revision or latest_revision
        self._d = None # data is loaded lazily on demand
        
    def copy(self):
        thing = Thing(self._site, self.id, self.key, None, self.latest_revision, self.revision)
        thing.last_modified = self.last_modified
        thing._d = self._d and self._d.copy()
        return thing

    def _get_value(self):
        return self.id

    def _get_datatype(self):
        return DATATYPE_REFERENCE
        
    def _load(self):
        if self._d is None:
            revision = self.revision or MAX_REVISION
            d = web.select('datum', where='thing_id=$self.id AND begin_revision <= $revision AND end_revision > $revision', order='key, ordering', vars=locals())
            d = self._parse_data(d)
            self._d = d
        
    def _get_data(self, expand=False):
        def unthingify(thing):
            if isinstance(thing, list):
                return [unthingify(x) for x in thing]
            elif isinstance(thing, Datum):
                if thing.datatype == DATATYPE_REFERENCE:
                    if expand:
                        return self._site.withID(thing.value)._get_data()
                    else:
                        return {'key': self._site.withID(thing.value).key}
                else:
                    return thing._get_value()
            else:
                return thing
        
        self._load()
        d = {
            'last_modified': self.last_modified, 
            'latest_revision': self.latest_revision,
            'revision': self.revision or self.latest_revision
        }
        for k, v in self._d.items():
            d[k] = unthingify(v)
        return d
        
    def _get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
        
    def __getitem__(self, key):
        if self._d is None:
            self._load()
        value = self._d[key]
        
        def process(value):
            """Return Thing when datatype is reference, Datum object otherwise.
            Properties of a thing are always stored as Datum objects, 
            so that it will not keep reference to any thing, which may interfere with caching.
            """
            if isinstance(value, list):
                return [process(v) for v in value]
            elif value.datatype == DATATYPE_REFERENCE:
                return self._site.withID(value.value)
            else:
                return value
                
        return process(value)
        
    def __getattr__(self, key):
        if key.startswith('__'):
            raise AttributeError, key
            
        try:
            return self[key]
        except KeyError:
            raise AttributeError, key
        
    def _parse_data(self, data):
        d = web.storage()
        for r in data:
            if r.datatype in (TYPES['/type/string'], TYPES['/type/key'], TYPES['/type/uri'], TYPES['/type/text']):
                value = Datum(r.value, r.datatype)
            elif r.datatype == TYPES['/type/int'] or r.datatype == DATATYPE_REFERENCE:
                value = Datum(int(r.value), r.datatype)
            elif r.datatype == TYPES['/type/float']:
                value = Datum(float(r.value), r.datatype)
            elif r.datatype == TYPES['/type/boolean']:
                value = Datum(bool(int(r.value)), r.datatype)
            else:
                raise Exception, "unknown datatype: %s" % r.datatype

            if r.ordering is not None:
                d.setdefault(r.key, []).append(value)
            else:
                assert r.key not in d
                d[r.key] = value

        return d
        
    def __repr__(self):
        return "<Thing: %s at %d>" % (self.key, self.id)
        
    def __str__(self):
        return self.key

    def __eq__(self, other):
        return isinstance(other, Thing) and self.id == other.id

    def __ne__(self, other):
        return not (self == other)

class Infosite:
    def __init__(self, id, name, secret_key):
        #@@ what is I want to use unified cache for all sites?
        self.cache = LRUCache() 
        self.id = id
        self.name = name
        self.secret_key = secret_key
        logroot = web.config.get('infobase_logroot', None)
        if logroot:
            self.logger = logger.Logger(self, logroot)
        else:
            self.logger = logger.DummyLogger()
        
    def get(self, key):
        """Same as withKey, but returns None instead of raising exception when object is not found."""
        try:
            return self.withKey(key)
        except NotFound:
            return None
            
    def cachify(self, thing, revision):
        if revision is None:
            self.cache['key', thing.id] = thing.key
            self.cache['thing', thing.id] = thing
        return thing

    def withKey(self, key, revision=None, lazy=False):
        assert key.startswith('/'), 'Bad key: ' + repr(key)
        
        # if id is known for that key, redirect to withID
        if ('key', key) in self.cache:
            id = self.cache[key]
            return self.withID(id, revision)
                    
        try:
            d = web.select('thing', where='site_id = $self.id AND key = $key', vars=locals())[0]
        except IndexError:
            raise NotFound, key
            
        thing = Thing(self, d.id, d.key, d.last_modified, d.latest_revision, revision=revision)
        return self.cachify(thing, revision)
        
    def withID(self, id, revision=None):
        if revision is None and ('thing', id) in self.cache:
            return self.cache['thing', id]
    
        try:
            d = web.select('thing', where='site_id=$self.id AND id=$id', vars=locals())[0]        
        except IndexError:
            raise NotFound, id
        return self.cachify(Thing(self, d.id, d.key, d.last_modified, d.latest_revision, revision=revision), revision)
        
    def _run_query(self, tag, query):
        if (tag, query) not in self.cache:
            result = query.execute()
            self.cache[tag, query] = result
        else:
            result = self.cache[tag, query]
        return result

    def things(self, query):
        assert isinstance(query, dict)
        from readquery import Things
        query = Things(self, query)
        return self._run_query('things', query)
        
    def versions(self, query):
        assert isinstance(query, dict)        
        from readquery import Versions
        query = Versions(self, query)
        return self._run_query('versions', query)

    def write(self, query, comment=None, machine_comment=None):
        web.transact()
        try:
            import writequery
            a = self.get_account_manager()
            ctx = writequery.Context(self, 
                author=a.get_user(), ip=web.ctx.get('ip'), 
                comment=comment, machine_comment=machine_comment)
            result = ctx.execute(query)
            
            modified = ctx.modified_objects()
            self.invalidate(modified, ctx.versions.values())
            self.logger.on_write(result, comment, machine_comment, a and a.get_user(), web.ctx.get('ip'))
            self.run_hooks(modified)
        except:
            web.rollback()
            raise
        else:
            web.commit()
        return result
    
    def get_permissions(self, key):
        import writequery
        a = self.get_account_manager()
        ctx = writequery.Context(self, author=a.get_user())
        return dict(write=ctx.can_write(key), admin=ctx.can_admin(key))
        
    def run_hooks(self, objects):
        for h in hooks:
            for o in objects:
                try:
                    h(o)
                except:
                    # ignore the exceptions in hooks
                    # but print traceback because "Errors should never pass silently."
                    import traceback
                    traceback.print_exc()
    
    def invalidate(self, objects, versions):
        """Invalidate the given keys from cache."""
        for o in objects:
            if ('thing', o.id) in self.cache:
                del self.cache['thing', o.id]
                
        for q in self.cache.keys('things'):
            for o in objects:
                if ('things', q) in self.cache and (q.matches(o) or o.key in self.cache['things', q]):
                    del self.cache['things', q]
                    
        for q in self.cache.keys('versions'):
            for v in versions:
                if ('versions', q) in self.cache and q.matches(v):
                    del self.cache['versions', q]
        
    def get_account_manager(self):
        import account
        return account.AccountManager(self)
        