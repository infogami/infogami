import os.path

from six import string_types
import web

from infogami import config
from infogami.utils import features, i18n
from infogami.utils.app import app, mode, page  # noqa: F401
from infogami.utils.app import *  # noqa: F40 TODO (cclauss): Remove wildcard imports
from infogami.utils.context import context
from infogami.utils.view import render_site, public


def create_site():
    from infogami.infobase import client

    if config.site is None:
        site = web.ctx.host.split(':')[0]  # strip port
    else:
        site = config.site

    web.ctx.conn = client.connect(**config.infobase_parameters)

    # set auto token in the connection
    if web.ctx.get('env'):  # do this only if web.load is already called
        auth_token = web.cookies().get(config.login_cookie_name)
        web.ctx.conn.set_auth_token(auth_token)

    return client.Site(web.ctx.conn, site)


def fakeload():
    # web.load()
    app.load(dict(REQUEST_METHOD="GET", PATH_INFO="/install"))
    web.ctx.ip = None
    context.load()
    context.error = None
    context.stylesheets = []
    context.javascripts = []
    context.site = config.site
    context.path = '/'

    # hack to disable permissions
    web.ctx.disable_permisson_check = True

    context.user = None
    web.ctx.site = create_site()


def initialize_context():
    web.ctx.site = create_site()
    context.load()
    context.error = None
    context.stylesheets = []
    context.javascripts = []
    context.user = web.ctx.site.get_user()
    context.site = config.site
    context.path = web.ctx.path

    i = web.input(_method='GET', rescue="false")
    context.rescue_mode = i.rescue.lower() == 'true'


def layout_processor(handler):
    """Processor to wrap the output in site template."""
    out = handler()

    path = web.ctx.path[1:]

    if out is None:
        out = RawText("")

    if isinstance(out, string_types):
        out = web.template.TemplateResult(__body__=out)

    if isinstance(out, web.webapi.HTTPError):
        raise out

    if 'title' not in out:
        out.title = path

    # overwrite the content_type of content_type is specified in the template
    if 'content_type' in out:
        web.ctx.headers = [h for h in web.ctx.headers if h[0].lower() != 'content-type']
        web.header('Content-Type', out.content_type)

    if hasattr(out, 'rawtext'):
        html = out.rawtext
    else:
        html = render_site(config.site, out)

    # cleanup references to avoid memory leaks
    web.ctx.site._cache.clear()
    web.ctx.pop('site', None)
    web.ctx.env = {}
    context.clear()

    return html


def notfound(path=None, create=True):
    from infogami.utils import template

    path = path or web.ctx.path
    html = template.render_template("notfound", path, create=create)
    return web.notfound(render_site(config.site, html))


app.add_processor(web.loadhook(initialize_context))
app.add_processor(layout_processor)
app.add_processor(web.loadhook(features.loadhook))
app.notfound = notfound


class RawText(web.storage):
    def __init__(self, text, **kw):
        web.storage.__init__(self, rawtext=text, **kw)


plugins = []


@public
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
            if p:
                m = __import__(p, globals(), locals(), ['plugins'])
                path = os.path.dirname(m.__file__) + '/' + name
                module = p + '.' + name
            else:
                path = name
                module = name
            if os.path.isdir(path):
                break
        else:
            raise Exception('Plugin not found: ' + name)

    return web.storage(name=name, path=path, module=module)


def _make_plugin_module(modname):
    """Makes a plugin object from module name.

    This works like _make_plugin, but takes a module name instead of plugin name.
    """
    m = __import__(modname, globals(), locals(), modname.split("."))
    path = os.path.dirname(m.__file__)
    return web.storage(name=modname, path=path, module=modname)


def _list_plugins(dir):
    if os.path.isdir(dir):
        return [
            _make_plugin(name)
            for name in os.listdir(dir)
            if os.path.isdir(dir + '/' + name)
        ]
    else:
        return []


def infogami_root():
    import infogami

    return os.path.dirname(infogami.__file__)


def _load():
    """Imports the files from the plugins directories and loads templates."""
    from infogami.utils import macro, template

    global plugins

    plugins = [_make_plugin('core')]

    if config.plugins is not None:
        plugins += [_make_plugin(p) for p in config.plugins]
    else:
        for p in config.plugin_path:
            m = __import__(p)
            root = os.path.dirname(m)
            plugins += _list_plugins(root)

    if config.plugin_modules is not None:
        plugins += [_make_plugin_module(name) for name in config.plugin_modules]

    for plugin in plugins:
        template.load_templates(plugin.path, lazy=True)
        macro.load_macros(plugin.path, lazy=True)
        i18n.load_strings(plugin.path)
        __import__(plugin.module + '.code', globals(), locals(), ['plugins'])

    features.set_feature_flags(config.get("features", {}))


def admin_login(site=None):
    site = site or web.ctx.site
    web.ctx.admin_mode = True
    web.ctx.ip = '127.0.0.1'
    web.ctx.site.login('admin', config.admin_password)


exception_hooks = []


def add_exception_hook(hook):
    exception_hooks.append(hook)


def register_exception():
    """Called to on exceptions to log exception or send exception mail."""
    for h in exception_hooks:
        h()


def email_exceptions():
    if config.bugfixer:
        web.emailerrors(config.bugfixer, lambda: None)()


add_exception_hook(email_exceptions)
