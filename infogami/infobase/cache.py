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

import web
import lru

class NoneDict:
    def __getitem__(self, key):
        raise KeyError, key
        
    def __setitem__(self, key, value):
        pass
        
    def update(self, d):
        pass

special_cache = {}
global_cache = lru.LRU(200)

def loadhook():
    web.ctx.new_objects = {}
    web.ctx.local_cache = {}
    web.ctx.locally_added = {}
    
def unloadhook():
    """Called at the end of every request."""
    d = {}
    d.update(web.ctx.new_objects)
    d.update(web.ctx.locally_added)
    
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
        except:
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
