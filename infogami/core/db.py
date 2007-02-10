from infogami.utils import delegate
import web

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
    
    def new_version(self, url, path, author_id, data):
        page_id = self.get_page_id(url, path) or self.new_page(url, path)
        web.transact()
        try:
            id = web.insert('version', page_id=page_id, author_id=author_id, ip_address=web.ctx.ip)
            web.query('UPDATE version SET revision=(SELECT max(revision)+1 FROM version WHERE page_id=$page_id) WHERE id=$id', vars=locals())
        except:
            web.rollback()
            raise
        else:
            web.commit()

        self._set_data(id, data)
        delegate.run_hooks('on_new_version', url, path, data['body'])
        return id
    
    def _version_query(self, revision=None):
        q = "SELECT version.*, login.name as author FROM version \
          JOIN page ON (version.page_id = page.id) \
          JOIN site ON (page.site_id = site.id) \
          LEFT JOIN login ON (login.id = version.author_id) \
          WHERE site.url = $url AND page.path = $path"
        if revision is None:
            q += " ORDER BY revision DESC LIMIT 1"
        else:
            q += " AND revision=$revision"
        return q
    
    def get_site_id(self, url):
        return web.select('site', where='url = $url', vars=locals())[0].id
    
    def get_page_id(self, url, path):
        d = web.query("SELECT page.* FROM page JOIN site ON page.site_id = site.id \
          WHERE site.url = $url AND page.path = $path", vars=locals())
        return (d and d[0].id) or None
    
    def get_random_page(self, url):
        d = web.query("SELECT page.* FROM page JOIN site ON page.site_id = site.id \
          WHERE site.url = $url ORDER BY RANDOM() LIMIT 1", vars=locals())
        return (d and d[0]) or None
    
    def get_all_pages(self, url):
        return web.query("SELECT page.* FROM page JOIN site ON page.site_id = site.id \
          WHERE site.url = $url ORDER BY page.path", vars=locals())
    
    def get_version(self, url, path, revision=None):
        vd = web.query(self._version_query(revision), vars=locals())[0]
        dd = web.query("SELECT * FROM datum WHERE version_id = $vd.id", vars=locals())
        vd.data = self._get_data(dd)
        return vd
    
    def get_all_versions(self, url, path):
        return web.query("SELECT version.*, login.name AS author FROM version \
          JOIN page ON (version.page_id = page.id) \
          JOIN site ON (page.site_id = site.id) \
          LEFT OUTER JOIN login ON (login.id = version.author_id) \
          WHERE site.url = $url AND page.path = $path \
          ORDER BY version.id DESC", vars=locals())
        return d
    
    def get_recent_changes(self, url):
        return web.query("SELECT login.name AS author, version.revision, version.created, version.ip_address, page.path FROM version \
            JOIN page ON version.page_id = page.id \
            JOIN site ON page.site_id = site.id \
            LEFT OUTER JOIN login ON (login.id = version.author_id) \
            WHERE site.url = $url \
            ORDER BY version.created DESC", vars=locals())
    
    def new_user(self, name, email, password):
        return web.insert('login', name=name, email=email, password=password)
    
    def login(self, name, password):
        d = web.query("SELECT * FROM login WHERE name=$name AND password=$password", vars=locals())
        return (d and d[0]) or None
    
    def get_user(self, user_id):
        d = web.query("SELECT * FROM login WHERE id=$user_id", vars=locals())
        return (d and d[0]) or None
    
    def get_user_by_name(self, name):
        d = web.query("SELECT * FROM login WHERE name=$name", vars=locals())
        return (d and d[0]) or None

from infogami.utils.delegate import pickdb
pickdb(globals())
