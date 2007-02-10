from infogami.core import db
import web

class SQL:
    def new_links(self, url, path, links):
        site_id = db.get_site_id(url)
        page_id = db.get_page_id(url, path)
        web.transact()
        web.delete('backlinks', where="site_id=$site_id AND page_id=$page_id", vars=locals())
        for link in links:
            web.insert('backlinks', False, site_id=site_id, page_id=page_id, link=link)
        web.commit()
    
    def get_links(self, url, path):
        site_id = db.get_site_id(url)
        return web.query("""SELECT page.* FROM page 
          JOIN backlinks ON page.id = backlinks.page_id
          WHERE page.site_id = $site_id AND backlinks.site_id = $site_id
          AND backlinks.link = $path
        """, vars=locals())

from infogami.utils.delegate import pickdb
pickdb(globals())
