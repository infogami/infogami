"""Infobase Implementation based on database.
"""
import common
import config
import web
import _json as simplejson
import datetime, time

INDEXED_DATATYPES = ["str", "int", "float", "ref", "boolean", "datetime"]

default_schema = None

class Schema:
    """Schema to map <type, datatype, key> to database table.
    
        >>> schema = Schema()
        >>> schema.add_entry('page_str', '/type/page', 'str', None)
        >>> schema.find_table('/type/page', 'str', 'title')
        'page_str'
        >>> schema.find_table('/type/article', 'str', 'title')
        'datum_str'
    """
    def __init__(self, multisite=False):
        self.entries = []
        self.sequences = {}
        self.prefixes = set()
        self.multisite = multisite
        self._table_cache = {}
        
    def add_entry(self, table, type, datatype, name):
        entry = web.storage(table=table, type=type, datatype=datatype, name=name)
        self.entries.append(entry)
        
    def add_seq(self, type, pattern='/%d'):
        self.sequences[type] = pattern
        
    def get_seq(self, type):
        if type in self.sequences:
            # name is 'type_page_seq' for type='/type/page'
            name = type[1:].replace('/', '_') + '_seq'
            return web.storage(type=type, pattern=self.sequences[type], name=name)
        
    def add_table_group(self, prefix, type, datatypes=None):
        datatypes = datatypes or INDEXED_DATATYPES
        for d in datatypes:
            self.add_entry(prefix + "_" + d, type, d, None)
            
        self.prefixes.add(prefix)
        
    def find_table(self, type, datatype, name):
        if datatype not in INDEXED_DATATYPES:
            return None
            
        def f():
            def match(a, b):
                return a is None or a == b
            for e in self.entries:
                if match(e.type, type) and match(e.datatype, datatype) and match(e.name, name):
                    return e.table
            return 'datum_' + datatype
        
        key = type, datatype, name
        if key not in self._table_cache:
            self._table_cache[key] = f()
        return self._table_cache[key]
        
    def find_tables(self, type):
        return [self.find_table(type, d, None) for d in INDEXED_DATATYPES]
        
    def sql(self):
        import os
        prefixes = sorted(list(self.prefixes) + ['datum'])
        sequences = [self.get_seq(type).name for type in self.sequences]
        
        path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        t = web.template.frender(path)

        self.add_table_group("datum", None)
        
        tables = sorted(set([(e.table, e.datatype) for e in self.entries]))
        web.template.Template.globals['dict'] = dict
        web.template.Template.globals['enumerate'] = enumerate
        return t(tables, sequences, self.multisite)
        
    def list_tables(self):
        self.add_table_group("datum", None)
        tables = sorted(set([e.table for e in self.entries]))
        return tables
        
    def __str__(self):
        lines = ["%s\t%s\t%s\t%s" % (e.table, e.type, e.datatype, e.name) for e in self.entries]
        return "\n".join(lines)
        
class DBSiteStore(common.SiteStore):
    """
    """
    def __init__(self, db, schema):
        self.db = db
        self.schema = schema
        self.sitename = None
        
        self.cache = None
        self.property_id_cache = {}
        
    def set_cache(self, cache):
        self.cache = cache

    def get_metadata(self, key):
        if self.cache and key in self.cache:
            thing = self.cache[key]
            return thing and web.storage(id=thing.id, key=thing.key, last_modified=thing.last_modified, created=thing.created, type=thing.type.id, latest_revision=thing.latest_revision)

        # postgres doesn't seem to like Reference objects even though Referece extends from unicode.
        if isinstance(key, common.Reference):
            key = unicode(key)

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
            return self._get(key, revision)
        else:
            thing = self.cache.get(key)
            if thing is None:
                thing = self._get(key, revision)
                if thing:
                    self.cache[key] = thing
            return thing
    
    def _get(self, key, revision):    
        metadata = self.get_metadata(key)
        if not metadata: 
            return None
        revision = revision or metadata.latest_revision
        d = self.db.query('SELECT data FROM data WHERE thing_id=$metadata.id AND revision=$revision', vars=locals())
        data = d and d[0].data 
        if not data:
            return None
        thing = common.Thing.from_json(self, key, data)

        # just to be careful about the old data
        for k in common.READ_ONLY_PROPERTIES:
            if k not in thing:
                thing._data[k] = metadata[k]

        return thing
        
    def get_many(self, keys):
        if not keys:
            return {}

        xkeys = [web.reparam('$k', dict(k=k)) for k in keys]
        query = 'SELECT thing.key, data.data from thing, data ' \
            + 'WHERE data.revision = thing.latest_revision and data.thing_id=thing.id ' \
            + ' AND thing.key IN (' + self.sqljoin(xkeys, ', ') + ')'

        result = {}
        for r in self.db.query(query):
            result[r.key] = common.LazyThing(self, r.key, r.data)
        return result
        
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
                
        def do_action(f, typekey, thing_id, name, value, ordering=None):
            if isinstance(value, list):
                for i, v in enumerate(value):
                    do_action(f, typekey, thing_id, name, v, i)
            elif isinstance(value, dict):
                for k, v in value.items():
                    do_action(f, typekey, thing_id, name + '.' + k, v, ordering)
            else:
                datatype = find_datatype(value)
                if datatype == 'ref':
                    value = self.get_metadata(value)
                    value = value and value.id
                elif datatype == 'str':
                    value = value[:2048] # truncate long strings
                elif isinstance(value, bool):
                    value = "ft"[int(value)] # convert boolean to 't' or 'f'
                table = self.schema.find_table(typekey, datatype, name)
                
                if table:
                    type_id = self.get_metadata(typekey).id
                    pid = self.get_property_id(type_id, name, create=True)
                    assert pid is not None
                    f(table, thing_id, pid, value, ordering)
        
        def action_delete(table, thing_id, key_id, value, ordering):
            self.db.delete(table, where='thing_id=$thing_id AND key_id=$key_id', vars=locals())
        
        def action_insert(table, thing_id, key_id, value, ordering):
            self.db.insert(table, seqname=False, thing_id=thing_id, key_id=key_id, value=value, ordering=ordering)

        old_type = olddata and olddata['type']
        new_type = newdata['type']

        for k in ['id', 'key', 'type', 'last_modified', 'created', 'revision']:
            olddata.pop(k, None)
            newdata.pop(k, None)
        
        removed, unchanged, added = common.dict_diff(olddata, newdata)
                
        if old_type != new_type:
            removed = olddata.keys()
            added = newdata.keys()
        
        for k in removed:
            do_action(action_delete, old_type, thing_id, k, olddata[k])
        
        for k in added:
            do_action(action_insert, new_type, thing_id, k, newdata[k])
                    
    def save_many(self, items, timestamp, comment, machine_comment, ip, author, action=None):
        action = action or "bulk_update"
        t = self.db.transaction()
        try:
            transaction_id = self._add_transaction(action=action, author=author, ip=ip, comment=comment, created=timestamp)
            result = [self.save(d['key'], d, transaction_id=transaction_id, timestamp=timestamp) for d in items]
        except:
            t.rollback()
            # clear local cache when something fails to avoid local cache changes due to
            # any earliers saves (in this save_many query) getting into global cache.
            self.cache.clear(local=True)
            raise
        else:
            t.commit()
        return result

    def save(self, key, data, timestamp=None, comment=None, machine_comment=None, ip=None, author=None, transaction_id=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        t = self.db.transaction()
        
        thing = self.get(key)
        typekey = data['type']

        if thing:
            revision = None
            thing_id = thing.id
            olddata = thing._get_data()
            action = "update"
        else:
            revision = 1
            type_id = self.get(typekey).id
            thing_id = self.new_thing(key=key, type=type_id, latest_revision=1, last_modified=timestamp, created=timestamp)
            olddata = {}
            action = "create"
    
        if transaction_id is None:
            transaction_id = self._add_transaction(action=action, author=author, ip=ip, comment=comment, created=timestamp)
        revision = self._add_version(thing_id=thing_id, revision=revision, transaction_id=transaction_id, created=timestamp)
        
        created = olddata and olddata['created']
    
        self._update_tables(thing_id, key, olddata, dict(data))
        
        data['created'] = created
        data['revision'] = revision
        data['last_modified'] = timestamp
        data['key'] = key
        data['id'] = thing_id
        data['latest_revision'] = revision
    
        if revision == 1:
            data['created'] = timestamp
        else:
            data['created'] = created
        
        data = common.format_data(data)
    
        type_id=self.get_metadata(typekey).id
        self.db.update('thing', where='id=$thing_id', last_modified=timestamp, latest_revision=revision, type=type_id, vars=locals())
        self.db.insert('data', seqname=False, thing_id=thing_id, revision=revision, data=simplejson.dumps(data))
        t.commit()
        
        thing = common.Thing.from_dict(self, key, data.copy())
        web.ctx.new_objects[key] = thing    
        return {'key': key, 'revision': revision}
        
    def get_property_id(self, type_id, name, create=False):
        if (type_id, name) in self.property_id_cache:
            return self.property_id_cache[type_id, name]
            
        pid = self._get_property_id(type_id, name, create)
        # Don't update the cache when the pid is created. The pid creation might be part of a transaction and that might get rolled back.
        if pid is not None and create is False:
            self.property_id_cache[type_id, name] = pid
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
        else:
            result = self.db.select(
                what='d0.thing_id', 
                tables=table_names, 
                where=self.sqljoin(wheres, ' AND '), 
                order=order,
                limit=query.limit, 
                offset=query.offset,
            )
            result = self.db.query('SELECT key FROM thing where ' + web.sqlors('id = ', [r.thing_id for r in result]))
        result = [r.key for r in result]
        t.commit()
        return result
        
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
            assert key in ['key', 'type', 'author', 'ip', 'comment', 'created', 'bot']
            
            try:
                if key == 'key':
                    key = 'thing_id'
                    value = get_id(value)
                elif key == 'type':
                    key = 'thing.type'
                    value = get_id(value)
                elif key == 'author':
                    key = 'transaction.author_id'
                    value = get_id(value)
                else:
                    # 'bot' column is not enabled
                    if key == 'bot' and not config.use_bot_column:
                        raise StopIteration
                        
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
        
    def update_user_details(self, key, email, enc_password):
        """Update user's email and/or encrypted password."""
        metadata = self.get_metadata(key)
        if metadata is None:
            return None
                    
        params = {}
        email and params.setdefault('email', email)
        enc_password and params.setdefault('password', enc_password)
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
