"""Infobase Implementation based on database.
"""
import common
import config
import web
import _json as simplejson
import datetime, time
from collections import defaultdict

from _dbstore import store, sequence
from _dbstore.schema import Schema, INDEXED_DATATYPES
from _dbstore.indexer import Indexer
from _dbstore.save import SaveImpl

default_schema = None

def process_json(key, json):
    """Hook to process json.
    """
    return json

class DBSiteStore(common.SiteStore):
    """
    """
    def __init__(self, db, schema):
        self.db = db
        self.schema = schema
        self.sitename = None
        self.indexer = Indexer()
        self.store = store.Store(self.db)
        self.seq = sequence.SequenceImpl(self.db)
        
        self.cache = None
        self.property_id_cache = None
                
    def get_store(self):
        return self.store
        
    def set_cache(self, cache):
        self.cache = cache

    def get_metadata(self, key, for_update=False):
        # postgres doesn't seem to like Reference objects even though Referece extends from unicode.
        if isinstance(key, common.Reference):
            key = unicode(key)

        if for_update:
            d = self.db.query('SELECT * FROM thing WHERE key=$key FOR UPDATE NOWAIT', vars=locals())
        else:
            d = self.db.query('SELECT * FROM thing WHERE key=$key', vars=locals())
        return d and d[0] or None
        
    def get_metadata_list(self, keys):
        result = self.db.select('thing', what='*', where=web.sqlors('key=', keys)).list()
        d = dict((r.key, r) for r in result)
        return d
        
    def new_thing(self, **kw):
        return self.db.insert('thing', **kw)
        
    def get_metadata_from_id(self, id):
        d = self.db.query('SELECT * FROM thing WHERE id=$id', vars=locals())
        return d and d[0] or None

    def get_metadata_list_from_ids(self, ids):
        d = {}
        result = self.db.select('thing', what='*', where=web.sqlors('id=', ids)).list()
        d = dict((r.id, r) for r in result)
        return d
        
    def new_key(self, type, kw):
        seq = self.schema.get_seq(type)
        if seq:
            # repeat until a non-existing key is found.
            # This is required to prevent error in cases where an object with the next key is already created.
            while True:
                value = self.db.query("SELECT NEXTVAL($seq.name) as value", vars=locals())[0].value
                key = seq.pattern % value
                if self.get_metadata(key) is None:
                    return key
        else:
            return common.SiteStore.new_key(self, type, kw)
    
    def get(self, key, revision=None):
        if self.cache is None or revision is not None:
            json = self._get(key, revision)
        else:
            json = self.cache.get(key)
            if json is None:
                json = self._get(key, revision)
                if json:
                    self.cache[key] = json
        return process_json(key, json)
    
    def _get(self, key, revision):    
        metadata = self.get_metadata(key)
        if not metadata: 
            return None
        revision = revision or metadata.latest_revision
        d = self.db.query('SELECT data FROM data WHERE thing_id=$metadata.id AND revision=$revision', vars=locals())
        json = d and d[0].data or None
        return json
        
    def get_many(self, keys):
        if not keys:
            return '{}'

        xkeys = [web.reparam('$k', dict(k=k)) for k in keys]
        query = 'SELECT thing.key, data.data from thing, data ' \
            + 'WHERE data.revision = thing.latest_revision and data.thing_id=thing.id ' \
            + ' AND thing.key IN (' + self.sqljoin(xkeys, ', ') + ')'
            
        def process(query):
            yield '{\n'
            for i, r in enumerate(self.db.query(query)):
                if i:
                    yield ',\n'
                yield simplejson.dumps(r.key)
                yield ": "
                yield process_json(r.key, r.data)
            yield '}'
        return "".join(process(query))
        
    def _add_transaction(self, action, author, ip, comment, created):
        kw = dict(
            action=action,
            author_id=author and self.get_metadata(author).id,
            ip=ip,
            created=created,
            comment=comment,
        )
        if config.use_bot_column:
            kw['bot'] = bool(author and (self.get_user_details(author) or {}).get('bot', False))
            
        return self.db.insert('transaction', **kw)
        
    def _add_version(self, thing_id, revision, transaction_id, created):
        if revision is None:
            d = self.db.query(
                'UPDATE thing set latest_revision=latest_revision+1, last_modified=$created WHERE id=$thing_id;' + \
                'SELECT latest_revision FROM thing WHERE id=$thing_id', vars=locals())
            revision = d[0].latest_revision
            
        self.db.insert('version', False, 
            thing_id=thing_id, 
            revision=revision, 
            transaction_id=transaction_id
        )
        return revision
        
    def _update_tables(self, thing_id, key, olddata, newdata):
        def find_datatype(value):
            if isinstance(value, common.Text):
                return 'text'
            elif isinstance(value, common.Reference):
                return 'ref'
            elif isinstance(value, bool):
                return 'boolean'
            elif isinstance(value, float):
                return 'float'
            elif isinstance(value, int):
                return 'int'
            else:
                return 'str'
                
        def do_action(f, type_key, type_id, thing_id, name, value, ordering=None):
            if isinstance(value, list):
                for i, v in enumerate(value):
                    do_action(f, type_key, type_id, thing_id, name, v, i)
            elif isinstance(value, dict):
                for k, v in value.items():
                    if k != 'type':
                        do_action(f, type_key, type_id, thing_id, name + '.' + k, v, ordering)
            else:
                datatype = find_datatype(value)
                if datatype == 'ref':
                    value = self.get_metadata(value)
                    value = value and value.id
                elif datatype == 'str':
                    value = value[:2048] # truncate long strings
                elif isinstance(value, bool):
                    value = "ft"[int(value)] # convert boolean to 't' or 'f'
                table = self.schema.find_table(type_key, datatype, name)
                
                if table:
                    pid = self.get_property_id(type_id, name, create=True)
                    assert pid is not None
                    f(table, thing_id, pid, value, ordering)
        
        deletes = {}
        inserts = {}
        
        def action_delete(table, thing_id, key_id, value, ordering):
            deletes.setdefault((table, thing_id), []).append(key_id)
            #self.db.delete(table, where='thing_id=$thing_id AND key_id=$key_id', vars=locals())
        
        def action_insert(table, thing_id, key_id, value, ordering):
            #self.db.insert(table, seqname=False, thing_id=thing_id, key_id=key_id, value=value, ordering=ordering)
            d = dict(thing_id=thing_id, key_id=key_id, value=value, ordering=ordering)
            inserts.setdefault(table, []).append(d)
            
        def do_deletes_and_inserts():
            for (table, thing_id), key_ids in deletes.items():
                key_ids = list(set(key_ids)) # remove duplicates
                self.db.delete(table, where='thing_id=$thing_id AND key_id IN $key_ids', vars=locals())
                
            for table, values in inserts.items():
                self.db.multiple_insert(table, values,  seqname=False)
            
        olddata = olddata and common.parse_data(olddata)
        newdata = newdata and common.parse_data(newdata)

        old_type = (olddata and olddata['type']) or None
        new_type = newdata['type']
        
        old_type_id = old_type and self.get_metadata(old_type).id
        new_type_id = new_type and self.get_metadata(new_type).id
        
        def _coerce(d):
            if isinstance(d, dict) and 'key' in d:
                return d['key']
            else:
                return d
    
        old_type = _coerce(old_type)
        new_type = _coerce(new_type)
        
        for k in ['id', 'key', 'type', 'last_modified', 'created', 'revision', 'latest_revision']:
            olddata.pop(k, None)
            newdata.pop(k, None)
        
        removed, unchanged, added = common.dict_diff(olddata, newdata)
                        
        if old_type != new_type:
            removed = olddata.keys()
            added = newdata.keys()
        
        for k in removed:
            do_action(action_delete, old_type, old_type_id, thing_id, k, olddata[k])
        
        for k in added:
            do_action(action_insert, new_type, new_type_id, thing_id, k, newdata[k])
            
        do_deletes_and_inserts()
        
    def _delete_index(self, index):
        """Delete the specified index.
        Index must be a list of (type, key, datatype, name, value). 
        """
        index = self._process_index(index)
        for table, data in index.items():
            for thing_id, key_id, value in data:
                if key_id is None:
                    self.db.delete(table, 'thing_id=$thing_id', vars=locals())
                else:
                    self.db.delete(table, 'thing_id=$thing_id AND key_id=$key_id AND value=$value', vars=locals())
            
    def _insert_index(self, index):
        """Insert the specified index.
        index must be a list of (type, key, datatype, name, value). 
        """
        index = self._process_index(index)
        for table, d in index.items():
            self.db.multiple_insert(table, d, seqname=False)
    
    def _process_index(self, index):
        """Process the index and create the data suitable for inserting/deleting from the database.
        """
        @web.memoize
        def get_thing_id(key):
            return self.get_metadata(key).id
            
        data = defaultdict(list)
            
        for type, key, datatype, name, value in index:
            thing_id = get_thing_id(key)
            key_id = name and self.get_property_id(get_thing_id(type), name, create=True)
            if datatype == 'ref':
                value = value and get_thing_id(value)
    
            table = self.schema.find_table(type, datatype, name)                
            data[table].append(web.storage(thing_id=thing_id, key_id=key_id, value=value))
        return data
        
    def compute_index(self, doc):
        """Computes the index for given doc.
        Index is a list of (type, key, datatype, name, value).
        """
        type = doc['type']['key']
        key = doc['key']
        return [(type, key, datatype, name, value) for datatype, name, value in self.indexer.compute_index(doc)]
    
    def reindex(self, keys):
        """Remove all entries from index table and add again."""
        
        t = self.db.transaction()
        try:
            thing_ids = dict((key, self._key2id(key)) for key in keys)
            docs = dict((key, simplejson.loads(self.get(key))) for key in keys)
            
            deletes = {}
            for key in keys:
                type = docs[key]['type']['key']
                for table in self.schema.find_tables(type):
                    deletes.setdefault(table, []).append(thing_ids[key])
        
            for table, ids in deletes.items():
                self.db.delete(table, where="thing_id IN $ids", vars=locals())
        
            index = [d for doc in docs.values() for d in self.compute_index(doc)]
            self._insert_index(index)
        except:
            t.rollback()
            raise
        else:
            t.commit()
                    
    def save_many(self, items, timestamp, comment, machine_comment, ip, author, action=None):
        action = action or "bulk_update"
        s = SaveImpl(self.db, self.schema, self.indexer)
        return s.save(common.format_data(items), timestamp=timestamp, comment=comment, ip=ip, author=author, action=action, machine_comment=machine_comment)
        
    def _key2id(self, key):
        d = self.get_metadata(key)
        return d and d.id

    def save(self, key, data, timestamp=None, comment=None, machine_comment=None, ip=None, author=None, transaction_id=None):
        timestamp = timestamp or datetime.datetime.utcnow
        return self.save_many([data], timestamp, comment, machine_comment, ip, author, action="update")[0]
        
    def _save(self, key, data, timestamp=None, comment=None, machine_comment=None, ip=None, author=None, transaction_id=None):
        try:
            metadata = self.get_metadata(key, for_update=True)
        except:
            raise common.Conflict(key=key, reason="Edit conflict detected.")

        typekey = data['type']
        type_id = self._key2id(typekey)
        
        if metadata: # already existing object
            revision = None
            thing_id = metadata.id
            olddata = simplejson.loads(self.get(key))
            created = metadata.created
            action = "update"
        else:
            revision = 1
            thing_id = self.new_thing(key=key, type=type_id, latest_revision=1, last_modified=timestamp, created=timestamp)
            olddata = {}
            created = timestamp
            action = "create"
            
        if transaction_id is None:
            transaction_id = self._add_transaction(action=action, author=author, ip=ip, comment=comment, created=timestamp)
        revision = self._add_version(thing_id=thing_id, revision=revision, transaction_id=transaction_id, created=timestamp)
                
        self._update_tables(thing_id, key, olddata, dict(data)) #@@ why making copy of data?
        
        data['created'] = created
        data['revision'] = revision
        data['last_modified'] = timestamp
        data['key'] = key
        data['latest_revision'] = revision
                
        data = common.format_data(data)
        
        self.db.update('thing', where='id=$thing_id', last_modified=timestamp, latest_revision=revision, type=type_id, vars=locals())
        self.db.insert('data', seqname=False, thing_id=thing_id, revision=revision, data=simplejson.dumps(data))
        
        web.ctx.new_objects[key] = simplejson.dumps(data)    
        return {'key': key, 'revision': revision}
        
    def get_property_id_cache(self):
        if self.property_id_cache is None:
            self.property_id_cache = {}
            for d in self.db.select('property'):
                self.property_id_cache[d.type, d.name] = d.id
        return self.property_id_cache
        
    def get_property_id(self, type_id, name, create=False):
        cache = self.get_property_id_cache()
        if (type_id, name) in cache:
            return cache[type_id, name]
            
        pid = self._get_property_id(type_id, name, create)
        # Don't update the cache when the pid is created. The pid creation might be part of a transaction and that might get rolled back.
        if pid is not None and create is False:
            cache[type_id, name] = pid
        return pid
            
    def _get_property_id(self, type_id, name, create=False):
        d = self.db.select('property', where='name=$name AND type=$type_id', vars=locals())
        if d:
            return d[0].id
        elif create:
            return self.db.insert('property', type=type_id, name=name)
        else:
            return None

    def things(self, query):
        type = query.get_type()
        if type:
            type_metedata = self.get_metadata(type)
            if type_metedata:
                type_id = type_metedata.id
            else:
                # Return empty result when type not found
                return []
        else:
            type_id = None
        
        # type is required if there are conditions/sort on keys other than [key, type, created, last_modified]
        common_properties = ['key', 'type', 'created', 'last_modified'] 
        _sort = query.sort and query.sort.key
        if _sort and _sort.startswith('-'):
            _sort = _sort[1:]
        type_required = bool([c for c in query.conditions if c.key not in common_properties]) or (_sort and _sort not in common_properties)
        
        if type_required and type is None:
            raise common.BadData("Type Required")
        
        class DBTable:
            def __init__(self, name, label=None):
                self.name = name
                self.label = label or name
                
            def sql(self):
                if self.label != self.name:
                    return "%s as %s" % (self.name, self.label)
                else:
                    return self.name
                    
            def __repr__(self):
                return self.label
                
        class Literal:
            def __init__(self, value):
                self.value = value
                
            def __repr__(self):
                return self.value

        tables = {}
        
        def get_table(datatype, key):
            if key not in tables:
                assert type is not None, "Missing type"            
                table = self.schema.find_table(type, datatype, key)
                label = 'd%d' % len(tables)
                tables[key] = DBTable(table, label)
            return tables[key]
            
        wheres = []
        
        def process(c, ordering_func=None):
            # ordering_func is used when the query contains emebbabdle objects
            #
            # example: {'links': {'title: 'foo', 'url': 'http://example.com/foo'}}
            if c.datatype == 'ref':
                metadata = self.get_metadata(c.value)
                if metadata is None:
                    # required object is not found so the query result wil be empty. 
                    # Raise StopIteration to indicate empty result.
                    raise StopIteration
                c.value = metadata.id
            if c.op == '~':
                op = Literal('LIKE')
                c.value = c.value.replace('*', '%')
            else:
                op = Literal(c.op)
                
            if c.key in ['key', 'type', 'created', 'last_modified']:
                #@@ special optimization to avoid join with thing.type when there are non-common properties in the query.
                #@@ Since type information is already present in property table, 
                #@@ getting property id is equivalent to join with type.
                if c.key == 'type' and type_required:
                    return
                    
                if isinstance(c.value, list):
                    q = web.sqlors('thing.%s %s ' % (c.key, op), c.value)
                else:
                    q = web.reparam('thing.%s %s $c.value' % (c.key, op), locals())
                xwheres = [q]
                
                # Add thing table explicitly because get_table is not called
                tables['_thing'] = DBTable("thing")
            else:
                table = get_table(c.datatype, c.key)
                key_id = self.get_property_id(type_id, c.key)
                if not key_id:
                    raise StopIteration
                    
                q1 = web.reparam('%(table)s.key_id=$key_id' % {'table': table}, locals())
                
                if isinstance(c.value, list):
                    q2 = web.sqlors('%s.value %s ' % (table, op), c.value)
                else:
                    q2 = web.reparam('%s.value %s $c.value' % (table, op), locals())
                
                xwheres = [q1, q2]
                if ordering_func:
                    xwheres.append(ordering_func(table))
            wheres.extend(xwheres)
            
        def make_ordering_func():
            d = web.storage(table=None)
            def f(table):
                d.table = d.table or table
                return '%s.ordering = %s.ordering' % (table, d.table)
            return f
            
        import readquery
        def process_query(q, ordering_func=None):
            for c in q.conditions:
                if isinstance(c, readquery.Query):
                    process_query(c, ordering_func or make_ordering_func())
                else:
                    process(c, ordering_func)
                    
        def process_sort(query):
            """Process sort field in the query and returns the db column to order by."""
            if query.sort:
                sort_key = query.sort.key
                if sort_key.startswith('-'):
                    ascending = " desc"
                    sort_key = sort_key[1:]
                else:
                    ascending = ""
                    
                if sort_key in ['key', 'type', 'created', 'last_modified']:
                    order = 'thing.' + sort_key # make sure c.key is valid
                    # Add thing table explicitly because get_table is not called
                    tables['_thing'] = DBTable("thing")                
                else:   
                    table = get_table(query.sort.datatype, sort_key)
                    key_id = self.get_property_id(type_id, sort_key)
                    if key_id is None:
                        raise StopIteration
                    q = '%(table)s.key_id=$key_id' % {'table': table}
                    wheres.append(web.reparam(q, locals()))
                    order = table.label + '.value'
                return order + ascending
            else:
                return None
        
        try:
            process_query(query)
            # special care for case where query {}.
            if not tables:
                tables['_thing'] = DBTable('thing')
            order = process_sort(query)
        except StopIteration:
            return []
            
        def add_joins():
            labels = [t.label for t in tables.values()]
            def get_column(table):
                if table == 'thing': return 'thing.id'
                else: return table + '.thing_id'
                
            if len(labels) > 1:
                x = labels[0]
                xwheres = [get_column(x) + ' = ' + get_column(y) for y in labels[1:]]
                wheres.extend(xwheres)
        
        add_joins()
        wheres = wheres or ['1 = 1']
        table_names = [t.sql() for t in tables.values()]

        t = self.db.transaction()
        if config.query_timeout:
            self.db.query("SELECT set_config('statement_timeout', $query_timeout, false)", dict(query_timeout=config.query_timeout))
            
        if 'thing' in table_names:
            result = self.db.select(
                what='thing.key', 
                tables=table_names, 
                where=self.sqljoin(wheres, ' AND '), 
                order=order,
                limit=query.limit, 
                offset=query.offset,
                )
            keys = [r.key for r in result]
        else:
            result = self.db.select(
                what='d0.thing_id', 
                tables=table_names, 
                where=self.sqljoin(wheres, ' AND '), 
                order=order,
                limit=query.limit, 
                offset=query.offset,
            )
            ids = [r.thing_id for r in result]
            rows = ids and self.db.query('SELECT id, key FROM thing where id in $ids', vars={"ids": ids})
            d = dict((r.id, r.key) for r in rows)
            keys = [d[id] for id in ids]
        t.commit()
        return keys
        
    def sqljoin(self, queries, delim):
        return web.SQLQuery.join(queries, delim)
        
    def versions(self, query):
        what = 'thing.key, version.revision, transaction.*'
        where = 'version.thing_id = thing.id AND version.transaction_id = transaction.id'

        if config.get('use_machine_comment'):
            what += ", version.machine_comment"
            
        def get_id(key):
            meta = self.get_metadata(key)
            if meta:
                return meta.id
            else:
                raise StopIteration
        
        for c in query.conditions:
            key, value = c.key, c.value
            assert key in ['key', 'type', 'author', 'ip', 'comment', 'created', 'bot', 'revision']
            
            try:
                if key == 'key':
                    key = 'thing_id'
                    value = get_id(value)
                elif key == 'revision':
                    key = 'version.revision'
                elif key == 'type':
                    key = 'thing.type'
                    value = get_id(value)
                elif key == 'author':
                    key = 'transaction.author_id'
                    value = get_id(value)
                else:
                    # 'bot' column is not enabled
                    if key == 'bot' and not config.use_bot_column:
                        bots = [r.thing_id for r in self.db.query("SELECT thing_id FROM account WHERE bot='t'")] or [-1]
                        if value == True or str(value).lower() == "true":
                            where += web.reparam(" AND transaction.author_id IN $bots", {"bots": bots})
                        else:
                            where += web.reparam(" AND (transaction.author_id NOT IN $bots OR transaction.author_id IS NULL)", {"bots": bots})
                        continue
                    else:
                        key = 'transaction.' + key
            except StopIteration:
                # StopIteration is raised when a non-existing object is referred in the query
                return []
                
            where += web.reparam(' AND %s=$value' % key, locals())
            
        sort = query.sort
        if sort and sort.startswith('-'):
            sort = sort[1:] + ' desc'

        sort = 'transaction.' + sort
        
        t = self.db.transaction()
        if config.query_timeout:
            self.db.query("SELECT set_config('statement_timeout', $query_timeout, false)", dict(query_timeout=config.query_timeout))
                
        result = self.db.select(['thing','version', 'transaction'], what=what, where=where, offset=query.offset, limit=query.limit, order=sort)
        result = result.list()
        author_ids = list(set(r.author_id for r in result if r.author_id))
        authors = self.get_metadata_list_from_ids(author_ids)
        
        t.commit()
        
        for r in result:
            r.author = r.author_id and authors[r.author_id].key
        return result
    
    def get_user_details(self, key):
        """Returns a storage object with user email and encrypted password."""
        metadata = self.get_metadata(key)
        if metadata is None:
            return None
            
        d = self.db.query("SELECT * FROM account WHERE thing_id=$metadata.id", vars=locals())
        return d and d[0] or None
        
    def update_user_details(self, key, **params):
        """Update user's email and/or encrypted password."""
        metadata = self.get_metadata(key)
        if metadata is None:
            return None
            
        for k, v in params.items():
            assert k in ['bot', 'active', 'verified', 'email', 'password']
            if v is None:
                del params[k]
        
        self.db.update('account', where='thing_id=$metadata.id', vars=locals(), **params)
            
    def register(self, key, email, enc_password):
        metadata = self.get_metadata(key)
        self.db.insert('account', False, email=email, password=enc_password, thing_id=metadata.id)
        
    def transact(self, f):
        t = self.db.transaction()
        try:
            f()
        except:
            t.rollback()
            raise
        else:
            t.commit()
    
    def find_user(self, email):
        """Returns the key of the user with the specified email."""
        d = self.db.select('account', where='email=$email', vars=locals())
        thing_id = d and d[0].thing_id or None
        return thing_id and self.get_metadata_from_id(thing_id).key
    
    def initialize(self):
        if not self.initialized():
            t = self.db.transaction()
            
            id = self.new_thing(key='/type/type')
            last_modified = datetime.datetime.utcnow()
            
            data = dict(
                key='/type/type',
                type={'key': '/type/type'},
                last_modified={'type': '/type/datetime', 'value': last_modified},
                created={'type': '/type/datetime', 'value': last_modified},
                revision=1,
                latest_revision=1,
                id=id
            )
            
            self.db.update('thing', type=id, where='id=$id', vars=locals())
            self.db.insert('version', False, thing_id=id, revision=1)
            self.db.insert('data', False, thing_id=id, revision=1, data=simplejson.dumps(data))
            t.commit()
            
    def initialized(self):
        return self.get_metadata('/type/type') is not None
        
    def delete(self):
        t = self.db.transaction()
        self.db.delete('data', where='1=1')
        self.db.delete('version', where='1=1')
        self.db.delete('transaction', where='1=1')
        self.db.delete('account', where='1=1')
        
        for table in self.schema.list_tables():
            self.db.delete(table, where='1=1')
            
        self.db.delete('property', where='1=1')
        self.db.delete('thing', where='1=1')
        t.commit()
        self.cache.clear()

class DBStore(common.Store):
    """StoreFactory that works with single site. 
    It always returns a the same site irrespective of the sitename.
    """
    def __init__(self, schema):
        self.schema = schema
        self.sitestore = None
        self.db = web.database(**web.config.db_parameters)
        
    def has_initialized(self):
        try:
            self.db.select('thing', limit=1)
            return True
        except:
            return False
        
    def create(self, sitename):
        if self.sitestore is None:
            self.sitestore = DBSiteStore(self.db, self.schema)
            if not self.has_initialized():
                q = str(self.schema.sql())
                self.db.query(web.SQLQuery([q]))
        self.sitestore.initialize()
        return self.sitestore
        
    def get(self, sitename):
        if self.sitestore is None:
            sitestore = DBSiteStore(self.db, self.schema)
            if not self.has_initialized():
                return None
            self.sitestore = sitestore
            
        if not self.sitestore.initialized():
            return None            
        return self.sitestore

    def delete(self, sitename):
        if not self.has_initialized():
            return
        d = self.get(sitename)
        d and d.delete()
            
class MultiDBStore(DBStore):
    """DBStore that works with multiple sites.
    """
    def __init__(self, schema):
        self.schema = schema
        self.sitestores = {}
        self.db = web.database(**web.config.db_parameters)
        
    def create(self, sitename):
        t = self.db.transaction()
        try:
            site_id = self.db.insert('site', name=sitename)
            sitestore = MultiDBSiteStore(self.db, self.schema, sitename, site_id)
            sitestore.initialize()
            self.sitestores[sitename] = sitestore
        except:
            t.rollback()
            raise
        else:
            t.commit()
            return self.sitestores[sitename]
            
    def get(self, sitename):
        if sitename not in self.sitestores:
            site_id = self.get_site_id(sitename)
            if site_id is None:
                return None
            else:
                self.sitestores[sitename] = MultiDBSiteStore(self.schema, sitename, site_id)
        return self.sitestores[sitename]
        
    def get_site_id(self, sitename):
        d = self.db.query('SELECT * FROM site WHERE name=$sitename', vars=locals())
        return d and d[0].id or None
        
    def delete(self, sitename):
        pass
            
class MultiDBSiteStore(DBSiteStore):
    def __init__(self, db, schema, sitename, site_id):
        DBStore.__init__(self, db, schema)
        self.sitename = sitename
        self.site_id = site_id
        
    def get_metadata(self, key):
        d = self.db.query('SELECT * FROM thing WHERE site_id=self.site_id AND key=$key', vars=locals())
        return d and d[0] or None
        
    def get_metadata_list(self, keys):
        where = web.reparam('site_id=$self.site_id', locals()) + web.sqlors('key=', keys)
        result = self.db.select('thing', what='*', where=where).list()
        d = dict((r.key, r) for r in result)
        return d
        
    def new_thing(self, **kw):
        kw['site_id'] = self.site_id
        return self.db.insert('thing', **kw)
        
    def new_account(self, thing_id, email, enc_password):
        return self.db.insert('account', False, site_id=self.site_id, thing_id=thing_id, email=email, password=enc_password)

    def find_user(self, email):
        """Returns the key of the user with the specified email."""
        d = self.db.select('account', where='site_id=$self.site_id, $email=email', vars=locals())
        thing_id = d and d[0].thing_id or None
        return thing_id and self.get_metadata_from_id(thing_id).key
    
    def delete(self):
        pass
        
if __name__ == "__main__":
    import doctest
    doctest.testmod()
