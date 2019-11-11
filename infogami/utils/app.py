"""Infogami application.
"""
import collections
import os
import re

import simplejson

import web

from infogami.utils import flash
import six

urls = ("/.*", "item")
app = web.application(urls, globals(), autoreload=False)

import delegate as infogami_delegate  # create app before importing delegate

# magical metaclasses for registering special paths and modes.
# Whenever any class extends from page/mode, an entry is added to pages/modes.
modes = {}
pages = {}
views = collections.defaultdict(dict)

encodings = set()
media_types = {"application/json": "json"}

class metapage(type):
    def __init__(self, *a, **kw):
        type.__init__(self, *a, **kw)

        enc = getattr(self, 'encoding', None)
        path = getattr(self, 'path', '/' + self.__name__)

        encodings.add(enc)
        pages.setdefault(path, {})
        pages[path][enc] = self

class metamode(type):
    def __init__(self, *a, **kw):
        type.__init__(self, *a, **kw)

        enc = getattr(self, 'encoding', None)
        name = getattr(self, 'name', self.__name__)

        encodings.add(enc)
        modes.setdefault(name, {})
        modes[name][enc] = self

class metaview(type):
    def __init__(self, *a, **kw):
        type.__init__(self, *a, **kw)

        suffix = getattr(self, 'suffix', self.__name__)

        if suffix:
            if self.types is None:
                views[suffix][None] = self
            else:
                for t in self.types:
                    views[suffix][t] = self


class mode(six.with_metaclass(metamode)):
    def HEAD(self, *a):
        return self.GET(*a)

    def GET(self, *a):
        return web.nomethod(web.ctx.method)

class page(six.with_metaclass(metapage)):
    def HEAD(self, *a):
        return self.GET(*a)

    def GET(self, *a):
        return web.nomethod(web.ctx.method)

class view(six.with_metaclass(metaview)):
    suffix = None
    types = None

    def emit_json(self, data):
        web.header('Content-Type', 'application/json')
        return infogami_delegate.RawText(simplejson.dumps(data))

    def delegate(self, page):
        converters = {"json" : self.emit_json}
        method = web.ctx.method.upper()
        f = getattr(self, method, None)
        encoding = find_encoding()
        if encoding and hasattr(self, "%s_%s" % (method,encoding.lower())):
            f = getattr(self, "%s_%s" % (method, encoding.lower()))
        if f:
            ret = f(page)
            converter = converters.get(encoding)
            if converter:
                ret = converter(ret)
            return ret
        else:
            raise web.nomethod(web.ctx.method)

@web.memoize
def get_sorted_paths():
    """Sort path such that wildcards go at the end.
    This is called only once. After that the value is memoized.
    """
    return sorted(pages, key=lambda path: ('.*' in path, path))

def find_page():
    path = web.ctx.path
    encoding = web.ctx.get('encoding')

    # I don't about this mode.
    if encoding not in encodings:
        raise web.HTTPError("406 Not Acceptable", {})

    # encoding can be specified as part of path, strip the encoding part of path.
    if encoding:
        path = web.rstrips(path, "." + encoding)

    for p in get_sorted_paths():
        m = web.re_compile('^' + p + '$').match(path)
        if m:
            cls = pages[p].get(encoding) or pages[p].get(None)
            args = m.groups()

            # FeatureFlags support.
            # A handler can be enabled only if a feature is active.
            if hasattr(cls, "is_enabled") and bool(cls().is_enabled()) is False:
               continue

            return cls, args
    return None, None

def find_mode():
    what = web.input(_method='GET').get('m', 'view')

    path = web.ctx.path
    encoding = web.ctx.get('encoding')

    # I don't about this mode.
    if encoding not in encodings:
        raise web.HTTPError("406 Not Acceptable", {})

    # encoding can be specified as part of path, strip the encoding part of path.
    if encoding:
        path = web.rstrips(path, "." + encoding)

    if what in modes:
        cls = modes[what].get(encoding)

        # mode is available, but not for the requested encoding
        if cls is None:
            raise web.HTTPError("406 Not Acceptable", {})

        args = [path]
        return cls, args
    else:
        return None, None

def find_view():
    def normalize_suffix(s):
        if "." in s:
            return s.split(".")[0]
        else:
            return s
    path = web.ctx.path
    key, suffix = path.rsplit("/", 1)
    suffix = normalize_suffix(suffix) # Review this!
    if key and suffix in views:
        page = web.ctx.site.get(key)
        d = views[suffix]
        if not page:
            raise app.notfound(create = False)
        type_key = page.type.key
        handler = d.get(type_key) or d.get(None)
        if not handler:
            raise app.notfound(create = False)
        return handler, [page]
    return None, None

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
    cls, args = find_page()
    if cls is None: # Check for view handlers
        cls, args = find_view()
    if cls is None: # Check for mode handlers
        cls, args = find_mode()
    if cls is None:
        raise web.seeother(web.changequery(m=None))
    elif hasattr(cls, "delegate"):
        return cls().delegate(*args)
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
        path.encode('utf-8')
    except UnicodeEncodeError:
        return '/'

    # path is taken as empty by web.py dev server when given path starts with //
    if path == '':
        return '/'

    # correct trailing / and ..s in the path
    path = os.path.normpath(path)
    # os.path.normpath doesn't remove double/triple /'s at the begining
    path = path.replace("///", "/").replace("//", "/")
    path = path.replace(' ', '_') # replace space with underscore
    path = path.replace('\n', '_').replace('\r', '_')
    return path

def path_processor(handler):
    """Processor to make sure path is normalized."""
    npath = normpath(web.ctx.path)
    if npath != web.ctx.path:
        if web.ctx.method in ['GET' or 'HEAD']:
            # give absolute url for redirect. There is a bug in web.py
            # that causes infinite redicts when web.ctx.path startswith "//"
            raise web.seeother(web.ctx.home + npath + web.ctx.query)
        else:
            raise app.notfound()
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
            except (IndexError, ValueError):
                pass

        try:
            if 'q' in d:
                d['q'] = float(d['q'])
        except ValueError:
            del d['q']

        result.append(d)
    result.sort(key=lambda m: m.get('q', 1.0), reverse=True)
    return result

def find_encoding():
    def find_from_extension():
        for enc in encodings:
            if enc is None: continue
            if web.ctx.path.endswith('.' + enc):
                return enc

    if web.ctx.method == 'GET':
        if 'HTTP_ACCEPT' in web.ctx.environ:
            accept = parse_accept(web.ctx.environ['HTTP_ACCEPT'])
            media_type = accept[0]['media_type']
        else:
            media_type = None

        if media_type in media_types:
            return media_types[media_type]
        else:
            return find_from_extension()
    else:
        content_type = web.ctx.env.get('CONTENT_TYPE')
        return media_types.get(content_type) or find_from_extension()

def encoding_processor(handler):
    web.ctx.encoding = find_encoding()
    return handler()

app.add_processor(hook_processor)
app.add_processor(path_processor)
app.add_processor(encoding_processor)
app.add_processor(flash.flash_processor)

if __name__ == '__main__':
    import doctest
    doctest.testmod()
