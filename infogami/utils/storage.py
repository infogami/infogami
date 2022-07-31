"""
Useful datastructures.
"""

from collections import OrderedDict, defaultdict
from collections.abc import Mapping

import web

storage: dict[str, dict] = defaultdict(OrderedDict)


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


class DictPile(Mapping):
    """Pile of ditionaries.
    A key in top dictionary covers the key with the same name in the bottom dictionary.

        >>> a = {'x': 1, 'y': 2}
        >>> b = {'y': 5, 'z': 6}
        >>> d = DictPile([a, b])
        >>> len(d)
        3
        >>> list(iter(d)) == list(d.keys())
        True
        >>> list(iter(d)) == list(d)
        True
        >>> d['x'], d['y'], d['z']
        (1, 5, 6)
        >>> b['x'] = 4
        >>> d['x'], d['y'], d['z']
        (4, 5, 6)
        >>> c = {'x':0, 'y':1}
        >>> d.add_dict(c)
        >>> d['x'], d['y'], d['z']
        (0, 1, 6)
        >>> d.add_dict({'new': 99})
        >>> len(d)
        4
        >>> list(iter(d)) == list(d.keys())
        True
        >>> list(iter(d)) == list(d)
        True
        >>> 'new' in d
        True
        >>> 'nope' in d
        False
    """

    def __init__(self, dicts=[]):
        self.dicts = dicts[:]

    def add_dict(self, d):
        """Adds d to the pile of dicts at the top."""
        self.dicts.append(d)

    def __getitem__(self, key):
        for d in self.dicts[::-1]:
            if key in d:
                return d[key]
        else:
            raise KeyError(key)

    def __iter__(self):
        yield from self.keys()

    def __len__(self):
        return len(self.keys())

    def keys(self):
        keys = set()
        for d in self.dicts:
            keys.update(d.keys())
        return list(keys)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
