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
        
    def delete(self):
        return self._infobase.delete(self.sitename)
    
    def get(self, key, revision=None):
        return self.store.get(key, revision)
        
    withKey = get
    
    def _get_thing(self, key, revision=None):
        json = self.get(key, revision)
        return json and common.Thing.from_json(self.store, key, json)

    def get_many(self, keys):
        return self.store.get_many(keys)
        
    def new_key(self, type, kw=None):
        return self.store.new_key(type, kw or {})
        
    def write(self, query, timestamp=None, comment=None, machine_comment=None, ip=None, author=None, action=None, _internal=False):
        timestamp = timestamp or datetime.datetime.utcnow()
        
        author = author or self.get_account_manager().get_user()
        p = writequery.WriteQueryProcessor(self.store, author)
        
        items = p.process(query)
        items = (item for item in items if item)
        result = self.store.save_many(items, timestamp, comment, machine_comment, ip, author and author.key, action=action)


        created = [r['key'] for r in result if r and r['revision'] == 1]
        updated = [r['key'] for r in result if r and r['revision'] != 1]

        result2 = web.storage(created=created, updated=updated)
        
        if not _internal:
            data = dict(comment=comment, machine_comment=machine_comment, query=query, result=result2)
            self._fire_event("write", timestamp, ip, author and author.key, data)
            
        self._fire_triggers(result)

        return result2
    
    def save(self, key, data, timestamp=None, comment=None, machine_comment=None, ip=None, author=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        author = author or self.get_account_manager().get_user()
        ip = ip or web.ctx.get('ip', '127.0.0.1')
        
        #@@ why to have key argument at all?
        data['key'] = key
        
        p = writequery.SaveProcessor(self.store, author)
        data = p.process(key, data)
        
        if data:
            result = self.store.save(key, data, timestamp, comment, machine_comment, ip, author and author.key)
        else:
            result = {}
        
        event_data = dict(comment=comment, machine_comment=machine_comment, key=key, query=data, result=result)
        self._fire_event("save", timestamp, ip, author and author.key, event_data)
        self._fire_triggers([result])
        return result
    
    def save_many(self, query, timestamp=None, comment=None, machine_comment=None, ip=None, author=None, action=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        author = author or self.get_account_manager().get_user()
        ip = ip or web.ctx.get('ip', '127.0.0.1')
        
        p = writequery.SaveProcessor(self.store, author)        

        items = query
        items = (p.process(item['key'], item) for item in items)
        items = (item for item in items if item)
        result = self.store.save_many(items, timestamp, comment, machine_comment, ip, author and author.key, action=action)
        
        event_data = dict(comment=comment, machine_comment=machine_comment, query=query, result=result)
        self._fire_event("save_many", timestamp, ip, author and author.key, event_data)

        self._fire_triggers(result)
        return result

    def _fire_event(self, name, timestamp, ip, username, data):
        event = common.Event(self.sitename, name, timestamp, ip, username, data)
        self._infobase.fire_event(event)
        
    def things(self, query):
        return readquery.run_things_query(self.store, query)
        
    def versions(self, query):
        try:
            q = readquery.make_versions_query(self.store, query)
        except ValueError:
            # ValueError is raised if unknown keys are used in the query. 
            # Invalid keys shouldn't make the query fail, instead the it should result in no match.
            return []
            
        return self.store.versions(q)
        
    def get_permissions(self, key):
        author = self.get_account_manager().get_user()
        perm = writequery.has_permission(self.store, author, key)
        return web.storage(write=perm, admin=perm)
        
    def bootstrap(self, admin_password='admin123'):
        import bootstrap
        web.ctx.ip = '127.0.0.1'
        
        import cache
        cache.loadhook()
        
        bootstrap.bootstrap(self, admin_password)
        
    def add_trigger(self, type, func):
        """Registers a trigger to call func when object of specified type is modified. 
        If type=None is specified then the trigger is called for every modification.
        func is called with old object and new object as arguments. old object will be None if the object is newly created.
        """
        self._triggers.setdefault(type, []).append(func)
                
    def _fire_triggers(self, result):
        """Executes all required triggers on write."""
        def fire_trigger(type, old, new):
            triggers = self._triggers.get(type.key, []) + self._triggers.get(None, [])
            for t in triggers:
                try:
                    t(self, old, new)
                except:
                    print >> web.debug, 'Failed to execute trigger', t
                    import traceback
                    traceback.print_exc()
                    
        created = [r['key'] for r in result if r and r['revision'] == 1]
        updated = [r['key'] for r in result if r and r['revision'] != 1]
        
        for key in created:
            thing = self._get_thing(key)
            fire_trigger(thing.type, None, thing)
        
        for key in updated:
            thing = self._get_thing(key)
            old = self._get_thing(key, thing.revision-1)
            if old.type.key == thing.type.key:
                fire_trigger(thing.type, old, thing)
            else:
                fire_trigger(old.type, old, thing)
                fire_trigger(thing.type, old, thing)