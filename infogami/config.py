"""
Infogami configuration.
"""


def get(name, default=None):
    return globals().get(name, default)


middleware = []  # type: ignore

cache_templates = True
db_printing = False
db_kind = 'SQL'

db_parameters: dict[str, str] | None = None
infobase_host = None
site = "infogami.org"

plugins = ['links']
plugin_modules = []  # type: ignore

plugin_path = ['infogami.plugins']

# key for encrypting password
encryption_key = "ofu889e4i5kfem"

# salt added to password before encrypting
password_salt = "zxps#2s4g@z"

from_address = "noreply@infogami.org"
smtp_server = "localhost"

login_cookie_name = "infogami_session"

infobase_parameters = dict(type='local')
bugfixer = None

admin_password = "admin123"
