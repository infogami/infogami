"""
Infobase: structured database.

Infobase is a structured database which contains multiple sites.
Each site is an independent collection of objects. 
"""
import web
import datetime

import common
import readquery
import writequery

class Infobase:
    """Infobase contains multiple sites."""
    def __init__(self, store, secret_key):
        self.store = store
        self.secret_key = secret_key
        self.sites = {}
        
    def create(self, sitename):
        """Creates a new site with the sitename."""
        site = Site(self.store.create(sitename), self.secret_key)
        site.bootstrap()
        self.sites[sitename] = site
        return site
    
    def get(self, sitename):
        """Returns the site with the given name."""
        if sitename in self.sites:
            site = self.sites[sitename]
        else:
            store = self.store.get(sitename)
            if store is None:
                return None
            site = Site(self.store.get(sitename), self.secret_key)
            self.sites[sitename] = site
        return site
        
    def delete(self, sitename):
        """Deletes the site with the given name."""
        if sitename in self.sites:
            del self.sites[sitename]
        return self.store.delete(sitename)

class Site:
    """A site of infobase."""
    def __init__(self, store, secret_key):
        self.store = store
        self.store = common.CachedSiteStore(store)
        import account
        self.account_manager = account.AccountManager(self, secret_key)
        
    def get_account_manager(self):
        return self.account_manager
    
    def get(self, key, revision=None):
        thing = self.store.get(key, revision)
        return thing
        
    withKey = get

    def get_many(self, keys):
        return self.store.get_many(keys)
        
    def new_key(self, type, kw=None):
        return self.store.new_key(type, kw or {})
        
    def write(self, query, timestamp=None, comment=None, machine_comment=None, ip=None, author=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        
        author = self.get_account_manager().get_user()
        q = writequery.make_query(self.store, author, query)
        ip = web.ctx.get('ip', '127.0.0.1')
        return self.store.write(q, timestamp=timestamp, comment=comment, machine_comment=machine_comment, ip=ip, author=author and author.key)
        
    def things(self, query):
        q = readquery.make_query(self.store, query)
        return self.store.things(q)
        
    def versions(self, query):
        q = readquery.make_versions_query(self.store, query)
        return self.store.versions(q)
        
    def get_permissions(self, key):
        author = self.get_account_manager().get_user()
        perm = writequery.has_permission(self.store, author, key)
        return web.storage(write=perm, admin=perm)
        
    def bootstrap(self, admin_password='admin123'):
        import bootstrap
        query = bootstrap.make_query()
        
        self.write(query)     
        a = self.get_account_manager()
        a.register(username="admin", email="admin@example.com", password=admin_password, data=dict(displayname="Administrator"))
        a.register(username="useradmin", email="useradmin@example.com", password=admin_password, data=dict(displayname="User Administrator"))

if __name__ == '__main__':
    web.config.db_parameters = dict(dbn='postgres', db='infobase2', user='anand', pw='')
    web.config.db_printing = True
    web.load()
    import dbstore, config
    schema = dbstore.Schema()
    store = dbstore.DBStore(schema)
    _infobase = Infobase(store, config.secret_key)
    print _infobase.create('infogami.org')
