import os.path
import re
import web
from infogami import config

import template
import macro
import view
import i18n
from context import context

urls = (
  '(/.*)', 'item'
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
    from infogami.core import db

    web.ctx.site = create_site()
    context.load()
    context.error = None
    context.stylesheets = []
    context.javascripts = []
    context.user = web.ctx.site.get_user()
    context.site = config.site
    context.path = web.ctx.path
    
    i = web.input(_method='GET', rescue="false")
    context.rescue_mode = (i.rescue.lower() == 'true')
    
def create_site():
    from infogami.infobase import client
    
    if config.site is None:
        site = web.ctx.host.split(':')[0] # strip port
    else:
        site = config.site
    
    web.ctx.conn = client.connect(**config.infobase_parameters)
    
    # set auto token in the connection
    if web.ctx.get('env'): # do this only if web.load is already called
        auth_token = web.cookies(infogami_session=None).infogami_session
        web.ctx.conn.set_auth_token(auth_token)
    
    return client.Site(web.ctx.conn, site)

def fakeload():
    from infogami.core import db
    web.load()
    web.ctx.ip = None
    context.load()
    context.error = None
    context.stylesheets = []
    context.javascripts = []
    context.site = config.site
    context.path = '/'
    
    # hack to disable permissions
    web.ctx.infobase_bootstrap = True
    
    context.user = None
    web.ctx.site = create_site()
    
def normpath(path):
    path = os.path.normpath(path) # correct multiple /'s and trailing /
    path = path.replace(' ', '_') # replace space with underscore
    return path
    
def delegate(path):
    method = web.ctx.method
    if method == 'HEAD': 
        method = 'GET'
    
    initialize_context()
    if not path.startswith('/api'):
        normalized = normpath(path)
        if path != normalized:
            if method == 'GET':
                return web.seeother(_changepath(normalized))
            elif method == 'POST':
                return web.notfound()

    for p in pages:
        m = re.match('^' + p + '$', path)
        if m:
            cls = pages[p]
            if not hasattr(cls, method):
                return web.nomethod(method)
            out = getattr(cls(), method)(*m.groups())
            break
    else: # mode
        what = web.input(_method='GET').get('m', 'view')
        
        if what not in modes:
            return web.seeother(web.changequery(m=None))
        
        if what == 'edit' and not web.ctx.site.can_write(path):
            out = view.permission_denied(error="You don't have permission to edit " + path + ".")
        else:
            cls = modes[what]            
            if not hasattr(cls, method):
                return web.nomethod(method)
            out = getattr(cls(), method)(path)
    if out is not None:
        if isinstance(out, basestring):
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

def admin_login(site=None):
    site = site or web.ctx.site
    web.ctx.admin_mode = True
    web.ctx.ip = '127.0.0.1'
    web.ctx.site.login('admin', config.admin_password)
    