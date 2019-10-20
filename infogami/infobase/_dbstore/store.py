"""JSON store for storing any unstructured data different from documents stored in the versioned database.

This provides a simple and limited interface for storing, retriving, querying documents.

    - get(key) -> data
    - put(key, data)
    - delete(key)

    - get_json(key) -> json
    - set_json(key, json)

    - list(limit=100, offset=0) -> keys
    - query(type, name, value, limit=100, offset=0) -> keys

Each doument can have an optional type property that can be used while querying.
The query interface is limited to only one name, value. No joins are possible and
the result is always ordered by the internal id.

To overcome the limitation of joins, the store provides a pluggable indexer interface.
The indexer decides the list of (name, value) pairs to index.

The following indexer allows querying for books using lowercase titles and books written by the given author in the given language.

    class BookIndexer:
        def index(self, doc):
            yield "title.lower", doc.title.lower()

            for a in doc.authors:
                yield "author,lang", simplejson.dumps([a, doc.lang])

"""

import simplejson
import web

from infogami.infobase import common

class Store:
    """JSON Store.
    """
    def __init__(self, db):
        self.db = db
        self.indexer = StoreIndexer()
        self.listener = None

    def get_row(self, key, for_update=False):
        q = "SELECT * FROM store WHERE key=$key"
        if for_update:
            q += " FOR UPDATE NOWAIT"
        rows = self.db.query(q, vars=locals())
        if rows:
            return rows[0]

    def set_listener(self, f):
        self.listener = f

    def fire_event(self, name, data):
        self.listener and self.listener(name, data)

    def get_json(self, key):
        d = self.get(key)
        return d and simplejson.dumps(d)

    def get(self, key):
        row = self.get_row(key)
        return row and self._get_doc(row)

    def _get_doc(self, row):
        doc = simplejson.loads(row.json)
        doc['_key'] = row.key
        doc['_rev'] = str(row.id)
        return doc

    def put(self, key, doc):
        if doc.get("_delete") == True:
            return self.delete(key, doc.get("_rev"))

        # conflict check is enabled by default. It can be disabled by passing _rev=None in the document.
        if "_rev" in doc and doc["_rev"] is None:
            enable_conflict_check = False
        else:
            enable_conflict_check = True

        doc.pop("_key", None)
        rev = doc.pop("_rev", None)

        json = simplejson.dumps(doc)

        tx = self.db.transaction()
        try:
            row = self.get_row(key, for_update=True)
            if row:
                if enable_conflict_check and str(row.id) != str(rev):
                    raise common.Conflict(key=key, message="Document update conflict")

                self.delete_index(row.id)

                # store query results are always order by id column.
                # It is important to update the id so that the newly modified
                # records show up first in the results.
                self.db.query("UPDATE store SET json=$json, id=nextval('store_id_seq') WHERE key=$key", vars=locals())

                id = self.get_row(key=key).id
            else:
                id = self.db.insert("store", key=key, json=json)

            self.add_index(id, key, doc)

            doc['_key'] = key
            doc['_rev'] = str(id)
        except:
            tx.rollback()
            raise
        else:
            tx.commit()
            self.fire_event("store.put", {"key": key, "data": doc})

        return doc

    def put_many(self, docs):
        """Stores multiple docs in a single transaction.
        """
        with self.db.transaction():
            for doc in docs:
                key = doc['_key']
                self.put(key, doc)

    def put_json(self, key, json):
        self.put(key, simplejson.loads(json))

    def delete(self, key, rev=None):
        tx = self.db.transaction()
        try:
            row = self.get_row(key, for_update=True)
            if row:
                if rev is not None and str(row.id) != str(rev):
                    raise common.Conflict(key=key, message="Document update conflict")
                self.delete_row(row.id)
        except:
            tx.rollback()
            raise
        else:
            tx.commit()
            self.fire_event("store.delete", {"key": key})

    def delete_row(self, id):
        """Deletes a row. This must be called in a transaction."""
        self.db.delete("store_index", where="store_id=$id", vars=locals())
        self.db.delete("store", where="id=$id", vars=locals())

    def query(self, type, name, value, limit=100, offset=0, include_docs=False):
        """Query the json store.

        Returns keys of all documents of the given type which have (name, value) in the index.
        All the documents of the given type are returned when the name is None.
        All the documents are returned when the type is None.
        """
        if type is None:
            rows = self.db.select("store", what="store.*", limit=limit, offset=offset, order="store.id desc", vars=locals())
        else:
            tables = ["store", "store_index"]
            wheres = ["store.id = store_index.store_id", "type = $type"]

            if name is None:
                wheres.append("name='_key'")
            else:
                wheres.append("name=$name AND value=$value")
            rows = self.db.select(tables, what='store.*', where=" AND ".join(wheres), limit=limit, offset=offset, order="store.id desc", vars=locals())

        def process_row(row):
            if include_docs:
                return {"key": row.key, "doc": self._get_doc(row)}
            else:
                return {"key": row.key}

        return [process_row(row) for row in rows]

    def delete_index(self, id):
        self.db.delete("store_index", where="store_id=$id", vars=locals())

    def add_index(self, id, key, data):
        if isinstance(data, dict):
            type = data.get("type", "")
        else:
            type = ""
        d = [web.storage(store_id=id, type=type, name="_key", value=key)]
        ignored = ["type"]
        for name, value in set(self.indexer.index(data)):
            if not name.startswith("_") and name not in ignored:
                if isinstance(value, bool):
                    value = str(value).lower()
                d.append(web.storage(store_id=id, type=type, name=name, value=value))
        if d:
            self.db.multiple_insert('store_index', d)

class StoreIndexer:
    """Default indexer for store.

    Indexes all properties of the given document.
    """
    def index(self, doc):
        return common.flatten_dict(doc)

class TypewiseIndexer:
    """An indexer that delegates the indexing to sub-indexers based on the docuemnt type.
    """
    def __init__(self):
        self.indexers = {}
        self.default_indexer = StoreIndexer()

    def set_indexer(self, type, indexer):
        """Installs indexer for the given type of documents.
        """
        self.indexers[type] = indexer

    def get_indexer(self, type):
        """Returns the indexer for the given type. The default indexer is returned when none available."""
        return self.indexers.get(type, self.default_indexer)

    def index(self, doc):
        """Delegates the call to the indexer installed for the doc type."""
        type = doc.get("type", "")
        return self.get_indexer(type).index(doc)
