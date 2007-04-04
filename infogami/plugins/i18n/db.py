from infogami.core import db
from infogami import tdb

def get_all_strings(site_id):
    type = db.get_type('i18n', create=True)
    return tdb.Things(type_id=type.id, parent_id=site_id)
