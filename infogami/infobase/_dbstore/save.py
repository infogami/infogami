"""Implementation of save for dbstore.
"""
import web
import simplejson

__all__ = ["SaveImpl"]

class SaveImpl:
    """Save implementaion."""
    def __init__(self, db):
        self.db = db
        self.thing_ids = {}
    
    def save(self, docs, timestamp, comment, ip, author, action, machine_comment=None):
        tx = self.db.transaction()
        try:
            records = self._get_records_for_save(docs, timestamp)
            self._update_thing_table(records)
            
            # add transaction
            tx_id = self.db.insert("transaction", 
                action=action,
                author_id=author and author.id,
                ip=ip,
                comment=comment, 
                created=timestamp)
                
            # add versions
            versions = [dict(thing_id=r.id, revision=r.revision, transaction_id=tx_id) for r in records]
            self.db.multiple_insert('version', versions, seqname=False)

            # add data
            data = [dict(thing_id=r.id, revision=r.revision, data=simplejson.dumps(r.data)) for r in records]
            self.db.multiple_insert('data', data, seqname=False)
            
            # TODO: update index
        except:
            tx.rollback()
            raise
        else:
            tx.commit()
        return [{"key": r.key, "revision": r.revision} for r in records]
        
    def reindex(self, keys):
        pass
        
    def _get_records_for_save(self, docs, timestamp):
        keys = [doc['key'] for doc in docs]
        rows = self.db.query("SELECT thing.*, data.data FROM thing, data" + 
            " WHERE thing.key in $keys" + 
            " AND data.thing_id=thing.id AND data.revision = thing.latest_revision" + 
            " FOR UPDATE NOWAIT",
            vars=locals())
        d = dict((r.key, r) for r in rows)
        
        type_ids = self.get_thing_ids(doc['type']['key'] for doc in docs)
            
        def make_record(doc):
            doc = dict(doc) # make a copy to avoid modifying the original.
            
            key = doc['key']
            r = d.get(key) or web.storage(id=None, key=key, latest_revision=0, type=None, data=None, created=timestamp)
            
            r.revision = r.pop('latest_revision')
            
            r.prev = web.storage(r)

            r.type = type_ids[doc['type']['key']]
            r.revision = r.prev.revision + 1
            r.data = doc
            r.last_modified = timestamp
            
            doc['latest_revision'] = r.revision
            doc['revision'] = r.revision
            doc['created'] = {"type": "/type/datetime", "value": r.created.isoformat()}
            doc['last_modified'] = {"type": "/type/datetime", "value": r.last_modified.isoformat()}
            return r
        
        return [make_record(doc) for doc in docs]
        
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
                
        # update records with type change
        type_changed = [r for r in records if r.type != r.prev.type]
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