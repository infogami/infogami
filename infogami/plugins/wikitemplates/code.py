"""
wikitemplates: allow keeping templates in wiki
"""

import web

from infogami.utils import delegate
from infogami.utils.view import render
from infogami import config

import db

cache = web.storage()

r_template = web.re_compile(r'templates/.*\.tmpl')

class hooks:
    __metaclass__ = delegate.hook
    def on_new_version(site, path, data):
        if r_template.match(path):
            _load_template(site, web.storage(path=path, data=web.storage(body=data)))
            
def _load_template(site, page):
    """load template from a wiki page."""
    try:
        t = web.template.Template(page.data.body, filter=web.websafe)
    except web.template.ParseError:
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
        if r_template.match(p.path):
            _load_template(site, p)

def get_templates(site):
    if site not in cache:
        cache[site] = web.storage()
        load_templates(site)
    return cache[site]

def wikitemplate(name, default_template):
    def render(page):
        path = "templates/%s/%s.tmpl" % (page.data.template, name)

        # shouldn't site be available somewhere without explicitly passing around?
        site = config.site 
        t = get_templates(site).get(path, default_template)
        return t(page)
    return render

def sitetemplate(default_template):
    def render(*args):
        path = 'templates/site.tmpl'
        site = config.site 
        t = get_templates(site).get(path, default_template)
        return t(*args)
    return render
        
render.core.view = wikitemplate("view", render.core.view)
render.core.edit = wikitemplate("edit", render.core.edit)
render.core.site = sitetemplate(render.core.site)

