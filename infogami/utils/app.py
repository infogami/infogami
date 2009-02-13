
"""Infogami application.
"""
import web
import os
import re

urls = ("/.*", "item")
app = web.application(urls, globals(), autoreload=False)

# magical metaclasses for registering special paths and modes.
# Whenever any class extends from page/mode, an entry is added to pages/modes.
modes = {}
pages = {}

class metapage(type):
    def __init__(self, *a, **kw):
        type.__init__(self, *a, **kw)
        path = getattr(self, 'path', '/' + self.__name__)
        pages[path] = self

class metamode (type):
    def __init__(self, *a, **kw):
        type.__init__(self, *a, **kw)
        modes[self.__name__] = self
        
class mode:
    __metaclass__ = metamode
    
    def HEAD(self, *a):
        return self.GET(*a)
        
    def GET(self, *a):
        return web.nomethod(web.ctx.method)        

class page:
    __metaclass__ = metapage

    def HEAD(self, *a):
        return self.GET(*a)
        
    def GET(self, *a):
        return web.nomethod(web.ctx.method)        

# mode and page are just base classes.
del modes['mode']
del pages['/page']

class item:
    HEAD = GET = POST = PUT = DELETE = lambda self: delegate()

def delegate():
    """Delegate the request to appropriate class."""
    path = web.ctx.path
    method = web.ctx.method

    # look for special pages
    for p in pages:
        m = re.match('^' + p + '$', path)
        if m:
            cls = pages[p]
            args = m.groups()
            break
    else:
        # look for modes
        what = web.input(_method='GET').get('m', 'view')
        if what not in modes:
            raise web.seeother(web.changequery(m=None))        
        cls = modes[what]
        args = [path]

    if not hasattr(cls, method):
        raise web.nomethod(method)
    return getattr(cls(), method)(*args)

##  processors

def normpath(path):
    """Normalized path.
    
        >>> normpath("/a b")
        '/a_b'
        >>> normpath("/a//b")
        '/a/b'
        >>> normpath("//a/b/")
        '/a/b'
    """
    try:
        # take care of bad unicode values in urls
        path.decode('utf-8')
    except UnicodeDecodeError:
        return '/'

    # correct trailing / and ..s in the path
    path = os.path.normpath(path)
    # os.path.normpath doesn't remove double/triple /'s at the begining    
    path = path.replace("///", "/").replace("//", "/")
    path = path.replace(' ', '_') # replace space with underscore
    return path
    
def path_processor(handler):
    """Processor to make sure path is normalized."""
    npath = normpath(web.ctx.path)
    if npath != web.ctx.path:
        if web.ctx.method in ['GET' or 'HEAD']:
            raise web.seeother(npath + web.ctx.query)
        else:
            raise web.notfound()
    else:
        return handler()

# setup load and unload hooks for legacy code
web._loadhooks = {}
web.unloadhooks = {}
web.load = lambda: None

def hook_processor(handler):
    for h in web._loadhooks.values():
        h()
    try:
        return handler()
    finally:
        for h in web.unloadhooks.values():
            h()

app.add_processor(hook_processor)
app.add_processor(path_processor)

if __name__ == '__main__':
    import doctest
    doctest.testmod()