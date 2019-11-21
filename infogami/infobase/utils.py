"""Generic utilities.
"""
from __future__ import print_function
import datetime
import re
import web


def parse_datetime(value):
    """Creates datetime object from isoformat.

        >>> t = '2008-01-01T01:01:01.010101'
        >>> parse_datetime(t).isoformat()
        '2008-01-01T01:01:01.010101'
    """
    if isinstance(value, datetime.datetime):
        return value
    else:
        tokens = re.split(r'-|T|:|\.| ', value)
        return datetime.datetime(*map(int, tokens))

def parse_boolean(value):
    return web.safeunicode(value).lower() in ["1", "true"]

def dict_diff(d1, d2):
    """Compares 2 dictionaries and returns the following.

        * all keys in d1 whose values are changed in d2
        * all keys in d1 which have same values in d2
        * all keys in d2 whose values are changed in d1

        >>> a, b, c = dict_diff({'x': 1, 'y': 2, 'z': 3}, {'x': 11, 'z': 3, 'w': 23})
        >>> sorted(a), sorted(b), sorted(c)
        (['x', 'y'], ['z'], ['w', 'x'])
    """
    same = set(k for k in d1 if d1[k] == d2.get(k))
    left = set(d1.keys()).difference(same)
    right = set(d2.keys()).difference(same)
    return left, same, right

def pprint(obj):
    """Pretty prints given object.
    >>> pprint(1)
    1
    >>> pprint("hello")
    'hello'
    >>> pprint([1, 2, 3])
    [1, 2, 3]
    >>> pprint({'x': 1, 'y': 2})
    {
        'x': 1,
        'y': 2
    }
    >>> pprint([dict(x=1, y=2), dict(c=1, a=2)])
    [{
        'x': 1,
        'y': 2
    }, {
        'a': 2,
        'c': 1
    }]
    >>> pprint({'x': 1, 'y': {'a': 1, 'b': 2}, 'z': 3})
    {
        'x': 1,
        'y': {
            'a': 1,
            'b': 2
        },
        'z': 3
    }
    >>> pprint({})
    {
    }
    """
    print(prepr(obj))

def prepr(obj, indent=""):
    """Pretty representaion."""
    if isinstance(obj, list):
        return "[" + ", ".join(prepr(x, indent) for x in obj) + "]"
    elif isinstance(obj, tuple):
        return "(" + ", ".join(prepr(x, indent) for x in obj) + ")"
    elif isinstance(obj, dict):
        if hasattr(obj, '__prepr__'):
            return obj.__prepr__()
        else:
            indent = indent + "    "
            items = ["\n" + indent + prepr(k) + ": " + prepr(obj[k], indent) for k in sorted(obj.keys())]
            return '{' + ",".join(items) + "\n" + indent[4:] + "}"
    else:
        return repr(obj)

def flatten(nested_list, result=None):
    """Flattens a nested list.::

        >>> flatten([1, [2, 3], [4, [5, 6]]])
        [1, 2, 3, 4, 5, 6]
    """
    if result is None:
        result = []

    for x in nested_list:
        if isinstance(x, list):
            flatten(x, result)
        else:
            result.append(x)
    return result

def flatten_dict(d):
    """Flattens a dictionary.::

        >>> flatten_dict({"type": {"key": "/type/book"}, "key": "/books/foo", "authors": [{"key": "/authors/a1"}, {"key": "/authors/a2"}]})
        [('type.key', '/type/book'), ('key', '/books/foo'), ('authors.key', '/authors/a1'), ('authors.key', '/authors/a2')]
    """
    def f(key, value):
        if isinstance(value, dict):
            for k, v in value.items():
                f(key + "." + k, v)
        elif isinstance(value, list):
            for v in value:
                f(key, v)
        else:
            key = web.lstrips(key, ".")
            items.append((key, value))
    items = []
    f("", d)
    return items

def safeint(value, default):
    """Converts a string to integer. Returns the specified default value on error.::

        >>> safeint("1", 0)
        1
        >>> safeint("foo", 0)
        0
        >>> safeint(None, 0)
        0
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

if __name__ == "__main__":
    import doctest
    doctest.testmod()
