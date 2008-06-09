"""
Infobase: structured database.

Infobase contains multiple sites and each site can store any number of objects. 
Each object has a key, that is unique to the site it belongs.
"""
import web
from multiple_insert import multiple_insert
from cache import LRU
import logger
import config
import datetime

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
    if config.query_timeout:
        web.query("SELECT set_config('statement_timeout', $query_timeout, false)", dict(query_timeout=config.query_timeout))
            
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
        
class CacheStore(object):
    """Store for managing different caches for Infobase. 
    Each site in infobase maintains multiple caches (key, thing, things and versions).
    
        >>> store = CacheStore()
        >>> store.get_cache(1, "key").keys()
        []
        >>> things_cache = store.get_cache(1, 'things')
        >>> things_cache['x'] = 1
        >>> things_cache['things']['x']
        1
        >>> things_cache.keys()
        ['x']
    """
    def __init__(self):
        self.store = {}
        
    def get_cache(self, site_id, name):
        """Returns cache for specified site_id and name."""
        if (site_id, name) not in self.store:
            self.store[site_id, name] = self.create_cache(name)
        return self.store[site_id, name]
        
    def clear(self):
        self.store = {}
        
    def create_cache(self, name):
        size = getattr(config, '%s_cache_size' % name, None) or config.default_cache_size
        return LRU(size)
                                
class Infobase:
    def __init__(self):
        self.cache = {}
        
        if config.logroot:
            self.logger = logger.Logger(config.logroot, compress=config.compress_log)
        else:
            self.logger = logger.DummyLogger()
                    
    def get_site(self, name):
        if name not in self.cache:
            d = web.select('site', where='name=$name', vars=locals())
            if d:
                s = d[0]
                self.cache[name] = Infosite(self, s.id, s.name, s.secret_key)
            else:
                raise SiteNotFound(name)
        
        return self.cache[name]

    def create_site(self, name, admin_password):
        import bootstrap
        secret_key = self.randomkey()
        try:
            web.transact()
            id = web.insert('site', name=name, secret_key=secret_key)
            site = Infosite(self, id, name, secret_key)
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

class Infosite(object):
    _class = None
    
    def __new__(cls, *a, **kw):
        """Overiding __new__ to allow creating a subclass of Infosite instead of Infosite when Infosite(..) is called.
        To install a new class set `Infosite._class = NewInfosite` before the system initialization.
        """
        if cls is Infosite:
            cls = Infosite._class or Infosite
        return object.__new__(cls, *a, **kw)
            
    def __init__(self, infobase, id, name, secret_key):
        self.cache_store = CacheStore()
        
        self.key_cache = self.cache_store.get_cache(id, 'key')
        self.thing_cache = self.cache_store.get_cache(id, 'thing')
        self.things_cache = self.cache_store.get_cache(id, 'things')
        self.versions_cache = self.cache_store.get_cache(id, 'versions')
        
        self.id = id
        self.name = name
        self.secret_key = secret_key
        self.logger = infobase.logger
        
    def get(self, key):
        """Same as withKey, but returns None instead of raising exception when object is not found."""
        try:
            return self.withKey(key)
        except NotFound:
            return None
    
    def _with(self, d, revision):
        assert revision is None or isinstance(revision, int), "revision must be integer"
            
        #@@ is this the right thing to do here?
        #@@ may be there should be error codes and this should raise no_such_revision error
        if revision is not None and revision > d.latest_revision:
            revision = None
        
        thing = Thing(self, d.id, d.key, d.last_modified, d.latest_revision, revision=revision)
                
        self.key_cache[thing.key] = thing.id
        self.thing_cache[thing.id, revision] = thing
        if revision is None:
            self.thing_cache[thing.id, thing.latest_revision] = thing
        return thing

    def withKey(self, key, revision=None, lazy=False):
        assert key.startswith('/'), 'Bad key: ' + repr(key)

        # if id is known for that key, redirect to withID
        if key in self.key_cache:
            id = self.key_cache[key]
            if id is not None:
                return self.withID(id, revision)
            else:
                raise NotFound, key

        try:
            d = web.select('thing', where="site_id=$self.id AND key=$key", vars=locals())[0]
        except IndexError:
            self.key_cache[key] = None
            raise NotFound, key

        return self._with(d, revision=revision)
        
    def withID(self, id, revision=None):
        if (id, revision) in self.thing_cache:
            return self.thing_cache[id, revision]
            
        try:
            d = web.select('thing', where="site_id=$self.id AND id=$id", vars=locals())[0]
        except IndexError:
            raise NotFound, id

        return self._with(d, revision=revision)
        
    def _run_query(self, cache, query):
        if query not in cache:
            result = query.execute()
            cache[query] = result
        else:
            result = cache[query]
        return result

    def things(self, query):
        assert isinstance(query, dict)
        from readquery import Things
        query = Things(self, query)
        return self._run_query(self.things_cache, query)
        
    def versions(self, query):
        assert isinstance(query, dict)
        from readquery import Versions
        query = Versions(self, query)
        return self._run_query(self.versions_cache, query)

    def write(self, query, comment=None, machine_comment=None, timestamp=None):
        a = self.get_account_manager()
        return self._write(query, comment, machine_comment, a.get_user(), web.ctx.get("ip"), timestamp)
        
    def _write(self, query, comment=None, machine_comment=None, author=None, ip=None, timestamp=None, log=True):
        web.transact()
        try:
            import writequery
            timestamp = timestamp or datetime.datetime.utcnow()
            ctx = writequery.Context(self, 
                author=author, ip=ip, 
                comment=comment, machine_comment=machine_comment,
                timestamp=timestamp)
            result = ctx.execute(query)
            
            modified = ctx.modified_objects()
            self.invalidate(modified, ctx.versions.values())
            log and self.logger.on_write(self, timestamp, query, result, comment, machine_comment, author, web.ctx.get('ip'))
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
            self.key_cache[o.key] = o.id
            if (o.id, None) in self.thing_cache:
                del self.thing_cache[o.id, None]
                
        for q in self.things_cache.keys():
            for o in objects:
                if q in self.things_cache and (q.matches(o) or o.key in self.things_cache[q]):
                    del self.things_cache[q]
                    
        for q in self.versions_cache.keys():
            for v in versions:
                if q in self.versions_cache and q.matches(v):
                    del self.versions_cache[q]
        
    def get_account_manager(self):
        import account
        return account.AccountManager(self)
        