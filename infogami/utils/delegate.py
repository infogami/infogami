import os.path
import web
from infogami import config

import template
import macro
import view
import i18n
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
        path = getattr(self, 'path', '/' + self.__name__)
        pages[path] = self

class page:
    __metaclass__ = metapage

# mode and page are just base classes.
del modes['mode']
del pages['/page']

def _keyencode(text): return text.replace(' ', '_')
def _changepath(new_path):
    return new_path + web.ctx.query

def initialize_context():
    from infogami.core import auth
    from infogami.core import db

    from infogami.infobase import client
    web.ctx.site = client.Site(client.Client(None, 'infogami.org'))
    
    context.load()
    context.error = None
    context.stylesheets = []
    context.javascripts = []
    #context.user = auth.get_user(context.site)
    context.user = None
    
    i = web.input(_method='GET', rescue="false")
    context.rescue_mode = (i.rescue.lower() == 'true')

def fakeload():
    from infogami.core import db

    web.load()
    web.ctx.ip = None
    context.load()
    context.error = None
    context.stylesheets = []
    context.javascripts = []
    context.user = None
        
def delegate(path):
    method = web.ctx.method
    if method == 'HEAD': 
        method = 'GET'
    
    initialize_context()
    
    pathx = '/' + path

    # redirect /foo/ to /foo
    if pathx != '/' and pathx.endswith('/'):
        return web.seeother(pathx[:-1])
        
    npath = os.path.normpath(pathx)
    if npath != pathx:
        web.seeother(npath)

    if pathx in pages:
        cls = pages[pathx]            
        if not hasattr(cls, method):
            return web.nomethod(method)
        out = getattr(cls(), method)()
    else: # mode
        normalized = _keyencode(path)
        if path != normalized:
            if method == 'GET':
                return web.seeother(_changepath('/' + normalized))
            elif method == 'POST':
                return web.notfound()

        what = web.input(_method='GET').get('m', 'view')
        
        #@@ move this to some better place
        from infogami.core import auth
        
        if what not in modes:
            web.seeother(web.changequery(m=None))
            return
        
        if what not in ("view", "edit") or True: #or auth.has_permission(context.site, context.user, path, what):
            cls = modes[what]            
            if not hasattr(cls, method):
                return web.nomethod(method)
            out = getattr(cls(), method)(path)
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
        i18n.load_strings(plugin.path)
        __import__(plugin.module + '.code', globals(), locals(), ['plugins'])
