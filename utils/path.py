import urllib
import web
from utils.view import keyencode

def _changepath(new_path):
    return web.ctx.homepath + new_path + web.ctx.query

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
