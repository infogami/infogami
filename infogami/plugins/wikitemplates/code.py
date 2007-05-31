"""
wikitemplates: allow keeping templates in wiki
"""

import web
import datetime
import os

import infogami
from infogami.utils import delegate
from infogami.utils.context import context
from infogami.utils.view import render, set_error
from infogami.utils.storage import storage
from infogami import config
from infogami.core.db import ValidationException
from infogami import core
from infogami import tdb
import db, forms
import re

cache = web.storage()

# validation will be disabled while executing movetemplates action
validation_enabled = True

class hooks(tdb.hook):
    def on_new_version(self, page):
        if page.type.name == 'template':
            site = page.parent
            _load_template(site, page)

    def before_new_version(self, page):
        if page.type.name == 'template':
            site = page.parent
            path = page.name
            
            # ensure that templates are loaded
            get_templates(site)

            rx = re.compile('templates/([^/]+)/(?:view|edit).tmpl')
            match = rx.match(path)

            if match:
                typename = match.group(1)
                _validate_pagetemplate(site, typename, page.body)
            elif path == 'templates/site.tmpl':
                _validate_sitetemplate(page.body)

def random_string(size=20):
    import string
    import random

    # pick random letters 
    return "".join(random.sample(string.letters, size))

def _validate_pagetemplate(site, typename, data):
    from infogami.core import db

    type = db.get_type(typename, create=False)

    if type is None:
        raise ValidationException, "Unknown page type: %s.\nMake sure schema is defined for this pagetype." % typename
    
    schema = db.get_schema(site, type, default=False)
    schema.pop('*', None)

    magic = random_string()

    d = web.storage()
    for k in schema:
        if k.endswith('*'):
            d[k] = [k + magic]
        else:
            d[k] = k + magic

    v = tdb.Version(0, 0, 0, '', '', '', datetime.datetime.utcnow())
    p = tdb.Thing(0, 'dummy', site, type, d, v)

    try:
        t = web.template.Template(data, filter=web.websafe)
        if validation_enabled:
            result = str(t(p))
    except Exception, e: 
        import traceback
        traceback.print_exc()
        raise ValidationException("Template parsing failed: " + str(e))
    else:
        if validation_enabled:
            for k in schema:
                if (k + magic) not in result:
                    raise ValidationException("Invalid template: missing %s" % k)
    
def _validate_sitetemplate(data):
    try:
        t = web.template.Template(data, filter=web.websafe)
        if validation_enabled:
            title = random_string()
            body = random_string()
            page = web.template.Stowage(title=title, _str=body)
            result = str(t(page, None))
    except Exception, e: 
        raise ValidationException("Template parsing failed: " + str(e))
    else:
        if validation_enabled:
            if title not in result:
                raise ValidationException("Invalid template: missing page title")

            if body not in result:
                raise ValidationException("Invalid template: missing page")
    
def dummypage(title, body):
    data = web.storage(title=title, body=body, template="page")
    page = web.storage(data=data, created=datetime.datetime.utcnow())
    return page

def _load_template(site, page):
    """load template from a wiki page."""
    try:
        t = web.template.Template(page.body, filter=web.websafe)
    except web.template.ParseError:
        print >> web.debug, 'load template', page.name, 'failed'
        import traceback
        traceback.print_exc()
        pass
    else:
        if site.id not in cache:
            cache[site.id] = web.storage()
        cache[site.id][page.name] = t

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
            set_error('error in processing template: ' + e.__class__.__name__ + ': ' + str(e) + ' (falling back to default template)')
     
    
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
    path = "templates/" + path
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
            path = name + '.tmpl'
            templates = [get_user_template(path), get_wiki_template(path), default_template]
            return saferender(templates, *a, **kw)
    return render
        
render.core.view = pagetemplate("view", render.core.default_view)
render.core.edit = pagetemplate("edit", render.core.default_edit)

render.core.site = sitetemplate('site', render.core.site)
render.core.history = sitetemplate("history", render.core.history)
render.core.login = sitetemplate("login", render.core.login)
render.core.register = sitetemplate("register", render.core.register)
render.core.diff = sitetemplate("diff", render.core.diff)

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
    wikitemplates[name] = ((name, filepath, wikipath))

def _move_template(title, path, dbpath):
    from infogami.core import db
    root = os.path.dirname(infogami.__file__)
    body = open(root + "/" + path).read()
    d = web.storage(title=title, body=body)
    type = db.get_type("template", create=True)
    db.new_version(get_site(), dbpath, type, d).save()

@infogami.install_hook
@infogami.action
def movetemplates():
    """Move templates to wiki."""
    global validation_enabled

    web.load()
    web.ctx.ip = ""

    validation_enabled = False

    load_templates(get_site())
    for name, filepath, wikipath in wikitemplates.values():
        print "*** %s\t%s -> %s" % (name, filepath, wikipath)
        _move_template(name, filepath, wikipath)

def _move_schema(name, data):
    from infogami.core import db
    path = 'templates/%s/schema' % name
    type = db.get_type("schema", create=True)
    db.new_version(get_site(), path, type, data).save()

@infogami.install_hook
def moveschemas():
    _move_schema('schema', web.storage({'*':'string'}))
    _move_schema('page', web.storage({'title':'string', 'body': 'string'}))
    _move_schema('template', web.storage({'title':'string', 'body': 'string'}))
    
# register site and page templates
register_wiki_template("Site Template", "core/templates/site.html", "templates/site.tmpl")
register_wiki_template("Page View Template", "core/templates/view.html", "templates/page/view.tmpl")
register_wiki_template("Page Edit Template", "core/templates/edit.html", "templates/page/edit.tmpl")
register_wiki_template("History Template", "core/templates/history.html", "templates/history.tmpl")
register_wiki_template("Login Template", "core/templates/login.html", "templates/login.tmpl")
register_wiki_template("Register Template", "core/templates/register.html", "templates/register.tmpl")
register_wiki_template("Diff Template", "core/templates/diff.html", "templates/diff.tmpl")

# register template templates
register_wiki_template("Template View Template",        
                       "plugins/wikitemplates/templates/view.html", 
                       "templates/template/view.tmpl")    

register_wiki_template("Template Edit Template", 
                       "plugins/wikitemplates/templates/edit.html", 
                       "templates/template/edit.tmpl")    

register_wiki_template("Schema View Template", 
                       "plugins/wikitemplates/templates/schema_view.html", 
                       "templates/schema/view.tmpl")

register_wiki_template("Schema Edit Template", 
                       "plugins/wikitemplates/templates/schema_edit.html", 
                       "templates/schema/edit.tmpl")
