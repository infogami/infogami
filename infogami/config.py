"""
Infogami configuration.
"""

import web

internalerror = web.debugerror
middleware = []

cache_templates = True
db_printing = False
db_kind = 'SQL'

db_parameters = None
site = None

plugins = ['links', 'wikitemplates', 'i18n']

plugin_path = ['infogami.plugins']
