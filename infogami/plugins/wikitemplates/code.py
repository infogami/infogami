"""
wikitemplates: allow keeping templates in wiki
"""
from infogami.utils import delegate
from infogami.utils.view import render
from infogami.core import db
import web
from infogami import config

def wikitemplate(name, default_template):
    def render(page):
        path = "templates/%s/%s.tmpl" % (page.data.template, name)

        # shouldn't site be available somewhere without explicitly passing around?
        site = config.site 

        has_template = db.get_page_id(site, path)
        if has_template:
            #TODO: cache templates
            template_page = db.get_version(site, path)
            try:
                t = web.template.Template(template_page.data.body, filter=web.websafe)
                return t(page)
            except:
                return default_template(page)
        else:
            return default_template(page)
    return render
        
render.core.view = wikitemplate("view", render.core.view)
render.core.edit = wikitemplate("edit", render.core.edit)

