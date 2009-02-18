
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

encodings = set()
media_types = {"application/json": "json"}

class metapage(type):
    def __init__(self, *a, **kw):
        type.__init__(self, *a, **kw)
        path = getattr(self, 'path', '/' + self.__name__)
        pages[path] = self

class metamode (type):
    def __init__(self, *a, **kw):
        type.__init__(self, *a, **kw)

        enc = getattr(self, 'encoding', None)        
        name = getattr(self, 'name', self.__name__)
        
        encodings.add(enc)
        modes.setdefault(enc, {})
        modes[enc][name] = self

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
        
def find_page():
    for p in pages:
        m = re.match('^' + p + '$', web.ctx.path)
        if m:
            cls = pages[p]
            args = m.groups()
            return cls, args
    return None, None

def find_mode():
    what = web.input(_method='GET').get('m', 'view')
    
    path = web.ctx.path
    encoding = web.ctx.get('encoding')
    
    # I don't about this mode.
    if encoding not in modes:
        raise web.HTTPError("406 Not Acceptable", {})
    
    # encoding can be specified as part of path, strip the encoding part of path.
    if encoding:
        path = web.rstrips(path, "." + encoding)
        
    # mode present for requested encoding
    if what in modes[encoding]:
        cls = modes[encoding][what]
        args = [path]
        return cls, args
    # mode is available, but not for the requested encoding
    elif what in modes[None]:    
        raise web.HTTPError("406 Not Acceptable", {})
    else:
        return None, None

# mode and page are just base classes.
del modes[None]['mode']
del pages['/page']

class item:
    HEAD = GET = POST = PUT = DELETE = lambda self: delegate()

def delegate():
    """Delegate the request to appropriate class."""
    path = web.ctx.path
    method = web.ctx.method

    # look for special pages
    cls, args = find_page()
    if cls is None:
        cls, args = find_mode()
        
    if cls is None:
        raise web.seeother(web.changequery(m=None))
    elif not hasattr(cls, method):
        raise web.nomethod(method)
    else:
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
            
def parse_accept(header):
    """Parses Accept: header.
    
        >>> parse_accept("text/plain; q=0.5, text/html")
        [{'media_type': 'text/html'}, {'q': 0.5, 'media_type': 'text/plain'}]
    """
    result= []
    for media_range in header.split(','):
        parts = media_range.split(';')
        media_type = parts.pop(0).strip()
        d = {'media_type': media_type}
        for part in parts:
            try:
                k, v = part.split('=')
                d[k.strip()] = v.strip()
            except IndexError:
                pass
                
        if 'q' in d:
            d['q'] = float(d['q'])
        result.append(d)
    result.sort(key=lambda m: m.get('q', 1.0), reverse=True)
    return result
            
def find_encoding():
    if web.ctx.method == 'GET':
        if 'HTTP_ACCEPT' in web.ctx.environ:
            accept = parse_accept(web.ctx.environ['HTTP_ACCEPT'])
            media_type = accept[0]['media_type']
            if media_type in media_types:
                return media_types[media_type]
    
        for enc in encodings:
            if enc is None: continue
            if web.ctx.path.endswith('.' + enc):
                return enc
    else:
        content_type = web.ctx.env.get('CONTENT_TYPE')
        return media_types.get(content_type)

def encoding_processor(handler):
    web.ctx.encoding = find_encoding()
    return handler()

app.add_processor(hook_processor)
app.add_processor(path_processor)
app.add_processor(encoding_processor)
if __name__ == '__main__':
    import doctest
    doctest.testmod()