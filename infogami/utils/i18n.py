"""
Support for Internationalization.
"""

import web

DEFAULT_LANG = 'en'

class i18n:
    def __init__(self):
        self._data = {}
        
    def getkeys(self):
        keys = set()
        for lang in self._data:
            keys.update(self._data[lang].keys())
        return sorted(keys)
        
    def _set_strings(self, lang, data):
        self._data[lang] = dict(data)
        
    def _update_strings(self, lang, data):
        self._data.setdefault(lang, {}).update(data)
        
    def __getattr__(self, key):
        if not key.startswith('__'):
            return self[key]
        else:
            raise AttributeError, key
            
    def __getitem__(self, key):
        return i18n_string(self, key)
            
class i18n_string:
    def __init__(self, i18n, key):
        self._i18n = i18n
        self._key = key
        
    def __str__(self):
        default_data = self._i18n._data.get(DEFAULT_LANG) or {}
        data = self._i18n._data.get(web.ctx.lang) or default_data
        return data.get(self._key) or default_data.get(self._key) or self._key
    
    def __call__(self, *a):
        return str(self) % a

def i18n_loadhook():
    """Load hook to set web.ctx.lang bases on HTTP_ACCEPT_LANGUAGE header."""
    accept_language = web.ctx.get('env', {}).get('HTTP_ACCEPT_LANGUAGE', '')

    re_accept_language = web.re_compile(', *')
    tokens = re_accept_language.split(accept_language)

    # take just the language part. ignore other details.
    # for example `en-gb;q=0.8` will be treated just as `en`.
    langs = [t[:2] for t in tokens]
    web.ctx.lang = langs and langs[0] or ''

def load_strings(plugin_path):
    """Load string.xx files from plugin/i18n/string.* files."""
    import os.path
    import glob
    
    def parse_lang(path):
        """Find lang from extenstion."""
        _, extn = os.path.splitext(p)
        return extn[1:] # strip dot
        
    def read_strings(path):
        env = {}
        execfile(path, env)
        # __builtins__ gets added by execfile
        del env['__builtins__']
        return env

    path = os.path.join(plugin_path, "i18n", "strings.*")
    for p in glob.glob(path):
        try:
            print >> web.debug, "load", p
            lang = parse_lang(p)
            data = read_strings(p)
            strings._update_strings(lang, data)
        except:
            print >> web.debug, "failed to load strings from", p

# global state
strings = i18n()
web._loadhooks['i18n'] = i18n_loadhook
