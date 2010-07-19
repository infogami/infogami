"""Implementation of save for dbstore.
"""
import web
import simplejson
from collections import defaultdict

from indexer import Indexer
from schema import INDEXED_DATATYPES, Schema

from infogami.infobase import config, common

__all__ = ["SaveImpl"]

class SaveImpl:
    """Save implementaion."""
    def __init__(self, db, schema=None, indexer=None, property_manager=None):
        self.db = db
        self.indexUtil = IndexUtil(db, schema, indexer, property_manager and property_manager.copy())
        self.thing_ids = {}
    
    def save(self, docs, timestamp, comment, ip, author, action, machine_comment=None):
        docs = list(docs)
        docs = common.format_data(docs)
        
        if not docs:
            return []
            
        tx = self.db.transaction()
        try:
            records = self._get_records_for_save(docs, timestamp)
            self._update_thing_table(records)
            
            # add transaction
            kw = dict(
                action=action,
                author_id=author and self.get_thing_id(author),
                ip=ip,
                comment=comment, 
                created=timestamp)
            if config.use_bot_column:
                kw['bot'] = bool(author and (self.get_user_details(author) or {}).get('bot', False))
            tx_id = self.db.insert("transaction", **kw)
                
            # add versions
            versions = [dict(thing_id=r.id, revision=r.revision, transaction_id=tx_id) for r in records]
            self.db.multiple_insert('version', versions, seqname=False)

            # add data
            data = [dict(thing_id=r.id, revision=r.revision, data=simplejson.dumps(r.data)) for r in records]
            self.db.multiple_insert('data', data, seqname=False)
            
            self._update_index(records)
        except:
            tx.rollback()
            raise
        else:
            tx.commit()
        return [{"key": r.key, "revision": r.revision} for r in records]
        
    def reindex(self, keys):
        pass
    
    def _update_index(self, records):
        self.indexUtil.update_index(records)
        
    def dedup(self, docs):
        x = set()
        docs2 = []
        for doc in docs[::-1]:
            key = doc['key']
            if key in x:
                continue
            x.add(key)
            docs2.append(doc)
        return docs2[::-1]
            
    def _get_records_for_save(self, docs, timestamp):
        docs = self.dedup(docs)
        keys = [doc['key'] for doc in docs]
        try:
            rows = self.db.query("SELECT thing.*, data.data FROM thing, data" + 
                " WHERE thing.key in $keys" + 
                " AND data.thing_id=thing.id AND data.revision = thing.latest_revision" + 
                " FOR UPDATE NOWAIT",
                vars=locals())
        except:
            raise common.Conflict(keys=keys, reason="Edit conflict detected.")
        
        d = dict((r.key, r) for r in rows)
        
        type_ids = self.get_thing_ids(doc['type']['key'] for doc in docs)
        
        def make_record(doc):
            doc = dict(doc) # make a copy to avoid modifying the original.
            
            key = doc['key']
            r = d.get(key) or web.storage(id=None, key=key, latest_revision=0, type=None, data=None, created=timestamp)
            
            r.revision = r.pop('latest_revision')
            r.data = r.data and simplejson.loads(r.data)
            
            r.prev = web.storage(r)

            r.type = type_ids.get(doc['type']['key'])
            r.revision = r.prev.revision + 1
            r.data = doc
            r.last_modified = timestamp
            
            doc['latest_revision'] = r.revision
            doc['revision'] = r.revision
            doc['created'] = {"type": "/type/datetime", "value": r.created.isoformat()}
            doc['last_modified'] = {"type": "/type/datetime", "value": r.last_modified.isoformat()}
            return r
        
        return [make_record(doc) for doc in docs]
    
    def _fill_types(self, records):
        type_ids = self.get_thing_ids(r.data['type']['key'] for r in records)
        for r in records:
            r.type = type_ids[r.data['type']['key']]
            
    def _update_thing_table(self, records):
        """Insert/update entries in the thing table for the given records."""
        d = dict((r.key, r) for r in records)
        timestamp = records[0].last_modified
                
        # insert new records
        new = [dict(key=r.key, type=r.type, latest_revision=1, created=r.created, last_modified=r.last_modified) 
                for r in records if r.revision == 1]
                
        if new:
            ids = self.db.multiple_insert('thing', new)
            # assign id to the new records
            for r, id in zip(new, ids):
                d[r['key']].id = id

        # type must be filled after entries for new docs is added to thing table. 
        # Otherwise this function will fail when type is also created in the same query.
        self._fill_types(records)
        if any(r['type'] is None for r in new):
            for r in new:
                if r['type'] is None:
                    self.db.update("thing", type=r['type'], where="key=key", vars={"key": r['key']})
                
        # update records with type change
        type_changed = [r for r in records if r.type != r.prev.type and r.revision != 1]
        for r in type_changed:
            self.db.update('thing', where='id=$r.id', vars=locals(),
                last_modified=timestamp, latest_revision=r.revision, type=r.type)

        # update the remaining records
        rest = [r.id for r in records if r.type == r.prev.type and r.revision > 1]
        if rest:
            self.db.query("UPDATE thing SET latest_revision=latest_revision+1, last_modified=$timestamp WHERE id in $rest", vars=locals())

    def get_thing_ids(self, keys):
        keys = list(set(keys))

        thing_ids = dict((key, self.thing_ids[key]) for key in keys if key in self.thing_ids)
        notfound = [key for key in keys if key not in thing_ids]

        if notfound:
            rows = self.db.query("SELECT id, key FROM thing WHERE key in $notfound", vars=locals())
            d = dict((r.key, r.id) for r in rows)
            thing_ids.update(d)
            self.thing_ids.update(d)

        return thing_ids
        
    def get_thing_id(self, key):
        return self.get_thing_ids([key])[key]

    def get_user_details(self, key):
        """Returns a storage object with user email and encrypted password."""
        thing_id = self.get_thing_id(key)
        d = self.db.query("SELECT * FROM account WHERE thing_id=$thing_id", vars=locals())
        return d and d[0] or None        

class IndexUtil:
    def __init__(self, db, schema=None, indexer=None, property_manager=None):
        self.db = db
        self.schema = schema or Schema()
        self._indexer = indexer or Indexer()
        self.property_manager = property_manager or PropertyManager(db)
        self.thing_ids = {}
    
    def compute_index(self, doc):
        """Computes the index for given doc.
        Index is a list of (type, key, datatype, name, value).
        """
        type = doc['type']['key']
        key = doc['key']
        
        special = ["id", "type", "revision", "latest_revision", "created", "last_modified"]
        index = [(type, key, datatype, name, value) for datatype, name, value in self._indexer.compute_index(doc) if name not in special]
        
        # boolen values are not supported. 
        # avoid empty strings and Nones
        return [x for x in index if not isinstance(x[-1], bool) and x[-1] != "" and x[-1] is not None]
        
    def diff_index(self, old_doc, new_doc):
        """Takes old and new docs and returns the indexes to be deleted and inserted."""
        def get_type(doc):
            return doc and doc.get('type', {}).get('key', None)

        new_index = set(self.compute_index(new_doc))
        
        # nothing to delete when there is no old doc
        if not old_doc:
            return [], new_index
            
        if get_type(old_doc) != get_type(new_doc):
            key = new_doc['key']
            old_index = [(type, key, datatype, None, None) for datatype in INDEXED_DATATYPES]
            return old_index, new_index
        else:
            old_index = set(self.compute_index(old_doc))
            return old_index.difference(new_index), new_index.difference(old_index)
    
    def diff_records(self, records):
        """Takes a list of records and returns the index to be deleted and index to be inserted.
        """
        deletes = []
        inserts = []
        
        for r in records:
            old_doc, new_doc = r.prev.data, r.data
            _deletes, _inserts = self.diff_index(old_doc, new_doc)
            deletes.extend(_deletes)
            inserts.extend(_inserts)
        return deletes, inserts
            
    def update_index(self, records):
        """Takes a list of records, computes the index to be deleted/inserted
        and updates the index tables in the database.
        """
        deletes, inserts = self.diff_records(records)        
        deletes = self.compile_index(deletes)
        inserts = self.compile_index(inserts)
        
        self.delete_index(deletes)
        self.insert_index(inserts)
        
    def compile_index(self, index):
        """Takes (type, key, datatype, name, value) tuples and returns (table, thing_id, property_id, value) tuples.
        """
        keys = set(key for type, key, datatype, name, value in index)
        keys.update(value for type, key, datatype, name, value in index if datatype=='ref')
        thing_ids = self.get_thing_ids(keys)
        
        def get_value(value, datatype):
            if datatype == 'ref':
                return value and thing_ids[value]
            else:
                return value
        
        def get_pid(type, name):
            return name and self.get_property_id(type, name)
        
        return [(self.find_table(type, datatype, name), thing_ids[key], get_pid(type, name), get_value(value, datatype))
            for type, key, datatype, name, value in index]
            
    def group_index(self, index):
        """Groups the index based on table.
        """
        groups = defaultdict(list)
        for table, thing_id, property_id, value in index:
            groups[table].append((thing_id, property_id, value))
        return groups
            
    def insert_index(self, index):
        """Inserts the given index into database."""
        for table, data in self.group_index(index).items():
            data = [dict(thing_id=thing_id, key_id=property_id, value=value) for thing_id, property_id, value in data]
            self.db.multiple_insert(table, data)
            
    def delete_index(self, index):
        """Deletes the given index from database."""
        for table, data in self.group_index(index).items():
            for thing_id, property_id, value in data:
                if property_id:
                    self.db.delete(table, where='thing_id=$thing_id AND key_id=$property_id AND value=$value', vars=locals())
                else:
                    self.db.delete(table, where='thing_id=$thing_id', vars=locals())
            
    def get_thing_ids(self, keys):
        ### TODO: same function is there is SaveImpl too. Get rid of this duplication.
        keys = list(set(keys))

        thing_ids = dict((key, self.thing_ids[key]) for key in keys if key in self.thing_ids)
        notfound = [key for key in keys if key not in thing_ids]

        if notfound:
            rows = self.db.query("SELECT id, key FROM thing WHERE key in $notfound", vars=locals())
            d = dict((r.key, r.id) for r in rows)
            thing_ids.update(d)
            self.thing_ids.update(d)

        return thing_ids
        
    def get_property_id(self, type, name):
        return self.property_manager.get_property_id(type, name, create=True)
        
    def find_table(self, type, datatype, name):
        return self.schema.find_table(type, datatype, name)
    
class PropertyManager:
    """Class to manage property ids.
    """
    def __init__(self, db):
        self.db = db
        self._cache = None
        self.thing_ids = {}
        
    def reset(self):
        self._cache = None
        self.thing_ids = {}
        
    def get_cache(self):
        if self._cache is None:
            self._cache = {}
            
            rows = self.db.select('property').list()
            type_ids = list(set(r.type for r in rows)) or [-1]
            types = dict((r.id, r.key) for r in self.db.select("thing", where='id IN $type_ids', vars=locals()))
            for r in rows:
                self._cache[types[r.type], r.name] = r.id
                
        return self._cache
        
    def get_property_id(self, type, name, create=False):
        """Returns the id of (type, name) property. 
        When create=True, a new property is created if not already exists.
        """
        try:
            return self.get_cache()[type, name]
        except KeyError:
            type_id = self.get_thing_id(type)
            d = self.db.query("SELECT * FROM property WHERE type=$type_id AND name=$name", vars=locals())

            if d:
                pid = d[0].id
            elif create:
                pid = self.db.insert('property', type=type_id, name=name)
            else:
                return None
                
            self.get_cache()[type, name] = pid
            return pid
    
    def get_thing_id(self, key):
        try:
            id = self.thing_ids[key]
        except KeyError:
            id = self.db.query("SELECT id FROM thing WHERE key=$key", vars=locals())[0].id
            self.thing_ids[key] = id
        return id
        
    def copy(self):
        """Returns a copy of this PropertyManager.
        Used in write transactions to avoid corrupting the global state in case of rollbacks.
        """
        p = PropertyManager(self.db)
        if self._cache is not None:
            p._cache = self._cache.copy()
        p.thing_ids = self.thing_ids.copy()
        return p