"""
wikitemplates: allow keeping templates and macros in wiki
"""

import web
import os
from UserDict import DictMixin

import infogami
from infogami import core, tdb
from infogami.core.db import ValidationException
from infogami.utils import delegate, macro, template, storage
from infogami.utils.context import context
from infogami.utils.template import render

import db

class WikiSource(DictMixin):
    """Template source for templates in the wiki"""
    def __init__(self, templates):
        self.templates = templates
        
    def getroot(self):
        return ""
        
    def __getitem__(self, key):
        key = self.process_key(key)
        root = self.getroot()
        if root is None:
            raise KeyError, key
        return self.templates[root+key]
        
    def keys(self):
        return [self.unprocess_key(k) for k in self.templates.keys()]
        
    def process_key(self, key):
        # There are two types of templates; regular templates and type templates.
        # regular template with name xxx will be available at templates/xxx.tmpl in the wiki.
        # type template with name type/xxx/yyy will be available at type/xxx/yyy.tmpl in the wiki.
        # So name of regular templates need to be prefixed with 'templates/' to get the wiki path.
        if not key.startswith('type/'):
            return 'templates/' + key + ".tmpl"
        else:
            return key + ".tmpl"
            
    def unprocess_key(self, key):
        key = web.lstrips(key, 'templates/')
        key = web.rstrips(key, '.tmpl')
        return key
    
class MacroSource(WikiSource):
    def process_key(self, key):
        # macro foo is availble at path macros/foo
        return 'macros/' + key
        
    def unprocess_key(self, key):
        return web.lstrips(key, 'macros/')
    
class UserSource(WikiSource):
    """Template source for user templates."""
    def getroot(self):
        from infogami.core import db
        if context.user:
            preferences = db.get_user_preferences(context.user)
            root = getattr(preferences, 'wikitemplates.template_root', None)
            if root is not None and root.strip() != "":
                return root
        return None

wikitemplates = storage.SiteLocalDict()
template.render.add_source(WikiSource(wikitemplates))
template.render.add_source(UserSource(wikitemplates))

wikimacros = storage.SiteLocalDict()
macro.macrostore.add_dict(MacroSource(wikimacros))

class hooks(tdb.hook):
    def on_new_version(self, page):
        """Updates the template/macro cache, when a new version is saved or deleted."""
        if page.type.name == 'type/template':
            _load_template(page)            
        elif page.type.name == 'type/macro':
            _load_macro(page)
        elif page.type.name == 'type/delete':
            if page.name in wikitemplates:
                del wikitemplates[page.name]
            if page.name in wikimacros:
                del wikimacros[page.name]
                
    def before_new_version(self, page):
        """Validates template/macro, before it is saved, by compiling it."""
        if page.type.name == 'type/template':
            _compile_template(page.name, page.body)
        elif page.type.name == 'type/macro':
            _compile_template(page.name, page.macro)

def _compile_template(name, text):
    try:
        return web.template.Template(text, filter=web.websafe, filename=name)
    except web.template.ParseError, e:
        print >> web.debug, 'Template parsing failed for ', name
        import traceback
        traceback.print_exc()
        raise ValidationException("Template parsing failed: " + str(e))

def _load_template(page):
    """load template from a wiki page."""
    wikitemplates[page.name] = _compile_template(page.name, page.body)
                    
def _load_macro(page):
    t = _compile_template(page.name, page.macro)
    t.__doc__ = page.d.get('description')
    wikimacros[page.name] = t
    
def setup():
    delegate.fakeload()
    def load_macros(site): 
        for m in db.get_all_macros(site):
            _load_macro(m)
    
    def load_templates(site):
        for t in db.get_all_templates(site):
            _load_template(t)
    
    for site in db.get_all_sites():
        context.site = site
        load_macros(site)
        load_templates(site)
    
@infogami.install_hook
def createtypes():
    """Create type/template and type/macro on install."""
    delegate.fakeload()
    from infogami.core import db
    
    site = context.site
    tstring = db.get_type(site, 'type/string')
    ttext = db.get_type(site, 'type/text')

    db._create_type(site, 'type/template', [
        dict(name='title', type=tstring), 
        dict(name='body', type=ttext)])

    db._create_type(site, 'type/macro', [
        dict(name='description', type=tstring), 
        dict(name='macro', type=ttext)])
    
@infogami.install_hook
@infogami.action
def movetemplates(prefix_pattern=None):
    """Move templates to wiki."""
    def get_title(name):
        if name.startswith('type/'):
            type, name = name.rsplit('/', 1)
            title = '%s template for %s' % (name, type)
        else:
            title = '%s template' % (name)
        return title

    delegate.fakeload()
    for name, t in template.disktemplates.items():
        if name.startswith('type'): 
            prefix = ''
        else: 
            prefix = 'templates/'
        wikipath = _wikiname(name, prefix, '.tmpl')
        if prefix_pattern is None or wikipath.startswith(prefix_pattern):
            title = get_title(name)
            body = open(t.filepath).read()
            d = web.storage(title=title, body=body)
            print 'movetemplates: %s -> %s' % (t.filename, wikipath)
            _new_version(wikipath, 'type/template', d)
        
@infogami.install_hook
@infogami.action
def movemacros():
    """Move macros to wiki."""
    delegate.fakeload()
    for name, m in macro.diskmacros.items():
        wikipath = _wikiname(name, 'macros/', '')
        body = open(m.filepath).read()
        d = web.storage(description='', macro=body)
        print 'movemacros: %s -> %s' % (m.filename, wikipath)
        _new_version(wikipath, 'type/macro', d)

def _wikiname(name, prefix, suffix):
    base, extn = os.path.splitext(name)
    return prefix + base + suffix
        
def _new_version(name, typename, d):
    from infogami.core import db
    type = db.get_type(context.site, typename)
    db.new_version(context.site, name, type, d).save()

class template_preferences:
    """Preferences to choose template root."""
    def GET(self, site):
        import forms
        prefs = core.db.get_user_preferences(context.user)
        path = prefs.get('wikitemplates.template_root', "")
        f = forms.template_preferences()
        f.fill(dict(path=path))
        return render.template_preferences(f)

    def POST(self, site):
        i = web.input()
        prefs = core.db.get_user_preferences(context.user)
        prefs['wikitemplates.template_root'] = i.path
        prefs.save()

from infogami.core.code import register_preferences
register_preferences("template_preferences", template_preferences())

# load templates and macros from all sites.
setup()