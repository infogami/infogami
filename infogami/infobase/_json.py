r"""
Wrapper to simplejson to fix unicode/utf-8 issues in python 2.4.

See Bug#231831 for details.


    >>> loads(dumps(u'\u1234'))
    u'\u1234'
    >>> loads(dumps(u'\u1234'.encode('utf-8')))
    u'\u1234'
"""
import simplejson

def dumps(obj, **kw):
    return simplejson.dumps(obj, ensure_ascii=False, *kw)

def loads(s, **kw):
    return simplejson.loads(s, **kw)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
