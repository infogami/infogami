"""
Useful datastructures.
"""

import web
import copy
from UserDict import DictMixin

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
            raise AttributeError(key)

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
            raise AttributeError(key)

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
        site = web.ctx.get('site')
        key = site and site.name
        if key not in self.__d:
            self.__d[key] = web.storage()
        return self.__d[key]

class ReadOnlyDict:
    """Dictionary wrapper to provide read-only access to a dictionary."""
    def __init__(self, d):
        self._d = d

    def __getitem__(self, key):
        return self._d[key]

    def __getattr__(self, key):
        try:
            return self._d[key]
        except KeyError:
            raise AttributeError(key)

class DictPile(DictMixin):
    """Pile of ditionaries. 
    A key in top dictionary covers the key with the same name in the bottom dictionary.

        >>> a = {'x': 1, 'y': 2}
        >>> b = {'y': 5, 'z': 6}
        >>> d = DictPile([a, b])
        >>> d['x'], d['y'], d['z'] 
        (1, 5, 6)
        >>> b['x'] = 4
        >>> d['x'], d['y'], d['z'] 
        (4, 5, 6)
        >>> c = {'x':0, 'y':1}
        >>> d.add_dict(c)
        >>> d['x'], d['y'], d['z']
        (0, 1, 6)
    """
    def __init__(self, dicts=[]):
        self.dicts = dicts[:]

    def add_dict(self, d):
        """Adds d to the pile of dicts at the top.
        """
        self.dicts.append(d)

    def __getitem__(self, key):
        for d in self.dicts[::-1]:
            if key in d:
                return d[key]
        else:
            raise KeyError(key)

    def keys(self):
        keys = set()
        for d in self.dicts:
            keys.update(d.keys())
        return list(keys)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
