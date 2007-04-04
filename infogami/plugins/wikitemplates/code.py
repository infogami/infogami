"""
wikitemplates: allow keeping templates in wiki
"""

import web
import datetime
import os

import infogami
from infogami.utils import delegate
from infogami.utils.view import render, set_error
from infogami import config
from infogami.core.db import ValidationException
from infogami import tdb
import db

cache = web.storage()

# validation will be disabled while executing movetemplates action
validation_enabled = True

class hooks(tdb.hook):
    def on_new_version(self, page):
        if page.type.name == 'template':
            site_id = page.parent_id
            _load_template(site_id, page)

    def before_new_version(self, page):
        if page.type.name == 'template':
            site_id = page.parent_id
            path = page.name
            
            # ensure that templates are loaded
            get_templates(site_id)

            if path.endswith('page/view.tmpl') or path.endswith('page/edit.tmpl'):
                _validate_pagetemplate(page.body)
            elif path.endswith('/site.tmpl'):
                _validate_sitetemplate(page.body)

def _validate_pagetemplate(data):
    return
    """
    try:
        t = web.template.Template(data, filter=web.websafe)
        if validation_enabled:
            title = 'asdfmnb'
            body = 'qwertzxc'
            page = dummypage(title, body)
            result = str(t(page))
            if body not in result:
                raise ValidationException("Invalid template")
    except Exception, e: 
        raise ValidationException("Template parsing failed: " + str(e))
    """
    
def _validate_sitetemplate(data):
    return
    """
    try:
        t = web.template.Template(data, filter=web.websafe)
        if validation_enabled:
            title = 'asdfmnb'
            body = 'qwertzxc'
            page = web.template.Stowage(title=title, _str=body)
            result = str(t(page, None))
            if title not in result or body not in result:
                raise ValidationException("Invalid template")
    except Exception, e: 
        raise ValidationException("Template parsing failed: " + str(e))
    """
    
def dummypage(title, body):
    data = web.storage(title=title, body=body, template="page")
    page = web.storage(data=data, created=datetime.datetime.utcnow())
    return page

def _load_template(site_id, page):
    """load template from a wiki page."""
    try:
        t = web.template.Template(page.body, filter=web.websafe)
    except web.template.ParseError:
        print >> web.debug, 'load template', page.path, 'failed'
        pass
    else:
        if site_id not in cache:
            cache[site_id] = web.storage()
        cache[site_id][page.name] = t

def load_templates(site_id):
    """Load all templates from a site.
    """
    pages = db.get_all_templates(site_id)
    
    for p in pages:
        _load_template(site_id, p)

def get_templates(site_id):
    if site_id not in cache:
        cache[site_id] = web.storage()
        load_templates(site_id)
    return cache[site_id]

def get_site_id():
    from infogami.core import db
    return db.get_site(config.site).id

def saferender(template, default_template, *a, **kw):
    if template is None:
        return default_template(*a, **kw)
    else:
        try:
            web.header('Content-Type', 'text/html; charset=utf-8', unique=True)
            return template(*a, **kw)
        except Exception, e:
            set_error(str(e))
            return default_template(*a, **kw)

def pagetemplate(name, default_template):
    def render(page, *a, **kw):
        path = "templates/%s/%s.tmpl" % (page.type.name, name)
        t = get_templates(get_site_id()).get(path, None)
        return saferender(t, default_template, page, *a, **kw)
    return render

def sitetemplate(default_template):
    def render(*a, **kw):
        path = 'templates/site.tmpl'
        t = get_templates(get_site_id()).get(path, None)
        return saferender(t, default_template, *a, **kw)
    return render
        
render.core.view = pagetemplate("view", render.core.view)
render.core.edit = pagetemplate("edit", render.core.edit)
render.core.site = sitetemplate(render.core.site)

wikitemplates = []
def register_wiki_template(name, filepath, wikipath):
    """Registers a wiki template. 
    All registered templates are moved to wiki on `movetemplates` action.
    """
    wikitemplates.append((name, filepath, wikipath))

def _move_template(title, path, dbpath):
    from infogami.core import db
    root = os.path.dirname(infogami.__file__)
    body = open(root + "/" + path).read()
    d = web.storage(title=title, body=body)
    type = db.get_type("template", create=True)
    db.new_version(get_site_id(), dbpath, type.id, d).save()


@infogami.install_hook
@infogami.action
def movetemplates():
    """Move templates to wiki."""
    global validation_enabled

    web.load()
    web.ctx.ip = ""

    validation_enabled = False

    load_templates(get_site_id())
    for name, filepath, wikipath in wikitemplates:
        print "*** %s\t%s -> %s" % (name, filepath, wikipath)
        _move_template(name, filepath, wikipath)

# register site and page templates
register_wiki_template("Site Template", "core/templates/site.html", "templates/site.tmpl") 
register_wiki_template("Page View Template", "core/templates/view.html", "templates/page/view.tmpl")
register_wiki_template("Page Edit Template", "core/templates/edit.html", "templates/page/edit.tmpl")

# register template templates
register_wiki_template("Template View Template",        
                       "plugins/wikitemplates/templates/view.html", 
                       "templates/template/view.tmpl")    

register_wiki_template("Template Edit Template", 
                       "plugins/wikitemplates/templates/edit.html", 
                       "templates/template/edit.tmpl")    

