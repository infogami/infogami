from infogami.core import db
from infogami import tdb

def get_all_templates(site):
    template_type = db.get_type('template', create=True)
    return tdb.Things(type=template_type, parent=site)

def get_all_macros(site):
    """"""
    macro_type = db.get_type('macro', create=True)
    return tdb.Things(type=macro_type, parent=site)
    
def get_all_sites():
    site_type = db.get_type('site', create=True)
    return tdb.Things(type=site_type, parent=site_type)
