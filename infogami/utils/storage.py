"""
Central Storage.

Plugin system always interferes with module reloading. 
Data collected through plugins will be lost once a module is reloaded. 
Central storage provided by this module can be used to avoid that problem.
"""

import web
import copy

class OrderedDict(dict):
    """
    A dictionary in which the insertion order of items is preserved.
    """
    _reserved = ['_keys']

    def __init__(self, d={}, **kw):
        self._keys = d.keys() + kw.keys()
        dict.__init__(self, d, **kw)

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self._keys.remove(key)

    def __setitem__(self, key, item):
        # a peculiar sharp edge from copy.deepcopy
        # we'll have our set item called without __init__
        if not hasattr(self, '_keys'):
            self._keys = [key,]
        if key not in self:
            self._keys.append(key)
        dict.__setitem__(self, key, item)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError, key

    def __setattr__(self, key, value):
        # special care special methods
        if key in self._reserved:
            self.__dict__[key] = value
        else:
            self[key] = value
    
    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError, key

    def clear(self):
        dict.clear(self)
        self._keys = []

    def popitem(self):
        if len(self._keys) == 0:
            raise KeyError('dictionary is empty')
        else:
            key = self._keys[-1]
            val = self[key]
            del self[key]
            return key, val

    def setdefault(self, key, failobj = None):
        if key not in self:
            self._keys.append(key)
        dict.setdefault(self, key, failobj)

    def update(self, d):
        for key in d.keys():
            if not self.has_key(key):
                self._keys.append(key)
        dict.update(self, d)

    def iterkeys(self):
        return iter(self._keys)

    def keys(self):
        return self._keys[:]

    def itervalues(self):
        for k in self._keys:
            yield self[k]

    def values(self):
        return list(self.itervalues())

    def iteritems(self):
        for k in self._keys:
            yield k, self[k]

    def items(self):
        return list(self.iteritems())

    def __iter__(self):
        return self.iterkeys()

    def index(self, key):
        if not self.has_key(key):
            raise KeyError(key)
        return self._keys.index(key)

class DefaultDict(dict):
    """Dictionary with a default value for unknown keys.
    Source: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/389639
        >>> a = DefaultDict(0)
        >>> a.foo
        0
        >>> a['bar']
        0
        >>> a.x = 1
        >>> a.x
        1
    """
    def __init__(self, default):
        self.default = default

    def __getitem__(self, key):
        if key in self: 
            return self.get(key)
        else:
            ## Need copy in case self.default is something like []
            return self.setdefault(key, copy.deepcopy(self.default))
    
    def __getattr__(self, key):
        # special care special methods
        if key.startswith('__'):
            return dict.__getattr__(self, key)
        else:
            return self[key]
            
    __setattr__ = dict.__setitem__

    def __copy__(self):
        copy = DefaultDict(self.default)
        copy.update(self)
        return copy

storage = DefaultDict(OrderedDict())    

class SiteLocalDict:
    """
    Takes a dictionary that maps sites to objects.
    When somebody tries to get or set an attribute or item 
    of the SiteLocalDict, it passes it on to the object 
    for the active site in dictionary.
    Active site is found from `context.site`.
    see infogami.utils.context.context
    """    
    def __init__(self):
        self.__dict__['_SiteLocalDict__d'] = {}
        
    def __getattr__(self, name):
        return getattr(self._getd(), name)
        
    def __setattr__(self, name, value):
        setattr(self._getd(), name, value)

    def __delattr__(self, name):
        delattr(self._getd(), name)
        
    def _getd(self):
        from context import context
        site = getattr(context, 'site', None)
        site_id = site and site.id
        if site_id not in self.__d:
            self.__d[site_id] = web.storage(self.__d.get(None, {}))
        return self.__d[site_id]
            
if __name__ == "__main__":
    import doctest
    doctest.testmod()
    