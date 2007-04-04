from infogami.core import db
from infogami import tdb

def get_links_type():
    linkstype = db.get_type('links') or db.new_type('links')
    linkstype.save()
    return linkstype
    
def new_links(page, links):
    # for links thing: parent=page, type=linkstype
    site_id = page.parent_id
    path = page.name
    d = {'site_id': site_id, 'path': path, 'links': list(links)}
    
    try:
        backlinks = tdb.withName("links", page.id)
        backlinks.setdata(d)
        backlinks.save()
    except tdb.NotFound:
        backlinks = tdb.new("links", page.id, get_links_type().id, d)
        backlinks.save()

def get_links(site_id, path):
    return tdb.Things(type_id=get_links_type().id, site_id=site_id, links=path)