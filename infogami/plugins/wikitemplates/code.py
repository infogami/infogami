"""
wikitemplates: allow keeping templates and macros in wiki
"""
from __future__ import print_function

import os
try:
    from collections.abc import Mapping
except ImportError:
    from collections import Mapping

import web

import infogami
from infogami import config
from infogami.core.db import ValidationException
from infogami.infobase import client
from infogami.plugins.wikitemplates import db, forms
from infogami.utils import delegate, macro, template, storage
from infogami.utils.context import context
from infogami.utils.template import render
from infogami.utils.view import require_login

LazyTemplate = template.LazyTemplate

class WikiSource(Mapping):
    """Template source for templates in the wiki"""
    def __init__(self, templates):
        self.templates = templates

    def getroot(self):
        return config.get("default_template_root", "/")

    def __getitem__(self, key):
        key = self.process_key(key)
        root = self.getroot()
        if root is None or context.get('rescue_mode'):
            raise KeyError(key)

        root = web.rstrips(root or "", "/")
        value = self.templates[root + key]
        if isinstance(value, LazyTemplate):
            value = value.func()

        return value

    # TODO: Should __iter__() and keys() return the same keys??
    def __iter__(self):
        return self.templates.__iter__()

    def __len__(self):
        return len(self.templates)

    def keys(self):
        return [self.unprocess_key(k) for k in self.templates.keys()]

    def process_key(self, key):
        return '/templates/%s.tmpl' % key

    def unprocess_key(self, key):
        key = web.lstrips(key, '/templates/')
        key = web.rstrips(key, '.tmpl')
        return key

class MacroSource(WikiSource):
    def process_key(self, key):
        # macro foo is available at path macros/foo
        return '/macros/' + key

    def unprocess_key(self, key):
        return web.lstrips(key, '/macros/')

def get_user_preferences():
    #@ quick hack to avoid querying for user_preferences again and again
    if 'user_preferences' not in web.ctx:
        web.ctx.user_preferences = context.get('user') and web.ctx.site.get(context.user.key + "/preferences")
    return web.ctx.user_preferences

def get_user_root():
    i = web.input(_method='GET')
    if 'template_root' in i:
        return i.template_root.strip()
    preferences = get_user_preferences()
    return preferences and preferences.get("template_root", None)

class UserSource(WikiSource):
    """Template source for user templates."""
    def getroot(self):
        return get_user_root()

class UserMacroSource(MacroSource):
    """Template source for user macros."""
    def getroot(self):
        return get_user_root()

wikitemplates = storage.SiteLocalDict()
template.render.add_source(WikiSource(wikitemplates))
template.render.add_source(UserSource(wikitemplates))

wikimacros = storage.SiteLocalDict()
macro.macrostore.add_dict(MacroSource(wikimacros))
macro.macrostore.add_dict(UserMacroSource(wikimacros))

class hooks(client.hook):
    def on_new_version(self, page):
        """Updates the template/macro cache, when a new version is saved or deleted."""
        if page.type.key == '/type/template':
            _load_template(page)
        elif page.type.key == '/type/macro':
            _load_macro(page)
        elif page.type.key == '/type/delete':
            if page.name in wikitemplates:
                del wikitemplates[page.key]
            if page.name in wikimacros:
                del wikimacros[page.key]

    def before_new_version(self, page):
        """Validates template/macro, before it is saved, by compiling it."""
        if page.type.key == '/type/template':
            _compile_template(page.key, page.body)
        elif page.type.key == '/type/macro':
            _compile_template(page.key, page.macro)


def _stringify(value):
    if isinstance(value, dict):
        return value['value']
    else:
        return value

def _compile_template(name, text):
    text = web.safestr(_stringify(text))

    try:
        return web.template.Template(text, filter=web.websafe, filename=name)
    except (web.template.ParseError, SyntaxError) as e:
        print('Template parsing failed for ', name, file=web.debug)
        import traceback
        traceback.print_exc()
        raise ValidationException("Template parsing failed: " + str(e))

def _load_template(page, lazy=False):
    """load template from a wiki page."""
    if lazy:
        page = web.storage(key=page.key, body=web.safestr(_stringify(page.body)))
        wikitemplates[page.key] = LazyTemplate(lambda: _load_template(page))
    else:
        wikitemplates[page.key] = _compile_template(page.key, page.body)

def _load_macro(page, lazy=False):
    if lazy:
        page = web.storage(key=page.key, macro=web.safestr(_stringify(page.macro)), description=page.description or "")
        wikimacros[page.key] = LazyTemplate(lambda: _load_macro(page))
    else:
        t = _compile_template(page.key, page.macro)
        t.__doc__ = page.description or ''
        wikimacros[page.key] = t

def load_all():
    def load_macros(site):
        for m in db.get_all_macros(site):
            _load_macro(m, lazy=True)

    def load_templates(site):
        for t in db.get_all_templates(site):
            _load_template(t, lazy=True)

    for site in db.get_all_sites():
        context.site = site
        load_macros(site)
        load_templates(site)

def setup():
    delegate.fakeload()

    load_all()

    from infogami.utils import types
    types.register_type(r'/templates/.*\.tmpl$', '/type/template')
    types.register_type('^/type/[^/]*$', '/type/type')
    types.register_type('/macros/.*$', '/type/macro')

def reload():
    """Reload all templates and macros."""
    load_all()

@infogami.install_hook
@infogami.action
def movetemplates(prefix_pattern=None):
    """Move templates to wiki."""
    def get_title(name):
        if name.startswith('/type/'):
            type, name = name.rsplit('/', 1)
            title = '%s template for %s' % (name, type)
        else:
            title = '%s template' % (name)
        return title

    templates = []

    for name, t in template.disktemplates.items():
        if isinstance(t, LazyTemplate):
            try:
                t.func()
            except:
                print('unable to load template', t.name, file=web.debug)
                raise

    for name, t in template.disktemplates.items():
        prefix = '/templates/'
        wikipath = _wikiname(name, prefix, '.tmpl')
        if prefix_pattern is None or wikipath.startswith(prefix_pattern):
            title = get_title(name)
            body = open(t.filepath).read()
            d = web.storage(create='unless_exists', key=wikipath, type={"key": '/type/template'}, title=title, body=dict(connect='update', value=body))
            templates.append(d)

    delegate.admin_login()
    result = web.ctx.site.write(templates)
    for p in result.created:
        print("created", p)
    for p in result.updated:
        print("updated", p)

@infogami.install_hook
@infogami.action
def movemacros():
    """Move macros to wiki."""
    macros = []

    for name, t in macro.diskmacros.items():
        if isinstance(t, LazyTemplate):
            t.func()

    for name, m in macro.diskmacros.items():
        key = _wikiname(name, '/macros/', '')
        body = open(m.filepath).read()
        d = web.storage(create='unless_exists', key=key, type={'key': '/type/macro'}, description='', macro=body)
        macros.append(d)
    delegate.admin_login()
    result = web.ctx.site.write(macros)
    for p in result.created:
        print("created", p)
    for p in result.updated:
        print("updated", p)

def _wikiname(name, prefix, suffix):
    base, extn = os.path.splitext(name)
    return prefix + base + suffix

def _new_version(name, typename, d):
    from infogami.core import db
    type = db.get_type(context.site, typename)
    db.new_version(context.site, name, type, d).save()

class template_preferences(delegate.page):
    """Preferences to choose template root."""
    path = "/account/preferences/template_preferences"
    title = "Change Template Root"

    @require_login
    def GET(self):
        prefs = web.ctx.site.get(context.user.key + "/preferences")
        path = (prefs and prefs.get('template_root')) or "/"
        f = forms.template_preferences()
        f.fill(dict(path=path))
        return render.template_preferences(f)

    @require_login
    def POST(self):
        i = web.input()
        q = {
            "create": "unless_exists",
            "type": "/type/object",
            "key": context.user.key + "/preferences",
            "template_root": {
                "connect": "update",
                "value": i.path
            }
        }
        web.ctx.site.write(q)
        raise web.seeother('/account/preferences')

def monkey_patch_debugerror():
    """Monkey patch web.debug error to display template code."""
    def xopen(filename):
        if filename.endswith('.tmpl') or filename.startswith('/macros/'):
            page = web.ctx.site.get(filename)
            if page is None:
                raise IOError("not found: " + filename)
            from six import StringIO
            return StringIO(page.body + "\n" * 100)
        else:
            return open(filename)

    web.debugerror.func_globals['open'] = xopen

from infogami.core.code import register_preferences
register_preferences(template_preferences)

# load templates and macros from all sites.
setup()

monkey_patch_debugerror()
