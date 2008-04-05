"""
Template Management.

In Infogami, templates are provided by multiple plugins. This module takes 
templates from each module and makes them available under single namespace.

There could also be multiple sources of templates. For example, from plugins 
and from the wiki. The `Render` class takes care of providing the correct 
template from multiple template sources and error handling.
"""
import web
import os

import storage

class DiskTemplateSource(web.storage):
    """Template source of templates on disk.
    Supports loading of templates from a search path instead of single dir.
    """
    def load_templates(self, path):
        def get_template(render, name):
            tokens = name.split(os.path.sep)
            for t in tokens:
                render = getattr(render, t)
            render.filepath = '%s/%s.html' % (path, name)
            return render
            
        render = web.template.render(path)
        # assuming all templates have .html extension
        names = [web.rstrips(p, '.html') for p in find(path) if p.endswith('.html')]
        for name in names:
            t = get_template(render, name)
            if t:
                self[name] = t
                
    def __repr__(self):
        return "<DiskTemplateSource at %d>" % id(self)
            
def find(path):
    """Find all files in the file hierarchy rooted at path.
        >> find('..../web')
        ['db.py', 'http.py', 'wsgiserver/__init__.py', ....]
    """
    for dirname, dirs, files in os.walk(path):
        dirname = web.lstrips(dirname, path)
        dirname = web.lstrips(dirname, '/')
        for f in files:
            yield os.path.join(dirname, f)

#@@ Find a better name
class Render(storage.DictPile):
    add_source = storage.DictPile.add_dict        
        
    def __getitem__(self, key):
        # take templates from all sources
        templates = [s[key] for s in self.dicts[::-1] if key in s]
        if templates:
            return lambda *a, **kw: saferender(templates, *a, **kw)
        else:
            raise KeyError, key
            
    def __getattr__(self, key):
        if key.startswith('__'):
            raise AttributeError, key
    
        try:
            return self[key]
        except KeyError:
            raise AttributeError, key

def usermode(f):
    """Returns a function that calls f after switching to user mode of tdb.
    In user mode, saving of things will be disabled to protect user written 
    templates from modifying things.
    """
    def g(*a, **kw):
        try:
            web.ctx.tdb_mode = 'user'
            return f(*a, **kw)
        finally:
            web.ctx.tdb_mode = 'system'

    g.__name__ = f.__name__
    return g

@usermode
def saferender(templates, *a, **kw):
    """Renders using the first successful template from the list of templates."""
    for t in templates:
        try:
            result = t(*a, **kw)
            content_type = getattr(result, 'ContentType', 'text/html; charset=utf-8').strip()
            web.header('Content-Type', content_type, unique=True)
            return result
        except Exception, e:
            # help to debug template errors.
            # when called with safe=false, the debug error is displayed.
            i = web.input(_method='GET', safe="true")
            if i.safe.lower() == "false":
                raise
            
            import traceback
            traceback.print_exc()
            from view import set_error
            set_error(str(t.filename) + ': error in processing template: ' + e.__class__.__name__ + ': ' + str(e) + ' (falling back to default template)')

    return web.template.Stowage(_str="Unable to render this page.", title='Error')

def typetemplate(name):
    """explain later"""
    def template(page, *a, **kw):
        default_template = getattr(render, 'default_' + name)
        key = page.type.key[1:] + '/' + name
        t = getattr(render, web.utf8(key), default_template)
        return t(page, *a, **kw)
    return template
    
def load_templates(plugin_root):
    """Adds $plugin_root/templates to template search path"""
    path = os.path.join(plugin_root, 'templates')
    if os.path.exists(path):
        disktemplates.load_templates(path)

disktemplates = DiskTemplateSource()
render = Render()
render.add_source(disktemplates)

# setup type templates
render.view = typetemplate('view')
render.edit = typetemplate('edit')
render.repr = typetemplate('repr')
render.input = typetemplate('input')
render.xdiff = typetemplate('diff')
