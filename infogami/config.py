"""
Infogami configuration.
"""

import web

internalerror = web.debugerror
middleware = [web.reloader]

db_printing = True
db_kind = 'SQL'

db_parameters = None
site = None
