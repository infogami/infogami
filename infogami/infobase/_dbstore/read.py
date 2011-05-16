"""Implementation of all read queries."""

from collections import defaultdict
import simplejson
import web
from infogami.infobase import config

def get_user_root():
    user_root = config.get("user_root", "/user")
    return user_root.rstrip("/") + "/"

def get_bot_users(db):
    """Returns thing_id of all bot users.
    """
    rows = db.query("SELECT store.key FROM store, store_index WHERE store.id=store_index.store_id AND type='account' AND name='bot' and value='true'")
    bots = [get_user_root() + row.key.split("/")[-1] for row in rows]
    if bots:
        bot_ids = [row.id for row in db.query("SELECT id FROM thing WHERE key in $bots", vars=locals())]
        return bot_ids or [-1]
    else:
        return [-1]

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
        tables = ['transaction t']
        what = 't.*'
        order = 't.created DESC'
        wheres = ["1 = 1"]
        
        if offset < 0:
            offset = 0
        
        key = kwargs.pop('key', None)
        if key is not None:
            thing_id = self.get_thing_id(key)
            if thing_id is None:
                return []
            else:
                tables.append('version v')
                wheres.append('v.transaction_id = t.id AND v.thing_id = $thing_id')
        
        bot = kwargs.pop('bot', None)
        if bot is not None:
            bot_ids = get_bot_users(self.db)
            if bot is True or str(bot).lower() == "true":
                wheres.append("t.author_id IN $bot_ids")
            else:
                wheres.append("(t.author_id NOT in $bot_ids OR t.author_id IS NULL)")

        author = kwargs.pop('author', None)
        if author is not None:
            author_id = self.get_thing_id(author)
            if not author_id:
                # Unknown author. Implies no changes by him.
                return []
            else:
                wheres.append("t.author_id=$author_id")
                
        ip = kwargs.pop("ip", None)
        if ip is not None:
            if not self._is_valid_ipv4(ip):
                return []
            else:
                # Don't include edits by logged in users when queried by ip. 
                wheres.append("t.ip = $ip AND t.author_id is NULL")
            
        kind = kwargs.pop('kind', None)
        if kind is not None:
            wheres.append('t.action = $kind')
            
        begin_date = kwargs.pop('begin_date', None)
        if begin_date is not None:
            wheres.append("t.created >= $begin_date")
        
        end_date = kwargs.pop('end_date', None)
        if end_date is not None:
            # end_date is not included in the interval.
            wheres.append("t.created < $end_date")
            
        data = kwargs.pop('data', None)
        if data:
            for i, (k, v) in enumerate(data.items()):
                t = 'ti%d' % i
                tables.append('transaction_index ' + t)
                q = '%s.tx_id = t.id AND %s.key=$k AND %s.value=$v' % (t, t, t)
                # k, v are going to change in the next iter of the loop.
                # bind the current values by calling reparam.
                wheres.append(web.reparam(q, locals())) 
        
        
        wheres = list(self._process_wheres(wheres, locals()))
        where = web.SQLQuery.join(wheres, " AND ")
        
        rows = self.db.select(tables, what=what, where=where, limit=limit, offset=offset, order=order, vars=locals()).list()

        authors = self.get_keys(row.author_id for row in rows)        
        
        return [self._process_transaction(row, authors) for row in rows]
        
    def _process_wheres(self, wheres, vars):
        for w in wheres:
            if isinstance(w, basestring):
                yield web.reparam(w, vars)
            else:
                yield w
        
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
