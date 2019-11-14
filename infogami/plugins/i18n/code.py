"""
i18n: allow keeping i18n strings in wiki
"""

from six import iteritems
import web

import infogami
from infogami import config
from infogami.infobase import client
from infogami.plugins.i18n import db
from infogami.utils import delegate, i18n
from infogami.utils.context import context
from infogami.utils.view import public
from infogami.utils.template import render

re_i18n = web.re_compile(r'^/i18n(/.*)?/strings\.([^/]*)$')

class hook(client.hook):
    def on_new_version(self, page):
        """Update i18n strings when a i18n wiki page is changed."""
        if page.type.key == '/type/i18n':
            data = page._getdata()
            load(page.key, data)

def load_strings(site):
    """Load strings from wiki."""
    pages = db.get_all_strings(site)
    for page in pages:
        load(page.key, page._getdata())

def load(key, data):
    result = re_i18n.match(key)
    if result:
        namespace, lang = result.groups()
        namespace = namespace or '/'
        i18n.strings._set_strings(namespace, lang, unstringify(data))

def setup():
    delegate.fakeload()
    from infogami.utils import types
    types.register_type('/i18n(/.*)?/strings.[^/]*', '/type/i18n')

    for site in db.get_all_sites():
        load_strings(site)

def stringify(d):
    """Prefix string_ for every key in a dictionary.

        >>> stringify({'a': 1, 'b': 2})
        {'string_a': 1, 'string_b': 2}
    """
    return dict([('string_' + k, v) for k, v in d.items()])

def unstringify(d):
    """Removes string_ prefix from every key in a dictionary.

        >>> unstringify({'string_a': 1, 'string_b': 2})
        {'a': 1, 'b': 2}
    """
    return dict([(web.lstrips(k, 'string_'), v) for k, v in d.items() if k.startswith('string_')])

def pathjoin(a, *p):
    """Join two or more pathname components, inserting '/' as needed.

        >>> pathjoin('/i18n', '/type/type', 'strings.en')
        '/i18n/type/type/strings.en'
    """
    path = a
    for b in p:
        if b.startswith('/'):
            b = b[1:] # strip /
        if path == '' or path.endswith('/'):
            path +=  b
        else:
            path += '/' + b
    return path

@infogami.install_hook
@infogami.action
def movestrings():
    """Moves i18n strings to wiki."""
    query = []
    for (namespace, lang), d in iteritems(i18n.strings._data):
        q = stringify(d)
        q['create'] = 'unless_exists'
        q['key'] = pathjoin('/i18n', namespace, '/strings.' + lang)
        q['type'] = '/type/i18n'
        query.append(q)
    web.ctx.site.write(query)

setup()
