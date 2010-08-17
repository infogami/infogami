"""Implementation of all read queries."""

from collections import defaultdict
import simplejson

class RecentChanges:
    def __init__(self, db):
        self.db = db
        
    def get_keys(self, ids):
        ids = list(set(id for id in ids if id is not None))
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
            
    def get_change(self, id):
        try:
            change = self.db.select("transaction", where="id=$id", vars=locals())[0]
        except IndexError:
            return None
        
        authors = self.get_keys([change.author_id])
        return self._process_transaction(change, authors=authors)
    
    def recentchanges(self, limit=100, offset=0, **kwargs):
        order = 'created DESC'
        wheres = ["1 = 1"]
                
        bot = kwargs.pop('bot', None)
        if bot is not None:
            bot_ids = [r.thing_id for r in self.db.query("SELECT thing_id FROM account WHERE bot='t'")] or [-1]
            if bot is True or str(bot).lower() == "true":
                wheres.append("author_id IN $bot_ids")
            else:
                wheres.append("(author_id NOT in $bot_ids OR author_id IS NULL)")

        author = kwargs.pop('author', None)
        if author is not None:
            author_id = self.get_thing_id(author)
            if not author_id:
                # Unknown author. Implies no changes by him.
                return {}
            else:
                wheres.append("author_id=$author_id")
                
        ip = kwargs.pop("ip", None)
        if ip is not None:
            if not self._is_valid_ipv4(ip):
                return {}
            else:
                # Don't include edits by logged in users when queried by ip. 
                wheres.append("ip = $ip AND author_id is NULL")
            
        kind = kwargs.pop('kind', None)
        if kind is not None:
            wheres.append('action = $kind')
            
        begin_date = kwargs.pop('begin_date', None)
        if begin_date is not None:
            wheres.append("created >= $begin_date")
        
        end_date = kwargs.pop('end_date', None)
        if end_date is not None:
            # end_date is not included in the interval.
            wheres.append("created < $end_date")
        
        where=" AND ".join(wheres)
        rows = self.db.select("transaction", where=where, limit=limit, offset=offset, order=order, vars=locals()).list()

        authors = self.get_keys(row.author_id for row in rows)        
        
        return [self._process_transaction(row, authors) for row in rows]
        
    def _process_transaction(self, tx, authors):
        d = {
            "id": str(tx.id),
            "kind": tx.action or "edit",
            "timestamp": tx.created.isoformat(),
            "comment": tx.comment,
        }
        
        d['changes'] = tx.changes and simplejson.loads(tx.changes)

        if tx.author_id:
            d['author'] = {"key": authors[tx.author_id]}
            d['ip'] = None
        else:
            d['author'] = None
            d['ip'] = tx.ip

        # The new db schema has a data column in transaction table. 
        # In old installations, machine_comment column is used as data
        if tx.get('data'):
            d['data'] = simplejson.loads(tx.data)
        elif tx.get('machine_comment') and tx.machine_comment.startswith("{"):
            d['data'] = simplejson.loads(tx.machine_comment)
        else:
            d['data'] = {}
            
        return d
        
    def _is_valid_ipv4(self, ip):
        tokens = ip.split(".")
        try:
            return len(tokens) == 4 and all(0 <= int(t) < 256 for t in tokens)
        except ValueError:
            return False
