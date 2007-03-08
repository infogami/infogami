import glob, os.path
import web

from infogami import config
import view

urls = (
  '/(.*)', 'item'
)

modes = {}
hooks = {}
pages = {}

# I'm going to hell for this...

# Basically, what it does is it fills `modes` up so that
# `modes['edit']` returns the edit class and fills `hooks`
# so that `hooks['on_new_version']` returns a list of 
# functions registered like that.

class metamode (type):
    def __init__(self, *a, **kw):
        type.__init__(self, *a, **kw)
        modes[self.__name__] = self

class mode:
    __metaclass__ = metamode

class metapage(type):
    def __init__(self, *a, **kw):
        type.__init__(self, *a, **kw)
        pages[self.__name__] = self

class page:
    __metaclass__ = metapage

# mode and page are just base classes.
del modes['mode']
del pages['page']

class hook (object):
    def __new__(klass, name, bases, attrs):
        for thing in attrs:
            if thing.startswith('on_') or thing.startswith('before_'):
                hooks.setdefault(thing, []).append(attrs[thing])

        return web.Storage(attrs)

def run_hooks(name, *args, **kwargs):
    for hook in hooks.get(name, []):
        hook(*args, **kwargs)

def _keyencode(text): return text.replace(' ', '_')
def _changepath(new_path):
    return web.ctx.homepath + new_path + web.ctx.query

def delegate(path):
    method = web.ctx.method
    web.ctx.infogami_ctx = web.storage()
    web.ctx.infogami_ctx.error = None
    web.ctx.infogami_ctx.stylesheets = []

    if path in pages:
        out = getattr(pages[path](), method)(config.site)
    elif path.startswith('files/'):
        # quickfix
        out = None
        print view.get_static_resource(path)
    else: # mode
        normalized = _keyencode(path)
        if path != normalized:
            if method == 'GET':
                return web.seeother(_changepath('/' + normalized))
            elif method == 'POST':
                return web.notfound()

        what = web.input().get('m', 'view')
        out = getattr(modes[what](), method)(config.site, path)

    if out:
        print view.render_site(config.site, out)

class item:
    GET = POST = lambda self, path: delegate(path)

def _load():
    """Imports the files from the plugins directory and loads templates."""
    view.load_templates('infogami/utils')
    view.load_templates('infogami/core')

    from infogami.core import code
    
    for plugin in glob.glob('infogami/plugins/*'):
        if os.path.isdir(plugin):
            view.load_templates(plugin)
            __import__(plugin.replace('/', '.')+'.code', globals(), locals(), ['plugins'])

def pickdb(g):
    """Looks up the db type to use in config and exports its functions."""
    instance = g[config.db_kind]()
    for k in dir(instance):
        g[k] = getattr(instance, k)

