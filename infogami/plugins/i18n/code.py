"""
i18n: allow keeping i18n strings in wiki
"""

import web

import infogami
from infogami import config, tdb
from infogami.utils import delegate, i18n
from infogami.utils.context import context
from infogami.utils.view import public
from infogami.utils.template import render
import db

re_i18n = web.re_compile(r'^i18n(/.*)?/strings\.([^/]*)$')

class hook(tdb.hook):
    def on_new_version(self, page):
        """Update i18n strings when a i18n wiki page is changed."""
        if page.type.name == 'type/i18n':
            path = page.name
            result = re_i18n.match(path)
            if result:
                namespace, lang = result.groups()
                namespace = namespace and namespace[1:] or ''
                i18n.strings._set_strings(namespace, lang, page.d)

def load_strings(site):
    """Load strings from wiki."""
    pages = db.get_all_strings(site)
    for page in pages:
        result = re_i18n.match(page.name)
        if result:
            namespace, lang = result.groups()
            namespace = namespace and namespace[1:] or ''
            i18n.strings._set_strings(namespace, lang, page.d)

class i18n_page(delegate.page):
    path = '/i18n'
    def GET(self, site):
        from infogami.core import db
        from infogami import tdb 
        
        i = web.input(lang='en', ns='')
        
        if i.lang not in i18n.strings.get_languages():
            web.changequery(lang='en')
            raise StopIteration
            
        path = pathjoin('i18n', i.ns, 'strings.' + i.lang)
        try:
            page = db.get_version(site, path)
        except tdb.NotFound:
            page = None
        return render.i18n(i.ns, i.lang, page)
    
def setup():
    delegate.fakeload()    
    from infogami.utils import types
    types.register_type('i18n(/.*)?/strings.[^/]*', 'type/i18n')
    
    for site in db.get_all_sites():
        load_strings(site)
    
@infogami.install_hook
def createtype():
    from infogami.core import db
    db.new_type(context.site, 'type/i18n', [])
    
def pathjoin(*p):
    return "/".join([a for a in p if a])
    
@infogami.install_hook
@infogami.action
def movestrings():
    """Moves i18n strings to wiki."""
    from infogami.core import db
    type = db.get_type(context.site, 'type/i18n')
    
    for (namespace, lang), d in i18n.strings._data.iteritems():
        wikipath = pathjoin('i18n', namespace, 'strings.' + lang)
        db.new_version(context.site, wikipath, type, d).save()

setup()
