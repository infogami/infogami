import web
from infogami.core import db

class SQL:
    def get_all_templates(self, url):
        d = web.query("SELECT path FROM page JOIN site ON (page.site_id=site.id) \
            WHERE site.url=$url AND page.path LIKE 'templates/%%.tmpl'", vars=locals())
        return [db.get_version(url, p.path) for p in d]


from infogami.utils.delegate import pickdb
pickdb(globals())
