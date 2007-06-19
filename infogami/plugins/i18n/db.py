from infogami.core import db
from infogami import tdb

def get_all_strings(site):
    return tdb.Things(type=db.get_type(site, 'type/i18n'), parent=site)
