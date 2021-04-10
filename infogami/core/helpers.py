"""
Generic Utilities.
"""

from six import iteritems


class xdict:
    """Dictionary wrapper to give sorted repr.
    Used for doctest.
    """

    def __init__(self, d):
        self.d = d

    def __repr__(self):
        def f(d):
            if isinstance(d, dict):
                return xdict(d)
            else:
                return d

        return (
            '{'
            + ", ".join(["'%s': %s" % (k, f(v)) for k, v in sorted(self.d.items())])
            + '}'
        )


def flatten(d):
    """Make a dictionary flat.

    >>> d = {'a': 1, 'b': [2, 3], 'c': {'x': 4, 'y': 5}}
    >>> xdict(flatten(d))
    {'a': 1, 'b#0': 2, 'b#1': 3, 'c.x': 4, 'c.y': 5}
    """

    def traverse(d, prefix, delim, visit):
        for k, v in iteritems(d):
            k = str(k)
            if isinstance(v, dict):
                traverse(v, prefix + delim + k, '.', visit)
            elif isinstance(v, list):
                traverse(betterlist(v), prefix + delim + k, '#', visit)
            else:
                visit(prefix + delim + k, v)

    def visit(k, v):
        d2[k] = v

    d2 = {}
    traverse(d, "", "", visit)
    return d2


def unflatten(d):
    """Inverse of flatten.

    >>> xdict(unflatten({'a': 1, 'b#0': 2, 'b#1': 3, 'c.x': 4, 'c.y': 5}))
    {'a': 1, 'b': [2, 3], 'c': {'x': 4, 'y': 5}}
    >>> unflatten({'a#1#2.b': 1})
    {'a': [None, [None, None, {'b': 1}]]}
    """

    def setdefault(d, k, v):
        # error check: This can happen when d has both foo.x and foo as keys
        if not isinstance(d, (dict, betterlist)):
            return

        if '.' in k:
            a, b = k.split('.', 1)
            return setdefault(setdefault(d, a, {}), b, v)
        elif '#' in k:
            a, b = k.split('#', 1)
            return setdefault(setdefault(d, a, betterlist()), b, v)
        else:
            return d.setdefault(k, v)

    d2 = {}
    for k, v in iteritems(d):
        setdefault(d2, k, v)
    return d2


class betterlist(list):
    """List with dict like setdefault method."""

    def fill(self, size):
        while len(self) < size:
            self.append(None)

    def setdefault(self, index, value):
        index = int(index)
        self.fill(index + 1)
        if self[index] is None:
            self[index] = value
        return self[index]

    def iteritems(self):
        return enumerate(self)

    def items(self):
        return list(self.iteritems())  # Works on both Python 2 and 3


def trim(x):
    """Remove empty elements from a list or dictionary.

    >>> trim([2, 3, None, None, '', 42])
    [2, 3, 42]
    >>> trim([{'x': 1}, {'x': ''}, {'x': 3}])
    [{'x': 1}, {'x': 3}]
    >>> trim({'x': 1, 'y': '', 'z': ['a', '', 'b']})
    {'x': 1, 'z': ['a', 'b']}
    >>> trim(unflatten({'a#1#2.b': 1}))
    {'a': [[{'b': 1}]]}
    >>> trim(flatten(unflatten({'a#1#2.b': 1})))
    {'a#1#2.b': 1}
    """

    def trimlist(x):
        y = []
        for v in x:
            if isinstance(v, list):
                v = trimlist(v)
            elif isinstance(v, dict):
                v = trimdict(v)
            if v:
                y.append(v)
        return y

    def trimdict(x):
        y = {}
        for k, v in iteritems(x):
            if isinstance(v, list):
                v = trimlist(v)
            elif isinstance(v, dict):
                v = trimdict(v)
            if v:
                y[k] = v
        return y

    if isinstance(x, list):
        return trimlist(x)
    elif isinstance(x, dict):
        return trimdict(x)
    else:
        return x


def subdict(d, keys):
    """Subset like operation on dictionary.

    >>> subdict({'a': 1, 'b': 2, 'c': 3}, ['a', 'c'])
    {'a': 1, 'c': 3}
    >>> subdict({'a': 1, 'b': 2, 'c': 3}, ['a', 'c', 'd'])
    {'a': 1, 'c': 3}
    """
    return dict((k, d[k]) for k in keys if k in d)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
