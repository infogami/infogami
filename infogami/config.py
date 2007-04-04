"""
Infogami configuration.
"""

import web

internalerror = web.debugerror
middleware = [web.reloader]

web.db._hasPooling = False

db_printing = True
db_kind = 'SQL'

db_parameters = None
site = None

plugins = ['links', 'wikitemplates', 'i18n']
