import glob, os.path
import web, config

urls = (
  '/(.*)', 'item'
)

modes = {}
hooks = {}

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

class hook (object):
    def __new__(klass, name, bases, attrs):
        for thing in attrs:
            if thing.startswith('on_'):
                hooks.setdefault(thing, []).append(attrs[thing])

        return web.Storage(attrs)

def delegate(f):
    def idelegate(self, path):
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
            __import__(plugin.replace('/', '.')+'.code', locals(), globals(), ['plugins'])
