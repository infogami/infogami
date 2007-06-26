from infogami.core import db
from infogami import tdb

def get_all_templates(site):
    return tdb.Things(type=db.get_type(site, 'type/template'), parent=site)

def get_all_macros(site):
    return tdb.Things(type=db.get_type(site, 'type/macro'), parent=site)
    
def get_all_sites():
    return [t for t in tdb.Things(type=tdb.root, parent=tdb.root) if t.id != 1]
