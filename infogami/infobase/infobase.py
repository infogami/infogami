"""
Infobase: structured database.

Infobase is a structured database which contains multiple sites.
Each site is an independent collection of objects.
"""

from __future__ import print_function

import datetime

import simplejson
import web

from infogami.infobase import (account, bootstrap, cache, common, config, readquery,
                               writequery)


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
        self.cache = cache.Cache()
        self.store.set_cache(self.cache)
        self.account_manager = account.AccountManager(self, secret_key)

        self._triggers = {}
        store.store.set_listener(self._log_store_action)
        store.seq.set_listener(self._log_store_action)

    def _log_store_action(self, name, data):
        event = web.storage(name=name, ip=web.ctx.ip, author=None, data=data, sitename=self.sitename, timestamp=None)
        self._infobase.fire_event(event)

    def get_account_manager(self):
        return self.account_manager

    def get_store(self):
        return self.store.get_store()

    def get_seq(self):
        return self.store.seq

    def delete(self):
        return self._infobase.delete(self.sitename)

    def get(self, key, revision=None):
        return self.store.get(key, revision)

    withKey = get

    def _get_thing(self, key, revision=None):
        json = self.get(key, revision)
        return json and common.Thing.from_json(self.store, key, json)

    def _get_many_things(self, keys):
        json = self.get_many(keys)
        d = simplejson.loads(json)
        return dict((k, common.Thing.from_dict(self.store, k, doc)) for k, doc in list(d.items()))

    def get_many(self, keys):
        return self.store.get_many(keys)

    def new_key(self, type, kw=None):
        return self.store.new_key(type, kw or {})

    def write(self, query, timestamp=None, comment=None, data=None, ip=None, author=None, action=None, _internal=False):
        timestamp = timestamp or datetime.datetime.utcnow()

        author = author or self.get_account_manager().get_user()
        p = writequery.WriteQueryProcessor(self.store, author)

        items = p.process(query)
        items = (item for item in items if item)
        changeset = self.store.save_many(items, timestamp, comment, data, ip, author and author.key, action=action)
        result = changeset.get('docs', [])

        created = [r['key'] for r in result if r and r['revision'] == 1]
        updated = [r['key'] for r in result if r and r['revision'] != 1]

        result2 = web.storage(created=created, updated=updated)

        if not _internal:
            event_data = dict(comment=comment, data=data, query=query, result=result2, changeset=changeset)
            self._fire_event("write", timestamp, ip, author and author.key, event_data)

        self._fire_triggers(result)

        return result2

    def save(self, key, doc, timestamp=None, comment=None, data=None, ip=None, author=None, action=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        author = author or self.get_account_manager().get_user()
        ip = ip or web.ctx.get('ip', '127.0.0.1')

        #@@ why to have key argument at all?
        doc['key'] = key

        p = writequery.SaveProcessor(self.store, author)
        doc = p.process(key, doc)

        if not doc:
            return {}
        else:
            changeset = self.store.save(key, doc, timestamp, comment, data, ip, author and author.key, action=action)
            saved_docs = changeset.get("docs")
            saved_doc = saved_docs[0]
            result={"key": saved_doc['key'], "revision": saved_doc['revision']}

            event_data = dict(comment=comment, key=key, query=doc, result=result, changeset=changeset)
            self._fire_event("save", timestamp, ip, author and author.key, event_data)
            self._fire_triggers([saved_doc])
            return result

    def save_many(self, query, timestamp=None, comment=None, data=None, ip=None, author=None, action=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        author = author or self.get_account_manager().get_user()
        ip = ip or web.ctx.get('ip', '127.0.0.1')

        p = writequery.SaveProcessor(self.store, author)

        items = p.process_many(query)
        if not items:
            return []

        changeset = self.store.save_many(items, timestamp, comment, data, ip, author and author.key, action=action)
        saved_docs = changeset.get('docs')

        result = [{"key": doc["key"], "revision": doc['revision']} for doc in saved_docs]
        event_data = dict(comment=comment, query=query, result=result, changeset=changeset)
        self._fire_event("save_many", timestamp, ip, author and author.key, event_data)

        self._fire_triggers(saved_docs)
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

    def recentchanges(self, query):
        return self.store.recentchanges(query)

    def get_change(self, id):
        return self.store.get_change(id)

    def get_permissions(self, key):
        author = self.get_account_manager().get_user()
        engine = writequery.PermissionEngine(self.store)
        perm = engine.has_permission(author, key)
        return web.storage(write=perm, admin=perm)

    def bootstrap(self, admin_password='admin123'):
        web.ctx.ip = '127.0.0.1'
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
            triggers = self._triggers.get(type['key'], []) + self._triggers.get(None, [])
            for t in triggers:
                try:
                    t(self, old, new)
                except:
                    print('Failed to execute trigger', t, file=web.debug)
                    import traceback
                    traceback.print_exc()

        if not self._triggers:
            return

        created = [doc['key'] for doc in result if doc and doc['revision'] == 1]
        updated = [doc['key'] for doc in result if doc and doc['revision'] != 1]

        things = dict((doc['key'], doc) for doc in result)

        for key in created:
            thing = things[key]
            fire_trigger(thing['type'], None, thing)

        for key in updated:
            thing = things[key]

            # old_data (the second argument) is not used anymore.
            # TODO: Remove the old_data argument.
            fire_trigger(thing['type'], None, thing)

            #old = self._get_thing(key, thing.revision-1)
            #if old.type.key == thing.type.key:
            #    fire_trigger(thing.type, old, thing)
            #else:
            #    fire_trigger(old.type, old, thing)
            #    fire_trigger(thing.type, old, thing)
