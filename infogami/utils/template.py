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

web_render = web.template.render

class TemplateRender(web_render):
    def _lookup(self, name):
        path = os.path.join(self._loc, name)
        filepath = self._findfile(path)
        if filepath:
            return 'file', filepath
        elif os.path.isdir(path):
            return 'dir', path
        else:
            return 'none', None
            
    def __repr__(self):
        return "<TemplateRender: %s>" % repr(self._loc)

web.template.Render = web.template.render = TemplateRender

class LazyTemplate:
    def __init__(self, func):
        self.func = func
        
class DiskTemplateSource(web.storage):
    """Template source of templates on disk.
    Supports loading of templates from a search path instead of single dir.
    """
    def load_templates(self, path, lazy=False):
        def get_template(render, name):
            tokens = name.split(os.path.sep)
            render = getattr(render, name)
            render.filepath = '%s/%s.html' % (path, name)
            return render
            
        def set_template(render, name):
            self[name] = get_template(render, name)
            return self[name]
            
        render = web.template.render(path)
        # assuming all templates have .html extension
        names = [web.rstrips(p, '.html') for p in find(path) if p.endswith('.html')]
        for name in names:
            if lazy:
                self[name] = LazyTemplate(lambda render=render, name=name: set_template(render, name))
            else:
                self[name] = get_template(render, name)
            
    def __getitem__(self, name):
        value = dict.__getitem__(self, name)
        if isinstance(value, LazyTemplate):
            value = value.func()
            
        return value
           
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

class Stowage(web.storage):
    def __str__(self):
        return self._str

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
            # when called with debug=true, the debug error is displayed.
            i = web.input(_method='GET', debug="false")
            if i.debug.lower() == "true":
                raise
            
            import delegate
            delegate.register_exception()
            
            import traceback
            traceback.print_exc()
            
            import view            
            message = str(t.filename) + ': error in processing template: ' + e.__class__.__name__ + ': ' + str(e) + ' (falling back to default template)'
            view.add_flash_message('error', message)

    return Stowage(_str="Unable to render this page.", title='Error')

def typetemplate(name):
    """explain later"""
    def template(page, *a, **kw):
        default_template = getattr(render, 'default_' + name, None)
        key = page.type.key[1:] + '/' + name
        t = getattr(render, web.utf8(key), default_template)
        return t(page, *a, **kw)
    return template
    
def load_templates(plugin_root, lazy=True):
    """Adds $plugin_root/templates to template search path"""
    path = os.path.join(plugin_root, 'templates')
    if os.path.exists(path):
        disktemplates.load_templates(path, lazy=lazy)

disktemplates = DiskTemplateSource()
render = Render()
render.add_source(disktemplates)

# setup type templates
render.view = typetemplate('view')
render.edit = typetemplate('edit')
render.repr = typetemplate('repr')
render.input = typetemplate('input')
render.xdiff = typetemplate('diff')

