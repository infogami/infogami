"""
i18n: allow keeping i18n strings in wiki
"""

import web
from infogami.utils import delegate, i18n
from infogami.utils.view import public
from infogami.plugins.wikitemplates.code import register_wiki_template
from infogami import config
import infogami
import db
import os.path

re_i18n = web.re_compile(r'^i18n/strings\.(.*)$')

class hooks:
    __metaclass__ = delegate.hook
    def on_new_version(site, path, data):
        """Update i18n strings when a i18n wiki page is changed."""
        if data.template == 'i18n': 
            result = re_i18n.match(path)
            if result:
                lang = result.group(1)
                update_strings(lang, data)

def load_strings():
    """Load strings from wiki."""
    # This function is called from the first request that uses i18n
    pages = db.get_all_strings(config.site)
    for page in pages:
        result = re_i18n.match(page.path)
        if result:
            lang = result.group(1)
            update_strings(lang, page.data)

i18n.i18n_hooks.append(load_strings)

def update_strings(lang, data):
    strings = i18n.get_strings()
    items = [(key.split('.', 1)[1], value) for key, value in data.iteritems() if '.' in key]
    strings[lang] = dict(items)

# register i18n templates
register_wiki_template("i18n View Template", 
                       "plugins/i18n/templates/view.html",
                       "templates/i18n/view.tmpl")

register_wiki_template("i18n edit Template", 
                       "plugins/i18n/templates/edit.html",
                       "templates/i18n/edit.tmpl")

@infogami.install_hook
@infogami.action
def movestrings():
    """Moves i18n strings to wiki."""
    from infogami.core import db
    web.load()
    web.ctx.ip=""
    
    strings = {}
    
    for p in delegate.plugins:
        name = os.path.basename(p)
        data = i18n.load_plugin(p)
        for lang, xstrings in data.iteritems():
            if lang not in strings:
                strings[lang] = {}
            for key, value in xstrings.iteritems():
                strings[lang][name + '.' + key] = value
    
    for lang, xstrings in strings.iteritems():
        wikipath = "i18n/strings." + lang
        db.new_version(config.site, wikipath, None,
            web.storage(template="i18n", **xstrings))

@public
def get_i18n_keys(plugin):
    keys = i18n.get_keys()
    return keys.get(plugin, {})

