"""Implementation of all read queries."""

from collections import defaultdict

class RecentChanges:
    def __init__(self, db):
        self.db = db
        
    def get_keys(self, ids):
        if ids:
            rows = self.db.query("SELECT id, key FROM thing WHERE id in $ids", vars=locals())
            return dict((row.id, row.key) for row in rows)
        else:
            return {}
            
    def get_thing_id(self, key):
        try:
            return self.db.where("thing", key=key)[0].id
        except IndexError:
            return None
    
    def recentchanges(self, author=None, limit=100, offset=0):
        order = 'transaction.created DESC'
        wheres = ["1 = 1"]
        
        if author:
            author_id = self.get_thing_id(author)
            if not author_id:
                return {}
            else:
                wheres.append("author_id=$author_id")
        
        where=" AND ".join(wheres)
        rows = self.db.select("transaction", where=where, limit=limit, offset=offset, order=order, vars=locals()).list()

        author_ids = set(row.author_id for row in rows if row.author_id)
        authors = self.get_keys(list(author_ids))
        
        versions = self.get_versions([row.id for row in rows])
        return [self._process_transaction(row, authors, versions) for row in rows]
        
    def get_versions(self, tx_ids):
        """Returns key,revision for each modified document in each transaction.
        """
        rows = self.db.query(
            "SELECT transaction.id, thing.key, version.revision" + 
            " FROM thing, version, transaction" + 
            " WHERE thing.id = version.thing_id" + 
            " AND version.transaction_id IN $tx_ids",
            vars=locals())

        d = defaultdict(list)
        for row in rows:
            d[row.id].append({"key": row.key, "revision": row.revision})
        return d
        
    def _process_transaction(self, tx, authors, versions):
        d = {
            "id": tx.id,
            "kind": tx.action,
            "timestamp": tx.created.isoformat(),
            "comment": tx.comment,
            "changes": versions[tx.id]
        }
        
        if tx.author_id:
            d['author'] = {"key": authors[tx.author_id]}
            d['ip'] = None
        else:
            d['author'] = None
            d['ip'] = tx.ip

        # The new db schema has a data column in transaction table. 
        # In old installations, machine_comment column is used as data
        if "data" in tx:
            d['data'] = simplejson.loads(tx.data)
        elif "machine_comment" in tx and tx.machine_comment and tx.machine_comment.startswith("{"):
            d['data'] = simplejson.loads(tx.machine_comment)
        else:
            d['data'] = {}
            
        return d