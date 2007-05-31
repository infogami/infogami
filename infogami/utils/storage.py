"""
Central Storage.

Plugin system always interferes with module reloading. 
Data collected through plugins will be lost once a module is reloaded. 
Central storage provided by this module can be used to avoid that problem.
"""

import web
from UserDict import DictMixin

class OrderedDict(DictMixin):
    """Dictionary that maintains the order in which the items are added.
    
    Source: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/496761
    
        >>> a = OrderedDict()
        >>> a[1] = 1
        >>> a[100] = 100
        >>> a[42] = 42
        >>> a[4] = 4
        >>> a.keys()
        [1, 100, 42, 4]
    """
    def __init__(self):
        self._keys = []
        self._data = {}

    def __setitem__(self, key, value):
        if key not in self._data:
            self._keys.append(key)
        self._data[key] = value

    def __getitem__(self, key):
        return self._data[key]

    def __delitem__(self, key):
        del self._data[key]
        self._keys.remove(key)

    def keys(self):
        return list(self._keys)

    def copy(self):
        copyDict = OrderedDict()
        copyDict._data = self._data.copy()
        copyDict._keys = self._keys[:]
        return copyDict

import copy

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
               
if __name__ == "__main__":
    import doctest
    doctest.testmod()
