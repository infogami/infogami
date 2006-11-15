import urllib

import web

from utils.view import keyencode

# to web.py's http.py?
def _changepath(new_path):
    """
    Imagine you're at `/foo?a=1&b=2`. Then `changepath('bar')` will return
    `/bar?a=3&b=2` -- a different URL but with the same arguments.
    """
    query = web.input(_method='get')
    out = web.ctx.homepath + new_path
    if query:
        out += '?' + urllib.urlencode(query)
    return out

def normalize():
    def decorator(func): 
        def proxyfunc(self, site, path):
            normalized = keyencode(path)
            if path != normalized:
                return web.seeother(_changepath('/' + normalized))
            return func(self, site, path)
        return proxyfunc
    return decorator

def filter_unnormalized():
    def decorator(func): 
        def proxyfunc(self, site, path):
            normalized = keyencode(path)
            if path != normalized:
                return web.notfound()
            return func(self, site, path)
        return proxyfunc
    return decorator
