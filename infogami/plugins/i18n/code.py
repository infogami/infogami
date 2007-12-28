"""
i18n: allow keeping i18n strings in wiki
"""

import web

import infogami
from infogami import config, tdb
from infogami.utils import delegate, i18n
from infogami.utils.context import context
from infogami.utils.view import public

import db

re_i18n = web.re_compile(r'^i18n/strings\.([^/]*)$')

class hook(tdb.hook):
    def on_new_version(self, page):
        """Update i18n strings when a i18n wiki page is changed."""
        if page.type.name == 'type/i18n':
            path = page.name
            result = re_i18n.match(path)
            if result:
                lang = result.group(1)
                i18n.strings._set_strings(lang, page.d)

def load_strings(site):
    """Load strings from wiki."""
    pages = db.get_all_strings(site)
    for page in pages:
        result = re_i18n.match(page.name)
        if result:
            lang = result.group(1)
            i18n.strings._set_strings(lang, page.d)
            
def setup():
    delegate.fakeload()    
    from infogami.utils import types
    types.register_type('i18n/strings.[^/]*', 'type/i18n')
    
    for site in db.get_all_sites():
        load_strings(site)
    
@infogami.install_hook
def createtype():
    from infogami.core import db
    db.new_type(context.site, 'type/i18n', [])
    
@infogami.install_hook
@infogami.action
def movestrings():
    """Moves i18n strings to wiki."""
    from infogami.core import db
    type = db.get_type(context.site, 'type/i18n')
    
    for lang, d in i18n.strings._data.iteritems():
        wikipath = "i18n/strings." + lang
        db.new_version(context.site, wikipath, type, d).save()

setup()