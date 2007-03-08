import web
from infogami.core import db

class SQL:
    def get_all_templates(self, url):
        d = web.query("SELECT page.path, MAX(version.id) FROM page \
            JOIN site ON (page.site_id=site.id) \
            JOIN version ON (version.page_id = page.id) \
            JOIN datum ON (datum.version_id = version.id) \
            WHERE site.url=$url \
                AND datum.key='template' \
                AND datum.value='template' \
            GROUP BY page.path", vars=locals())

        return [db.get_version(url, p.path) for p in d]


from infogami.utils.delegate import pickdb
pickdb(globals())
