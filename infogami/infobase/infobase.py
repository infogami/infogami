"""
Infobase: structured database.

Infobase contains multiple sites and each site can store any number of objects. 
Each object has a key, that is unique to the site it belongs.
"""
import web
import datetime

import common
import readquery
import writequery

class Infobase:
    def __init__(self, store):
        self.store = store
        import account
        self.account_manager = account.AccountManager(self, 'admin123')
        
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
        q = writequery.make_query(self.store, query)
        return self.store.write(q, timestamp=timestamp, comment=comment, machine_comment=machine_comment, ip=ip, author=author)
        
    def things(self, query):
        q = readquery.make_query(self.store, query)
        return self.store.things(q)
        
    def versions(self, query):
        q = readquery.make_versions_query(self.store, query)
        return self.store.versions(q)
        
    def get_permissions(self, key):
        return web.storage(write=True, admin=True)
        
    def bootstrap(self, admin_password='admin'):
        import bootstrap
        query = bootstrap.make_query()
        
        self.store.initialize()
        self.write(query)
        
        a = self.get_account_manager()
        a.register(username="admin", email="admin@example.com", password=admin_password, data=dict(displayname="Administrator"))
        a.register(username="useradmin", email="useradmin@example.com", password=admin_password, data=dict(displayname="User Administrator"))
        
if __name__ == "__main__":
    import web
    web.config.db_parameters = dict(dbn='postgres', db='infobase2', user='anand', pw='')
    web.config.db_printing = True
    web.load()
    
    from dbstore import Schema, DBStore
    
    schema = Schema()
    schema.add_table_group('sys', '/type/type')
    schema.add_table_group('sys', '/type/property')
    schema.add_table_group('sys', '/type/backreference')
    store = DBStore(schema)
    ibase = Infobase(store)
    
    import bootstrap
    bootstrap.bootstrap(ibase, 'admin123')
