from infogami.core import db
from infogami import tdb

def get_all_templates(site_id):
    template_type = db.get_type('template', create=True)
    return tdb.Things(type_id=template_type.id, parent_id=site_id)
