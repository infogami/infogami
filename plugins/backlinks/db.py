from core import db
import web

class SQL:
    def new_link(self, url, path, link):
        site_id = db.get_site_id(url)
        page_id = db.get_page_id(url, path)
        web.insert('backlinks', False, site_id=site_id, page_id=page_id, link=link)
    
    def get_links(self, url, path):
        site_id = db.get_site_id(url)
        #XXX: this gives me only the ids of the pages, which have link to path.
        # it is lot of work to get the title of all these pages (required for display).
        # what about different versions?
        # is something going wrong?
        return web.select('backlinks', where="site_id=$site_id and link=$path", vars=locals())

from utils.delegate import pickdb
pickdb(globals())
