from infogami.core import db
from infogami import tdb

def get_all_strings(site):
    return tdb.Things(type=db.get_type(site, 'type/i18n'), parent=site)

def get_all_sites():
    return [t for t in tdb.Things(type=tdb.root, parent=tdb.root) if t.id != 1]
