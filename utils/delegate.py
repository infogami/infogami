import glob, os.path
import web, config

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
            if thing.startswith('on_'):
                hooks.setdefault(thing, []).append(attrs[thing])

        return web.Storage(attrs)

def run_hooks(name, *args, **kwargs):
    for hook in hooks.get(name, []):
        hook(*args, **kwargs)

def delegate(f):
    def idelegate(self, path):
        if path in pages:
            return getattr(pages[path](), f)(config.site)
        else:
            what = web.input().get('m', 'view')
            return getattr(modes[what](), f)(config.site, path)
    return idelegate

class item:
    GET = delegate('GET')
    POST = delegate('POST')

def _load():
    """Imports the files from the plugins directory."""
    from core import code
    for plugin in glob.glob('plugins/*'):
        if os.path.isdir(plugin):
            __import__(plugin.replace('/', '.')+'.code', globals(), locals(), ['plugins'])

def pickdb(g):
    """Looks up the db type to use in config and exports its functions."""
    instance = g[config.db_kind]()
    for k in dir(instance):
        g[k] = getattr(instance, k)
