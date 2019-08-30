"""Implementation of save for dbstore.
"""
import web
import simplejson
from collections import defaultdict

from indexer import Indexer
from schema import INDEXED_DATATYPES, Schema
from six import string_types

from infogami.infobase import config, common

__all__ = ["SaveImpl"]

class SaveImpl:
    """Save implementaion."""
    def __init__(self, db, schema=None, indexer=None, property_manager=None):
        self.db = db
        self.indexUtil = IndexUtil(db, schema, indexer, property_manager and property_manager.copy())
        self.thing_ids = {}

    def process_json(self, key, json):
        """Hack to allow processing of json before using. Required for OL legacy."""
        return json

    def save(self, docs, timestamp, comment, ip, author, action, data=None):
        docs = list(docs)
        docs = common.format_data(docs)

        if not docs:
            return {}

        dbtx = self.db.transaction()
        try:
            records = self._get_records_for_save(docs, timestamp)
            self._update_thing_table(records)

            changes = [dict(key=r.key, revision=r.revision) for r in records]
            bot = bool(author and (self.get_user_details(author) or {}).get('bot', False))

            # add transaction
            changeset = dict(
                kind=action,
                author=author and {"key": author},
                ip=ip,
                comment=comment,
                timestamp=timestamp.isoformat(),
                bot=bot,
                changes=changes,
                data=data or {},
            )
            tx_id = self._add_transaction(changeset)
            changeset['id'] = str(tx_id)

            # add versions
            versions = [dict(thing_id=r.id, revision=r.revision, transaction_id=tx_id) for r in records]
            self.db.multiple_insert('version', versions, seqname=False)

            # add data
            data = [dict(thing_id=r.id, revision=r.revision, data=simplejson.dumps(r.data)) for r in records]
            self.db.multiple_insert('data', data, seqname=False)

            self._update_index(records)
        except:
            dbtx.rollback()
            raise
        else:
            dbtx.commit()
        changeset['docs'] = [r.data for r in records]
        changeset['old_docs'] = [r.prev.data for r in records]
        return changeset

    def _add_transaction(self, changeset):
        tx = {
            "action": changeset['kind'],
            "author_id": changeset['author'] and self.get_thing_id(changeset['author']['key']),
            "ip": changeset['ip'],
            "comment": changeset['comment'],
            "created": changeset['timestamp'],
            "changes": simplejson.dumps(changeset['changes']),
            "data": simplejson.dumps(changeset['data']),
        }
        if config.use_bot_column:
            tx['bot'] = changeset['bot']

        tx_id = self.db.insert("transaction", **tx)
        self._index_transaction_data(tx_id, changeset['data'])
        return tx_id

    def _index_transaction_data(self, tx_id, data):
        d = []
        def index(key, value):
            if isinstance(value, (string_types, int)):
                d.append({"tx_id": tx_id, "key": key, "value": value})
            elif isinstance(value, list):
                for v in value:
                    index(key, v)

        for k, v in data.iteritems():
            index(k, v)

        if d:
            self.db.multiple_insert("transaction_index", d, seqname=False)

    def reindex(self, keys):
        records = self._load_records(keys).values()

        for r in records:
            # Force reindex
            old_doc = {"key": r.key, "type": r.data['type'], "_force_reindex": True}
            r.prev = web.storage(r, data=old_doc)

        tx = self.db.transaction()
        try:
            self.indexUtil.update_index(records)
        except:
            tx.rollback()
            raise
        else:
            tx.commit()

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
        type_ids = self.get_thing_ids(doc['type']['key'] for doc in docs)

        records = self._load_records(keys)

        def make_record(doc):
            doc = dict(doc) # make a copy to avoid modifying the original.

            key = doc['key']
            r = records.get(key) or web.storage(id=None, key=key, revision=0, type=None, data=None, created=timestamp)

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

    def _load_records(self, keys):
        """Returns a dictionary of records for the given keys.

        The records are queried FOR UPDATE to lock those rows from concurrent updates.
        Each record is a storage object with (id, key, type, revision, last_modified, data) keys.
        """
        try:
            rows = self.db.query("SELECT thing.*, data.data FROM thing, data" +
                " WHERE thing.key in $keys" +
                " AND data.thing_id=thing.id AND data.revision = thing.latest_revision" +
                " FOR UPDATE NOWAIT",
                vars=locals())
        except:
            raise common.Conflict(keys=keys, reason="Edit conflict detected.")

        records = dict((r.key, r) for r in rows)
        for r in records.values():
            r.revision = r.latest_revision
            json = r.data and self.process_json(r.key, r.data)
            r.data = simplejson.loads(json)
        return records

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
                    self.db.update("thing", type=d[r['key']]['type'], where="key=$key", vars={"key": r['key']})

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
        account_key = "account/" + key.split("/")[-1]
        rows = self.db.query("SELECT * FROM store WHERE key=$account_key", vars=locals())
        if rows:
            return simplejson.loads(rows[0].json)
        else:
            return None

class IndexUtil:
    """

    There are 3 types of indexes that are used here.

    1. triples

    Triples are indexeble (property, datatype, value) triples for a given document.

    2. document index

    Dictionary of (type, key, property, datatype) -> [values] for a set of documents.
    This is generated by processing the triples.

    3. db index

    Dictionary of (table, thing_id, property_id) -> [values] for a set of documents.
    This is generated by compling the document index.
    """
    def __init__(self, db, schema=None, indexer=None, property_manager=None):
        self.db = db
        self.schema = schema or Schema()
        self._indexer = indexer or Indexer()
        self.property_manager = property_manager or PropertyManager(db)
        self.thing_ids = {}

    def compute_index(self, doc):
        """Computes the doc-index for given doc.
        """
        type = doc['type']['key']
        key = doc['key']

        special = ["id", "type", "revision", "latest_revision", "created", "last_modified"]

        def ignorable(name, value):
            # ignore special properties
            # boolen values are not supported.
            # ignore empty strings and Nones
            return name in special or isinstance(value, bool) or value is None or value == ""

        index = defaultdict(list)
        for datatype, name, value in self._indexer.compute_index(doc):
            if not ignorable(name, value):
                index[type, key, datatype, name].append(value)
        return index

    def diff_index(self, old_doc, new_doc):
        """Takes old and new docs and returns the indexes to be deleted and inserted."""
        def get_type(doc):
            return doc and doc.get('type', {}).get('key', None)

        new_index = self.compute_index(new_doc)

        # nothing to delete when there is no old doc
        if not old_doc:
            return {}, new_index

        if get_type(old_doc) != get_type(new_doc) or old_doc.get("_force_reindex"):
            key = new_doc['key']

            old_index = {}
            old_type = get_type(old_doc)
            for datatype in INDEXED_DATATYPES:
                # name is None means all the names need be deleted.
                old_index[old_type, key, datatype, None] = []

            return old_index, new_index
        else:
            old_index = self.compute_index(old_doc)

            # comparision between the lists must be done without considering the order.
            # Converting the value to set before comparision is the simplest option.
            xset = lambda a: a and set(a)
            xeq = lambda a, b: xset(a) == xset(b)

            deletes = self._dict_difference(old_index, new_index, xeq)
            inserts = self._dict_difference(new_index, old_index, xeq)
            return deletes, inserts

    def _dict_difference(self, d1, d2, eq=None):
        """Returns set equivalant of d1.difference(d2) for dictionaries.
        """
        eq = eq or (lambda a, b: a == b)
        return dict((k, v) for k, v in d1.iteritems() if not eq(v, d2.get(k)))

    def diff_records(self, records):
        """Takes a list of records and returns the index to be deleted and index to be inserted.
        """
        deletes = {}
        inserts = {}

        for r in records:
            old_doc, new_doc = r.prev.data, r.data
            _deletes, _inserts = self.diff_index(old_doc, new_doc)
            deletes.update(_deletes)
            inserts.update(_inserts)
        return deletes, inserts

    def update_index(self, records):
        """Takes a list of records, computes the index to be deleted/inserted
        and updates the index tables in the database.
        """
        # update thing_ids to save some queries
        for r in records:
            self.thing_ids[r.key] = r.id

        deletes, inserts = self.diff_records(records)
        deletes = self.compile_index(deletes)
        inserts = self.compile_index(inserts)

        self.delete_index(deletes)
        self.insert_index(inserts)

    def compile_index(self, index):
        """Compiles doc-index into db-index.
        """
        keys = set(key for type, key, datatype, name in index)
        for (type, key, datatype, name), values in index.iteritems():
            if datatype == 'ref':
                keys.update(values)

        thing_ids = self.get_thing_ids(keys)

        def get_value(value, datatype):
            if datatype == 'ref':
                return value and thing_ids[value]
            else:
                return value

        def get_values(values, datatype):
            return [get_value(v, datatype) for v in values]

        def get_pid(type, name):
            return name and self.get_property_id(type, name)

        dbindex = {}

        for (type, key, datatype, name), values in index.iteritems():
            table = self.find_table(type, datatype, name)
            thing_id = thing_ids[key]
            pid = get_pid(type, name)

            dbindex[table, thing_id, pid] = get_values(values, datatype)

        return dbindex

    def group_index(self, index):
        """Groups the index based on table.
        """
        groups = defaultdict(dict)
        for (table, thing_id, property_id), values in index.iteritems():
            groups[table][thing_id, property_id] = values
        return groups

    def ignore_long_values(self, index):
        """The DB schema has a limit of 2048 chars on string values. This function ignores values which are longer than that.
        """
        is_too_long = self._is_too_long
        return dict((k, [v for v in values if not is_too_long(v)]) for k, values in index.iteritems())

    def _is_too_long(self, v, limit=2048):
        return (
            isinstance(v, string_types)
            # unicode string can be as long as 4 bytes in utf-8.
            # This check avoid UTF-8 conversion for small strings.
            and len(v) > limit/4
            and len(web.safestr(v)) > limit
        )

    def insert_index(self, index):
        """Inserts the given index into database."""
        for table, group in self.group_index(index).iteritems():
            # ignore values longer than 2048, the limit specified by the db schema.
            group = self.ignore_long_values(group)
            data = [dict(thing_id=thing_id, key_id=property_id, value=v)
                for (thing_id, property_id), values in group.iteritems()
                for v in values]
            self.db.multiple_insert(table, data, seqname=False)

    def delete_index(self, index):
        """Deletes the given index from database."""
        for table, group in self.group_index(index).iteritems():

            thing_ids = [] # thing_ids to delete all

            # group all deletes for a thing_id
            d = defaultdict(list)
            for thing_id, property_id in group:
                if property_id:
                    d[thing_id].append(property_id)
                else:
                    thing_ids.append(thing_id)

            if thing_ids:
                self.db.delete(table, where='thing_id IN $thing_ids', vars=locals())

            for thing_id, pids in d.iteritems():
                self.db.delete(table, where="thing_id=$thing_id AND key_id IN $pids", vars=locals())

    def get_thing_ids(self, keys):
        ### TODO: same function is there is SaveImpl too. Get rid of this duplication.
        keys = list(set(keys))
        if not keys:
            return {}

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
        p._cache = self.get_cache().copy()
        p.thing_ids = self.thing_ids.copy()
        return p
