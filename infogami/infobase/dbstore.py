"""Infobase Implementation based on database.
"""
import common
import config
import web
import _json as simplejson
import datetime, time
from collections import defaultdict
import logging

from _dbstore import store, sequence
from _dbstore.schema import Schema, INDEXED_DATATYPES
from _dbstore.indexer import Indexer
from _dbstore.save import SaveImpl, PropertyManager
from _dbstore.read import RecentChanges, get_bot_users

default_schema = None

logger = logging.getLogger("infobase")

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
        self.property_manager = PropertyManager(self.db)
                
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
        if not keys:
            return {}
            
        result = self.db.select('thing', what='*', where="key IN $keys", vars=locals()).list()
        d = dict((r.key, r) for r in result)
        return d
        
    def new_thing(self, **kw):
        return self.db.insert('thing', **kw)
        
    def get_metadata_from_id(self, id):
        d = self.db.query('SELECT * FROM thing WHERE id=$id', vars=locals())
        return d and d[0] or None

    def get_metadata_list_from_ids(self, ids):
        if not ids:
            return {}
            
        result = self.db.select('thing', what='*', where="id IN $ids", vars=locals()).list()
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
        
    def get_many_as_dict(self, keys):
        if not keys:
            return {}
            
        query = 'SELECT thing.key, data.data from thing, data' \
            + ' WHERE data.revision = thing.latest_revision and data.thing_id=thing.id' \
            + ' AND thing.key IN $keys'
            
        return dict((row.key, row.data) for row in self.db.query(query, vars=locals()))
        
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
                    
    def save_many(self, docs, timestamp, comment, data, ip, author, action=None):
        docs = list(docs)
        action = action or "bulk_update"
        logger.debug("saving %d docs - %s", len(docs), dict(timestamp=timestamp, comment=comment, data=data, ip=ip, author=author, action=action))

        s = SaveImpl(self.db, self.schema, self.indexer, self.property_manager)
        
        # Hack to allow processing of json before using. Required for OL legacy.
        s.process_json = process_json
        
        docs = common.format_data(docs)
        changeset = s.save(docs, timestamp=timestamp, comment=comment, ip=ip, author=author, action=action, data=data)
        
        # update cache. 
        # Use the docs from result as they contain the updated revision and last_modified fields.
        for doc in changeset.get('docs', []):
            web.ctx.new_objects[doc['key']] = simplejson.dumps(doc)
            
        return changeset
        
    def save(self, key, doc, timestamp=None, comment=None, data=None, ip=None, author=None, transaction_id=None, action=None):
        logger.debug("saving %s", key)
        timestamp = timestamp or datetime.datetime.utcnow
        return self.save_many([doc], timestamp, comment, data, ip, author, action=action or "update")
        
    def reindex(self, keys):
        s = SaveImpl(self.db, self.schema, self.indexer, self.property_manager)
        # Hack to allow processing of json before using. Required for OL legacy.
        s.process_json = process_json        
        return s.reindex(keys)
        
    def get_property_id(self, type, name):
        return self.property_manager.get_property_id(type, name)

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
                key_id = self.get_property_id(type, c.key)
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
                if d.table == table:
                    # avoid a comparsion when both tables are same. it fails when ordering is None
                    return "1 = 1"
                else:
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
                    key_id = self.get_property_id(type, sort_key)
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
        
    def recentchanges(self, query):
        """Returns the list of changes matching the given query.
        
        Sample Queries:
            {"limit": 10, "offset": 100}
            {"limit": 10, "offset": 100, "key": "/authors/OL1A"}
            {"limit": 10, "offset": 100, "author": "/people/foo"}
        """
        engine = RecentChanges(self.db)
        
        limit = query.pop("limit", 1000)
        offset = query.pop("offset", 0)
        
        keys = "key", "author", "ip", "kind", "bot", "begin_date", "end_date", "data"
        kwargs = dict((k, query[k]) for k in keys if k in query)
        
        return engine.recentchanges(limit=limit, offset=offset, **kwargs)
        
    def get_change(self, id):
        """Return the info about the requrested change.
        """
        engine = RecentChanges(self.db)
        return engine.get_change(id)
        
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
                        bots = get_bot_users(self.db)
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
        self.db = create_database(**web.config.db_parameters)
        
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
        self.db = create_database(**web.config.db_parameters)
        
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

def create_database(**params):
    db = web.database(**params)
    
    # monkey-patch query method to collect stats
    _query = db.query
    def query(*a, **kw):
        t_start = time.time()
        result = _query(*a, **kw)
        t_end = time.time()
        
        web.ctx.querytime = web.ctx.get("querytime", 0.0) + t_end - t_start
        web.ctx.queries = web.ctx.get("queries", 0) + 1
        
        return result
        
    db.query = query
    return db
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
