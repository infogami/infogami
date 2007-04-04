import glob, os.path
import web

from infogami import config
import view
import i18n

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

def initialize_context():
    from infogami.core import auth
    
    web.ctx.infogami_ctx = ctx = web.storage()
    ctx.error = None
    ctx.stylesheets = []
    ctx.javascripts = []
    ctx.user = auth.get_user()

def delegate(path):
    method = web.ctx.method
    initialize_context()

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
        from infogami.core import db
        site = db.get_site(config.site)
        out = getattr(modes[what](), method)(site, path)

    if out:
        print view.render_site(config.site, out)

class item:
    GET = POST = lambda self, path: delegate(path)

plugins = []

@view.public
def get_plugins():
    return [os.path.basename(p) for p in plugins]

def _load():
    """Imports the files from the plugins directory and loads templates."""
    global plugins

    plugins = ["infogami/core"]
    
    if config.plugins is not None:
        plugins += ["infogami/plugins/" + p for p in config.plugins]
    else:
        plugins += [f for f in glob.glob('infogami/plugins/*') if os.path.isdir(f)]

    for plugin in plugins:
        if os.path.isdir(plugin):
            view.load_templates(plugin)
            __import__(plugin.replace('/', '.')+'.code', globals(), locals(), ['plugins'])

def pickdb(g):
    """Looks up the db type to use in config and exports its functions."""
    instance = g[config.db_kind]()
    for k in dir(instance):
        g[k] = getattr(instance, k)

