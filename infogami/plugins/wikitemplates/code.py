"""
wikitemplates: allow keeping templates in wiki
"""

import web
import datetime
import os

import infogami
from infogami.utils import delegate, macro
from infogami.utils.context import context
from infogami.utils.view import render, set_error
from infogami.utils.storage import storage
from infogami import config
from infogami.core.db import ValidationException
from infogami import core
from infogami import tdb
import db, forms

cache = web.storage()

RE_MACRO = web.re_compile(r'macros/([^/]*)$')

class hooks(tdb.hook):
    def on_new_version(self, page):
        if page.type.name == 'type/template':
            site = page.parent
            _load_template(site, page)
            
        elif page.type.name == 'type/macro':
            _load_macro(page)
        elif page.type.name == 'type/delete':
            # if the type of previous version is template, then unload template
            # if the type of previous version is macro, then unregister macro
            pass

    def before_new_version(self, page):
        if page.type.name == 'type/template':
            _compile_template(page.name, page.body)
        elif page.type.name == 'type/template':
            _compile_template(page.name, page.macro)
                    
def _load_macro(page):
    match = RE_MACRO.match(page.name)
    if match:
        name = match.group(1)
        t = _compile_template(page.name, page.macro)
        t.__doc__ = page.description
        macro.register_macro(name, t)
        
def _load_macros():
    import db
    #@@ TODO: global macros must be available for every site
    web.load()
    context.load()
    for site in db.get_all_sites():
        macros = db.get_all_macros(site)
        context.site = site
        for m in macros:
            _load_macro(m)
try:
    #@@ this should be done lazily
    _load_macros()
except:
    # this fails when doing install. Temporary fix.
    pass
    
def random_string(size=20):
    import string
    import random

    # pick random letters 
    return "".join(random.sample(string.letters, size))

def _compile_template(name, text):
    try:
        return web.template.Template(text, filter=web.websafe, filename=name)
    except web.template.ParseError:
        print >> web.debug, 'Template parsing failed for ', name
        import traceback
        traceback.print_exc()
        raise ValidationException("Template parsing failed: " + str(e))
    
def _load_template(site, page):
    """load template from a wiki page."""
    if site.id not in cache:
        cache[site.id] = web.storage()
    cache[site.id][page.name] = _compile_template(page.name, page.body)

def load_templates(site):
    """Load all templates from a site.
    """
    pages = db.get_all_templates(site)    
    for p in pages:
        _load_template(site, p)

def get_templates(site):
    if site.id not in cache:
        cache[site.id] = web.storage()
        load_templates(site)
    return cache[site.id]

def get_site():
    from infogami.core import db
    return db.get_site(config.site)
    
def usermode(f):
    from infogami import tdb
    def g(*a, **kw):
        try:
            tdb.impl.hints.mode = 'user'
            return f(*a, **kw)
        finally:
            tdb.impl.hints.mode = 'system'
    
    g.__name__ = f.__name__
    return g

@usermode
def saferender(templates, *a, **kw):
    """Renders using the first successful template from the list of templates."""
    for t in templates:
        if t is None:
            continue
        try:
            result = t(*a, **kw)
            content_type = getattr(result, 'ContentType', 'text/html; charset=utf-8').strip()
            web.header('Content-Type', content_type, unique=True)
            return result
        except Exception, e:
            print >> web.debug, str(e)
            import traceback
            traceback.print_exc()
            set_error(str(t.filename) + ': error in processing template: ' + e.__class__.__name__ + ': ' + str(e) + ' (falling back to default template)')
     
    return "Unable to render this page."            
    
def get_user_template(path):
    from infogami.core import db
    if context.user is None:
        return None
    else:
        preferences = db.get_user_preferences(context.user)
        root = getattr(preferences, 'wikitemplates.template_root', None)
        if root is None or root.strip() == "":
            return None
        path = "%s/%s" % (root, path)
        return get_templates(get_site()).get(path, None)
    
def get_wiki_template(path):
    return get_templates(get_site()).get(path, None)
    
def pagetemplate(name, default_template):
    def render(page, *a, **kw):
        if context.rescue_mode:
            return default_template(page, *a, **kw)
        else:
            path = "%s/%s.tmpl" % (page.type.name, name)
            templates = [get_user_template(path), get_wiki_template(path), default_template]
            return saferender(templates, page, *a, **kw)
    return render
    
def sitetemplate(name, default_template):
    def render(*a, **kw):
        if context.rescue_mode:
            return default_template(*a, **kw)
        else:
            path = 'templates/%s.tmpl' % (name)
            templates = [get_user_template(path), get_wiki_template(path), default_template]
            return saferender(templates, *a, **kw)
    return render
        
class template_preferences:
    def GET(self, site):
        prefs = core.db.get_user_preferences(context.user)
        path = prefs.get('wikitemplates.template_root', "")
        f = forms.template_preferences()
        f.fill(dict(path=path))
        return render.wikitemplates.template_preferences(f)
        
    def POST(self, site):
        i = web.input()
        prefs = core.db.get_user_preferences(context.user)
        prefs['wikitemplates.template_root'] = i.path
        prefs.save()
        
core.code.register_preferences("template_preferences", template_preferences())

wikitemplates = storage.wikitemplates

def register_wiki_template(name, filepath, wikipath):
    """Registers a wiki template. 
    All registered templates are moved to wiki on `movetemplates` action.
    """
    wikitemplates[wikipath] = ((name, filepath, wikipath))

@infogami.install_hook
@infogami.action
def movetypes():
    delegate.fakeload()
    from infogami.core import db
    
    site = context.site
    tstring = db.get_type(site, 'type/string')
    ttext = db.get_type(site, 'type/text')

    db._create_type(site, 'type/template', [
        dict(name='title', type=tstring), 
        dict(name='body', type=ttext)])

    db._create_type(site, 'type/template', [
        dict(name='description', type=tstring), 
        dict(name='macro', type=ttext)])
    
@infogami.install_hook
@infogami.action
def movetemplates():
    """Move templates to wiki."""
    delegate.fakeload()
    load_templates(context.site)
    for name, filepath, wikipath in wikitemplates.values():
        print "*** %s\t%s -> %s" % (name, filepath, wikipath)
        _move_template(context.site, name, filepath, wikipath)

def _move_template(site, title, path, dbpath):
    from infogami.core import db
    root = os.path.dirname(infogami.__file__)
    body = open(root + "/" + path).read()
    d = web.storage(title=title, body=body)
    type = db.get_type(site, "type/template")
    db.new_version(site, dbpath, type, d).save()

render.core.site = sitetemplate('site', render.core.site)
render.core.history = sitetemplate("history", render.core.history)
render.core.login = sitetemplate("login", render.core.login)
render.core.register = sitetemplate("register", render.core.register)
render.core.diff = sitetemplate("diff", render.core.diff)
render.core.preferences = sitetemplate("preferences", render.core.preferences)
render.core.sitepreferences = sitetemplate("sitepreferences", render.core.sitepreferences)
render.core.default_view = sitetemplate("default_view", render.core.default_view)
render.core.default_edit = sitetemplate("default_edit", render.core.default_edit)
render.core.default_repr = sitetemplate("default_repr", render.core.default_repr)
render.core.default_ref = sitetemplate("default_ref", render.core.default_ref)

render.core.view = pagetemplate("view", render.core.default_view)
render.core.edit = pagetemplate("edit", render.core.default_edit)
render.core.repr = pagetemplate("repr", render.core.default_repr)
render.core.ref = pagetemplate("ref", render.core.default_ref)

render.core.notfound = sitetemplate("notfound", render.core.notfound)
render.core.deleted = sitetemplate("deleted", render.core.deleted)
    
# register site and page templates
register_wiki_template("Site Template", "core/templates/site.html", "templates/site.tmpl")
register_wiki_template("History Template", "core/templates/history.html", "templates/history.tmpl")
register_wiki_template("Login Template", "core/templates/login.html", "templates/login.tmpl")
register_wiki_template("Register Template", "core/templates/register.html", "templates/register.tmpl")
register_wiki_template("Diff Template", "core/templates/diff.html", "templates/diff.tmpl")
register_wiki_template("Preferences Template", "core/templates/preferences.html", "templates/preferences.tmpl")
register_wiki_template("Site Preferences Template", "core/templates/sitepreferences.html", "templates/sitepreferences.tmpl")
register_wiki_template("Default View Template", "core/templates/default_view.html", "templates/default_view.tmpl")
register_wiki_template("Default Edit Template", "core/templates/default_edit.html", "templates/default_edit.tmpl")
register_wiki_template("notfound", "core/templates/notfound.html", "templates/notfound.tmpl")
register_wiki_template("deleted", "core/templates/deleted.html", "templates/deleted.tmpl")

register_wiki_template("Page View Template", "core/templates/view.html", "type/page/view.tmpl")
register_wiki_template("Page Edit Template", "core/templates/edit.html", "type/page/edit.tmpl")

# register template templates
register_wiki_template("Template View Template",        
                       "plugins/wikitemplates/templates/view.html", 
                       "type/template/view.tmpl")    

register_wiki_template("Template Edit Template", 
                       "plugins/wikitemplates/templates/edit.html", 
                       "type/template/edit.tmpl")    

"""
register_wiki_template("Type View Template", 
                       "plugins/wikitemplates/templates/schema_view.html", 
                       "type/type/view.tmpl")

register_wiki_template("Type Edit Template", 
                       "plugins/wikitemplates/templates/schema_edit.html", 
                       "type/type/edit.tmpl")
"""