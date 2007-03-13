"""
wikitemplates: allow keeping templates in wiki
"""

import web
import datetime

from infogami.utils import delegate
from infogami.utils.view import render, set_error
from infogami import config
from infogami.core.db import ValidationException

import db

cache = web.storage()

class hooks:
    __metaclass__ = delegate.hook
    def on_new_version(site, path, data):
        if data.template == 'template':
            _load_template(site, web.storage(path=path, data=data))

    def before_new_version(site, path, data):
        # ensure that templates are loaded
        get_templates(site)

        if data.template == 'template':
            if path.endswith('/view.tmpl') or path.endswith('/edit.tmpl'):
                _validate_pagetemplate(data.body)
            elif path.endswith('/site.tmpl'):
                _validate_sitetemplate(data.body)

def _validate_pagetemplate(data):
    try:
        t = web.template.Template(data, filter=web.websafe)

        title = 'asdfmnb'
        body = 'qwertzxc'
        page = dummypage(title, body)
        result = str(t(page))
        if body not in result:
            raise ValidationException("Invalid template")
    except Exception, e: 
        raise ValidationException("Template parsing failed: " + str(e))

def _validate_sitetemplate(data):
    try:
        t = web.template.Template(data, filter=web.websafe)

        title = 'asdfmnb'
        body = 'qwertzxc'
        page = web.template.Stowage(title=title, _str=body)
        result = str(t(page, None))
        if title not in result or body not in result:
            raise ValidationException("Invalid template")
    except Exception, e: 
        raise ValidationException("Template parsing failed: " + str(e))

def dummypage(title, body):
    data = web.storage(title=title, body=body, template="page")
    page = web.storage(data=data, created=datetime.datetime.utcnow())
    return page

def _load_template(site, page):
    """load template from a wiki page."""
    try:
        t = web.template.Template(page.data.body, filter=web.websafe)
    except web.template.ParseError:
        print >> web.debug, 'load template', page.url, 'failed'
        pass
    else:
        if site not in cache:
            cache[site] = web.storage()
        cache[site][page.path] = t

def load_templates(site):
    """Load all templates from a site.
    """
    pages = db.get_all_templates(site)
    
    for p in pages:
        _load_template(site, p)

def get_templates(site):
    if site not in cache:
        cache[site] = web.storage()
        load_templates(site)
    return cache[site]

def saferender(template, default_template, *a, **kw):
    if template is None:
        return default_template(*a, **kw)
    else:
        try:
            web.header('Content-type', 'text/html')
            return template(*a, **kw)
        except Exception, e:
            set_error(str(e))
            return default_template(*a, **kw)

def pagetemplate(name, default_template):
    def render(page, *a, **kw):
        path = "templates/%s/%s.tmpl" % (page.data.template, name)
        t = get_templates(config.site).get(path, None)
        return saferender(t, default_template, page, *a, **kw)
    return render

def sitetemplate(default_template):
    def render(*a, **kw):
        path = 'templates/site.tmpl'
        t = get_templates(config.site).get(path, None)
        return saferender(t, default_template, *a, **kw)
    return render
        
render.core.view = pagetemplate("view", render.core.view)
render.core.edit = pagetemplate("edit", render.core.edit)
render.core.site = sitetemplate(render.core.site)

