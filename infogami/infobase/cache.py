"""
Infobase cache.

Infobase cache contains multiple layers.

new_objects (thread-local)
special_cache
local_cache (thread-local)
global_cache

new_objects is a thread-local dictionary containing objects created in the
current request. It is stored at web.ctx.new_objects. new_objects are added
to the global cache at the end of every request. It is the responsibility of
the DBStore to populate this on write and it should also make sure that this
is cleared on write failures.

special_cache is an optional cache provided to cache most frequently accessed
objects (like types and properties) and the application is responsible to keep
it in sync.

local_cache is a thread-local cache maintained to avoid repeated requests to
global cache. This is stored at web.ctx.local_cache.

global_cache is typically expensive to access, so its access is minimized.
Typical examples of global_cache are LRU cache and memcached cache.

Any elements added to the infobase cache during a request are cached locally until the end
of that request and then they are added to the global cache.
"""

import logging

import web

from infogami.infobase import lru

logger = logging.getLogger("infobase.cache")

class NoneDict:
    def __getitem__(self, key):
        raise KeyError(key)

    def __setitem__(self, key, value):
        pass

    def update(self, d):
        pass

class MemcachedDict:
    def __init__(self, memcache_client=None, servers=[]):
        if memcache_client is None:
            import memcache
            memcache_client = memcache.Client(servers)
        self.memcache_client = memcache_client

    def __getitem__(self, key):
        key = web.safestr(key)
        value = self.memcache_client.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key, value):
        key = web.safestr(key)
        logger.debug("MemcachedDict.set: %s", key)
        self.memcache_client.set(key, value)

    def update(self, d):
        d = dict((web.safestr(k), v) for k, v in d.items())
        logger.debug("MemcachedDict.update: %s", d.keys())
        self.memcache_client.set_multi(d)

    def clear(self):
        self.memcache_client.flush_all()

_cache_classes = {}
def register_cache(type, klass):
    _cache_classes[type] = klass

register_cache('lru', lru.LRU)
register_cache('memcache', MemcachedDict)

def create_cache(type, **kw):
    klass = _cache_classes.get(type) or NoneDict
    return klass(**kw)

special_cache = {}
global_cache = lru.LRU(200)

def loadhook():
    web.ctx.new_objects = {}
    web.ctx.local_cache = {}
    web.ctx.locally_added = {}

def unloadhook():
    """Called at the end of every request."""
    d = {}
    d.update(web.ctx.locally_added)
    d.update(web.ctx.new_objects)

    if d:
        global_cache.update(d)

class Cache:
    def __getitem__(self, key):
        ctx = web.ctx
        obj = ctx.new_objects.get(key) \
            or special_cache.get(key)  \
            or ctx.local_cache.get(key) \

        if not obj:
            obj = global_cache[key]
            ctx.local_cache[key] = obj

        return obj

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        """Tests whether an element is present in the cache.
        This function call is expensive. Provided for the sake of completeness.

        Use:
            obj = cache.get(key)
            if obj is None:
                do_something()

        instead of:
            if key in cache:
                obj = cache[key]
            else:
                do_something()
        """
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __setitem__(self, key, value):
        web.ctx.local_cache[key] = value
        web.ctx.locally_added[key] = value

    def clear(self, local=False):
        """Clears the cache.
        When local=True, only the local cache is cleared.
        """
        web.ctx.locally_added.clear()
        web.ctx.local_cache.clear()
        web.ctx.new_objects.clear()
        if not local:
            global_cache.clear()
