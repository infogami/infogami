"""
Support for Internationalization.
"""
from __future__ import print_function

import web

DEFAULT_LANG = 'en'

def find_i18n_namespace(path):
    """Finds i18n namespace from the path.

        >>> find_i18n_namespace('/i18n/type/type/strings.en')
        '/type/type'
        >>> find_i18n_namespace('/i18n/strings.en')
        '/'
    """
    import os.path
    return os.path.dirname(web.lstrips(path, '/i18n'))

class i18n:
    def __init__(self):
        self._data = {}

    def get_locale(self):
        return web.ctx.lang

    def get_namespaces(self):
        return sorted(set(k[0] for k in self._data))

    def get_languages(self):
        return sorted(set(k[1] for k in self._data))

    def get_count(self, namespace, lang=None):
        lang = lang or DEFAULT_LANG
        return len(self._data.get((namespace, lang)) or {})

    def get_namespace(self, namespace):
        return i18n_namespace(self, namespace)

    def getkeys(self, namespace, lang=None):
        namespace = web.safestr(namespace)
        lang = web.safestr(lang)

        # making a simplified assumption here.
        # Keys for a language are all the strings defined for that language and
        # all the strings defined for default language. By doing this, once a key is
        # added to default lang, then it will automatically appear in all other languages.
        keys = set(self._data.get((namespace, lang), {}).keys() + self._data.get((namespace, DEFAULT_LANG), {}).keys())
        return sorted(keys)

    def _set_strings(self, namespace, lang, data):
        namespace = web.safestr(namespace)
        lang = web.safestr(lang)
        self._data[namespace, lang] = dict(data)

    def _update_strings(self, namespace, lang, data):
        namespace = web.safestr(namespace)
        lang = web.safestr(lang)
        self._data.setdefault((namespace, lang), {}).update(data)

    def get(self, namespace, key):
        namespace = web.safestr(namespace)
        key = web.safestr(key)
        return i18n_string(self, namespace, key)

    def __getattr__(self, key):
        if not key.startswith('__'):
            return self[key]
        else:
            raise AttributeError(key)

    def __getitem__(self, key):
        namespace = web.ctx.get('i18n_namespace', '/')
        key = web.safestr(key)
        return i18n_string(self, namespace, key)

class i18n_namespace:
    def __init__(self, i18n, namespace):
        self._i18n = i18n
        self._namespace = namespace

    def __getattr__(self, key):
        if not key.startswith('__'):
            return self[key]
        else:
            raise AttributeError(key)

    def __getitem__(self, key):
        return self._i18n.get(self._namespace, key)

class i18n_string:
    def __init__(self, i18n, namespace, key):
        self._i18n = i18n
        self._namespace = namespace
        self._key = key

    def __str__(self):
        def get(lang):
            return self._i18n._data.get((self._namespace, lang))
        default_data = get(DEFAULT_LANG) or {}
        data = get(web.ctx.lang) or default_data
        text = data.get(self._key) or default_data.get(self._key) or self._key
        return web.safestr(text)

    def __call__(self, *a):
        try:
            a = [x or "" for x in a]
            return str(self) % tuple(web.safestr(x) for x in a)
        except:
            print('failed to substitute (%s/%s) in language %s' % (self._namespace, self._key, web.ctx.lang), file=web.debug)
        return str(self)

def i18n_loadhook():
    """Load hook to set web.ctx.lang bases on HTTP_ACCEPT_LANGUAGE header."""
    def parse_lang_header():
        """Parses HTTP_ACCEPT_LANGUAGE header."""
        accept_language = web.ctx.get('env', {}).get('HTTP_ACCEPT_LANGUAGE', '')

        re_accept_language = web.re_compile(', *')
        tokens = re_accept_language.split(accept_language)

        # take just the language part. ignore other details.
        # for example `en-gb;q=0.8` will be treated just as `en`.
        langs = [t[:2] for t in tokens]
        return langs and langs[0]

    def parse_lang_cookie():
        """Parses HTTP_LANG cookie."""
        # Quick check to avoid making cookies call
        if "HTTP_LANG" in web.ctx.get("HTTP_COOKIE", ""):
            cookies = web.cookies()
            return cookies.get('HTTP_LANG')

    def parse_query_string():
        # Quick check to avoid parsing query string
        if "lang=" in web.ctx.env.get("QUERY_STRING", ""):
            i = web.input(lang=None, _method="GET")
            return i.lang

    try:
        web.ctx.lang = parse_query_string() or parse_lang_cookie() or parse_lang_header() or ''
    except:
        import traceback
        traceback.print_exc()
        web.ctx.lang = None

def find(path, pattern):
    """Find all files matching the given pattern in the file hierarchy rooted at path.
    """
    import os
    import re
    for dirname, dirs, files in os.walk(path):
        for f in files:
            if re.match(pattern, f):
                yield os.path.join(dirname, f)

def dirstrip(f, dir):
    """Strips dir from f.
        >>> dirstrip('a/b/c/d', 'a/b/')
        'c/d'
    """
    f = web.lstrips(f, dir)
    return web.lstrips(f, '/')

def read_strings(path):
    """Return a version of file's contents without __builtins__
    (which gets added by execfile
    """
    env = {}
    with open(path) as in_file:
        exec(in_file.read(), env)
    if '__builtins__' in env:
        del env['__builtins__']
    return env
    
def load_strings(plugin_path):
    """Load string.xx files from plugin/i18n/string.* files."""
    import os.path
    import glob

    def parse_path(path):
        """Find namespace and lang from path."""
        namespace = os.path.dirname(path)
        _, extn = os.path.splitext(p)
        return '/' + namespace, extn[1:] # strip dot

    root = os.path.join(plugin_path, 'i18n')
    for p in find(root, r'strings\..*'):
        try:
            namespace, lang = parse_path(dirstrip(p, root))
            data = read_strings(p)
            strings._update_strings(namespace, lang, data)
        except:
            import traceback
            traceback.print_exc()
            print("failed to load strings from", p, file=web.debug)

# global state
strings = i18n()
if hasattr(web, "_loadhooks"):
    web._loadhooks['i18n'] = i18n_loadhook
