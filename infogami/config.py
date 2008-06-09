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
infobase_host = None
site = None

plugins = ['links', 'wikitemplates']

plugin_path = ['infogami.plugins']

# key for encrypting password
encryption_key = "ofu889e4i5kfem" 

# salt added to password before encrypting
password_salt = "zxps#2s4g@z"

from_address = "noreply@infogami.org"
smtp_server = "localhost"

infobase_parameters = dict(type='local')