"""
Infobase: structured database.

Infobase is a structured database which contains multiple sites.
Each site is an independent collection of objects. 
"""
import web
import datetime

import common
import config
import readquery
import writequery

# important: this is required here to setup _loadhooks and unloadhooks
import cache

class Infobase:
    """Infobase contains multiple sites."""
    def __init__(self, store, secret_key):
        self.store = store
        self.secret_key = secret_key
        self.sites = {}
        self.event_listeners = []
        
        if config.startup_hook:
            config.startup_hook(self)
        
    def create(self, sitename):
        """Creates a new site with the sitename."""
        site = Site(self, sitename, self.store.create(sitename), self.secret_key)
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
            site = Site(self, sitename, self.store.get(sitename), self.secret_key)
            self.sites[sitename] = site
        return site
        
    def delete(self, sitename):
        """Deletes the site with the given name."""
        if sitename in self.sites:
            del self.sites[sitename]
        return self.store.delete(sitename)
        
    def add_event_listener(self, listener):
        self.event_listeners.append(listener)
    
    def remove_event_listener(self, listener):
        try:
            self.event_listeners.remove(listener)
        except ValueError:
            pass

    def fire_event(self, event):
        for listener in self.event_listeners:
            try:
                listener(event)
            except:
                common.record_exception()
                pass
        
class Site:
    """A site of infobase."""
    def __init__(self, _infobase, sitename, store, secret_key):
        self._infobase = _infobase
        self.sitename = sitename
        self.store = store
        self.store.set_cache(cache.Cache())
        
        import account
        self.account_manager = account.AccountManager(self, secret_key)
        
        self._triggers = {}
        
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
        
    def write(self, query, timestamp=None, comment=None, machine_comment=None, ip=None, author=None, _internal=False):
        timestamp = timestamp or datetime.datetime.utcnow()
        
        author = author or self.get_account_manager().get_user()
        q = writequery.make_query(self.store, author, query)
        ip = ip or web.ctx.get('ip', '127.0.0.1')
        result = self.store.write(q, timestamp=timestamp, comment=comment, machine_comment=machine_comment, ip=ip, author=author and author.key)
        
        if not _internal:
            # fire event
            data = dict(comment=comment, machine_comment=machine_comment, query=query, result=result)
            self._fire_event("write", timestamp, ip, author and author.key, data)
            self._fire_triggers(result.created, result.updated)
        
        return result
    
    def save(self, key, data, timestamp=None, comment=None, machine_comment=None, ip=None, author=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        author = author or self.get_account_manager().get_user()
        ip = ip or web.ctx.get('ip', '127.0.0.1')
        self.store.save(key, data, timestamp, comment, machine_comment, ip, author)
        
        #@@ TODO: fire event

    def _fire_event(self, name, timestamp, ip, username, data):
        event = common.Event(self.sitename, name, timestamp, ip, username, data)
        self._infobase.fire_event(event)
        
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
        
    def add_trigger(self, type, func):
        """Registers a trigger to call func when object of specified type is modified.
        func is called with old object and new object as arguments. old object will be None if the object is newly created.
        """
        self._triggers.setdefault(type, []).append(func)
                
    def _fire_triggers(self, created, updated):
        """Executes all required triggers on write."""
        def fire_trigger(type, old, new):
            triggers = self._triggers.get(type.key, [])
            for t in triggers:
                try:
                    t(self, old, new)
                except:
                    print >> web.debug, 'Failed to execute trigger', t
                    import traceback
                    traceback.print_exc()
        
        for key in created:
            thing = self.get(key)
            fire_trigger(thing.type, None, thing)
        
        for key in updated:
            thing = self.get(key)
            old = self.get(key, thing.revision-1)
            if old.type.key == thing.type.key:
                fire_trigger(thing.type, old, thing)
            else:
                fire_trigger(old.type, old, thing)
                fire_trigger(thing.type, old, thing)
        
if __name__ == '__main__':
    web.config.db_parameters = dict(dbn='postgres', db='infobase2', user='anand', pw='')
    web.config.db_printing = True
    web.load()
    import dbstore, config
    schema = dbstore.Schema()
    store = dbstore.DBStore(schema)
    _infobase = Infobase(store, config.secret_key)
    print _infobase.create('infogami.org')
