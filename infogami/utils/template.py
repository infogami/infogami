"""
Template Management.

In Infogami, templates are provided by multiple plugins. This module takes
templates from each module and makes them available under single namespace.

There could also be multiple sources of templates. For example, from plugins
and from the wiki. The `Render` class takes care of providing the correct
template from multiple template sources and error handling.
"""
import os
import time
import traceback

import web

from infogami.utils import storage

# There are some backward-incompatible changes in web.py 0.34 which makes Infogami fail.
assert web.__version__ != "0.34",  "Please pip install --upgrade web.py"
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
    def __init__(self, func, name=None, **kw):
        self.func = func
        self.name = name
        self.__dict__.update(kw)

    def __repr__(self):
        return "<LazyTemplate: %s>" % repr(self.name)

class DiskTemplateSource(web.storage):
    """Template source of templates on disk.
    Supports loading of templates from a search path instead of single dir.
    """
    def load_templates(self, path, lazy=False):
        # assuming all templates have .html extension
        names = [web.rstrips(p, '.html') for p in find(path) if p.endswith('.html')]
        for name in names:
            filepath = path + '/' + name + '.html'
            if lazy:
                def load(render=render, name=name, filepath=filepath):
                    self[name] = self.get_template(filepath)
                    return self[name]
                self[name] = LazyTemplate(load, name=name, filepath=filepath)
            else:
                self[name] = self.get_template(filepath)

    def get_template(self, filepath):
        mtime = time.time()
        t = web.template.frender(filepath)
        t.mtime = mtime
        t.filepath = filepath
        return t

    def is_template_modified(self, t):
        return os.path.exists(t.filepath) and os.stat(t.filepath).st_mtime > t.mtime

    def __getitem__(self, name):
        t = dict.__getitem__(self, name)
        if isinstance(t, LazyTemplate):
            t = t.func()
        elif web.config.debug is True and self.is_template_modified(t):
            t = self.get_template(t.filepath)
            self[name] = t

        return t

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
            raise KeyError(key)

    def __getattr__(self, key):
        if key.startswith('__'):
            raise AttributeError(key)

        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

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
        except Exception as e:
            # help to debug template errors.
            # when called with debug=true, the debug error is displayed.
            i = web.input(_method='GET', debug="false")
            if i.debug.lower() == "true":
                raise

            from . import delegate, view  # avoids circular imports
            delegate.register_exception()
            traceback.print_exc()
            message = str(t.filename) + ': error in processing template: ' + e.__class__.__name__ + ': ' + str(e) + ' (falling back to default template)'
            view.add_flash_message('error', message)

    return Stowage(_str="Unable to render this page.", title='Error')

def typetemplate(name):
    """explain later"""
    def template(page, *a, **kw):
        default_template = getattr(render, 'default_' + name, None)
        key = page.type.key[1:] + '/' + name
        t = getattr(render, web.safestr(key), default_template)
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

def render_template(name, *a, **kw):
    return get_template(name)(*a, **kw)

def get_template(name):
    # strip extension
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return render.get(name)
