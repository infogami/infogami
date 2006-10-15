import web
from utils import delegate

class DB: pass

class SQL(DB):
    def _set_data(self, version_id, data):
        for k, v in data.iteritems():
            web.insert('datum', key=k, value=v, version_id=version_id)
    
    def _get_data(self, dd):
        out = web.storage()
        for row in dd:
            out[row.key] = row.value
        return out

    def new_site(self, url):
        return web.insert('site', url=url)

    def new_page(self, url, path):
        return web.insert('page', path=path, site_id=self.get_site_id(url))

    def new_version(self, url, path, data):
        page_id = self.get_page_id(url, path) or self.new_page(url, path)
        id = web.insert('version', page_id=page_id)
        self._set_data(id, data)
        #XXX: is it a good idea to make this a decorator?
        delegate.run_hooks('on_new_version', url, path, data['body'])
        return id

    def _version_query(self, date):
        q = "SELECT version.* FROM version JOIN page ON (version.page_id = page.id) \
          JOIN site ON (page.site_id = site.id) \
          WHERE site.url = $url AND page.path = $path"
        if date is None:
            q += " ORDER BY created DESC LIMIT 1"
        else:
            q += " AND date_trunc('second', created) = date_trunc('second', TIMESTAMP $date)"
        return q
    
    def get_site_id(self, url):
        return web.select('site', where='url = $url', vars=locals())[0].id
    
    def get_page_id(self, url, path):
        d = web.query("SELECT page.* FROM page JOIN site ON page.site_id = site.id \
          WHERE site.url = $url AND page.path = $path", vars=locals())
        return (d and d[0].id) or None

    def get_version(self, url, path, date=None):
        date = date and web.dateify(date)
        vd = web.query(self._version_query(date), vars=locals())[0]
        dd = web.query("SELECT * FROM datum WHERE version_id = $vd.id", vars=locals())
        vd.data = self._get_data(dd)
        return vd

    def get_all_versions(self, url, path):
        return web.query("SELECT version.* FROM version \
          JOIN page ON (version.page_id = page.id) \
          JOIN site ON (page.site_id = site.id) \
          WHERE site.url = $url AND page.path = $path \
          ORDER BY version.id DESC", vars=locals())
        return d

from utils.delegate import pickdb
pickdb(globals())
