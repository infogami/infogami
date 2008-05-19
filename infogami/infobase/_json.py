r"""
Wrapper to simplejson to fix unicode/utf-8 issues in python 2.4.

See Bug#231831 for details.


    >>> loads(dumps(u'\u1234'))
    u'\u1234'
    >>> loads(dumps(u'\u1234'.encode('utf-8')))
    u'\u1234'
    >>> loads(dumps({'x': u'\u1234'.encode('utf-8')}))
    {u'x': u'\u1234'}
"""
import simplejson

def unicodify(d):
    """Converts all utf-8 encoded strings to unicode recursively."""
    if isinstance(d, dict):
        return dict((k, unicodify(v)) for k, v in d.iteritems())
    elif isinstance(d, list):
        return [unicodify(x) for x in d]
    elif isinstance(d, str):
        return d.decode('utf-8')
    else:
        return d

def dumps(obj, **kw):
    return simplejson.dumps(unicodify(obj), **kw)

def loads(s, **kw):
    return simplejson.loads(s, **kw)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
