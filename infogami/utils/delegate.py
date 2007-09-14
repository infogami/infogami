import os.path
import web
from infogami import config

import template
import macro
import view
from context import context

urls = (
  '/(.*)', 'item'
)

modes = {}
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

def _keyencode(text): return text.replace(' ', '_')
def _changepath(new_path):
    return new_path + web.ctx.query

def initialize_context():
    from infogami.core import auth
    from infogami.core import db
    
    context.load()
    context.error = None
    context.stylesheets = []
    context.javascripts = []
    context.site = db.get_site(config.site)
    context.user = auth.get_user(context.site)
    
    i = web.input(_mode='GET', rescue="false")
    context.rescue_mode = (i.rescue.lower() == 'true')

def fakeload():
    from infogami.core import db

    web.load()
    web.ctx.ip = ""
    context.load()
    context.error = None
    context.stylesheets = []
    context.javascripts = []
    context.user = None
    try:
        context.site = db.get_site(config.site)
    except:
        pass
        
def delegate(path):
    method = web.ctx.method
    if method == 'HEAD': 
        method = 'GET'
    
    initialize_context()

    # redirect foo/ to foo
    if path.endswith('/'):
        return web.seeother('/' + path[:-1])
        
    npath = os.path.normpath('/' + path)
    if npath != '/' + path:
        web.seeother(npath)

    if path in pages:
        out = getattr(pages[path](), method)(context.site)
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
        
        #@@ move this to some better place
        from infogami.core import auth
        
        if what not in modes:
            web.seeother(web.changequery(m=None))
            return
        
        if what not in ("view", "edit") or auth.has_permission(context.site, context.user, path, what):
            cls = modes[what]            
            if not hasattr(cls, method):
                return web.nomethod(cls)
            out = getattr(cls(), method)(context.site, path)
        else:
            #context.error = 'You do not have permission to do that.'
            return auth.login_redirect()

    if out is not None:
        if isinstance(out, str):
            out = web.template.Stowage(_str=out, title=path)
            
        if hasattr(out, 'rawtext'):
            print out.rawtext
        else:
            print view.render_site(config.site, out)

class item:
    GET = POST = lambda self, path: delegate(path)

plugins = []

@view.public
def get_plugins():
    """Return names of all the plugins."""
    return [p.name for p in plugins]

def _make_plugin(name):
    # plugin can be present in infogami/plugins directory or <pwd>/plugins directory.    
    if name == 'core':
        path = infogami_root() + '/core'
        module = 'infogami.core'
    else:
        for p in config.plugin_path:
            m = __import__(p, globals(), locals(), ['plugins'])
            path = os.path.dirname(m.__file__) + '/' + name
            module = p + '.' + name
            if os.path.isdir(path):
                break
        else:
            raise Exception, 'Plugin not found: ' + name
            
    return web.storage(name=name, path=path, module=module)

def _list_plugins(dir):
    if os.path.isdir(dir):
        return [_make_plugin(name) for name in os.listdir(dir) if os.path.isdir(dir + '/' + name)]
    else:
        return []
    
def infogami_root():
    import infogami
    return os.path.dirname(infogami.__file__)
        
def _load():
    """Imports the files from the plugins directories and loads templates."""
    global plugins
    
    plugins = [_make_plugin('core')]
    
    if config.plugins is not None:
        plugins += [_make_plugin(p) for p in config.plugins]
    else:        
        for p in config.plugin_path:
            m = __import__(p)
            root = os.path.dirname(m)
            plugins += _list_plugins(root)
            
    for plugin in plugins:
        template.load_templates(plugin.path)
        macro.load_macros(plugin.path)
        __import__(plugin.module + '.code', globals(), locals(), ['plugins'])

def pickdb(g):
    """Looks up the db type to use in config and exports its functions."""
    instance = g[config.db_kind]()
    for k in dir(instance):
        g[k] = getattr(instance, k)
