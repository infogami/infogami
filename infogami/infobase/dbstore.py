"""Infobase Implementation based on database.
"""
import common
import web
import _json as simplejson
import datetime, time
from multiple_insert import multiple_insert

INDEXED_DATATYPES = ["str", "int", "float", "ref", "boolean", "datetime"]

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
        
    def add_table_group(self, prefix, type):
        for d in INDEXED_DATATYPES:
            self.add_entry(prefix + "_" + d, type, d, None)
            
        self.prefixes.add(prefix)
        
    def find_table(self, type, datatype, name):
        if datatype not in INDEXED_DATATYPES:
            return None
            
        def match(a, b):
            return a is None or a == b
        for e in self.entries:
            if match(e.type, type) and match(e.datatype, datatype) and match(e.name, name):
                return e.table
        
        return 'datum_' + datatype
        
    def sql(self):
        import os
        prefixes = sorted(list(self.prefixes) + ['datum'])
        sequences = [self.get_seq(type).name for type in self.sequences]
        
        path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        t = web.template.frender(path)
        
        web.template.Template.globals['dict'] = dict
        web.template.Template.globals['enumerate'] = enumerate
        return t(prefixes, sequences, self.multisite)
        
    def __str__(self):
        lines = ["%s\t%s\t%s\t%s" % (e.table, e.type, e.datatype, e.name) for e in self.entries]
        return "\n".join(lines)
        
class DBSiteStore(common.SiteStore):
    """
    """
    def __init__(self, schema):
        self.schema = schema
        self.sitename = None
        
        self.cache = None
        self.property_id_cache = {}
        
    def set_cache(self, cache):
        self.cache = cache

    def get_metadata(self, key):
        if self.cache and key in self.cache:
            thing = self.cache[key]
            return thing and web.storage(id=thing.id, key=thing.key, last_modified=thing.last_modified, created=thing.created, type=thing.type.id)
        d = web.query('SELECT * FROM thing WHERE key=$key', vars=locals())
        return d and d[0] or None
        
    def get_metadata_list(self, keys):
        result = web.select('thing', what='*', where=web.sqlors('key=', keys)).list()
        d = dict((r.key, r) for r in result)
        return d
        
    def new_thing(self, **kw):
        return web.insert('thing', **kw)
        
    def get_metadata_from_id(self, id):
        d = web.query('SELECT * FROM thing WHERE id=$id', vars=locals())
        return d and d[0] or None

    def get_metadata_list_from_ids(self, ids):
        d = {}
        result = web.select('thing', what='*', where=web.sqlors('id=', ids)).list()
        d = dict((r.id, r) for r in result)
        return d
        
    def new_key(self, type, kw):
        seq = self.schema.get_seq(type)
        if seq:
            # repeat until a non-existing key is found.
            # This is required to prevent error in cases where an object with the next key is already created.
            while True:
                value = web.query("SELECT NEXTVAL($seq.name) as value", vars=locals())[0].value
                key = seq.pattern % value
                if self.get_metadata(key) is None:
                    return key
        else:
            return common.SiteStore.new_key(self, type, kw)
        
    def get(self, key, revision=None):
        if self.cache is None or revision is not None:
            return self._get(key, revision)
        else:
            if key not in self.cache:
                thing = self._get(key, revision)
                self.cache[key] = thing
            else:
                thing = self.cache[key]
            return thing
    
    def _get(self, key, revision):    
        metadata = self.get_metadata(key)
        if not metadata: 
            return None
        revision = revision or metadata.latest_revision
        d = web.query('SELECT data FROM data WHERE thing_id=$metadata.id AND revision=$revision', vars=locals())
        data = d and d[0].data 
        if not data:
            return None
        thing = common.Thing.from_json(self, key, data)
        #@@ why is this required? for bootstrap?
        thing.set('type', self.get_metadata_from_id(metadata.type).key, 'ref')
        return thing
        
    def get_many(self, keys):
        if not keys:
            return o

        xkeys = [web.reparam('$k', dict(k=k)) for k in keys]
        query = 'SELECT thing.key, data.data from thing, data ' \
            + 'WHERE data.revision = thing.latest_revision and data.thing_id=thing.id ' \
            + ' AND thing.key IN (' + self.sqljoin(xkeys, ', ') + ')'

        result = {}
        for r in web.query(query):
            result[r.key] = common.LazyThing(self, r.key, r.data)
        return result
        
    def write(self, queries, timestamp=None, comment=None, machine_comment=None, ip=None, author=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        versions = {}
        def add_version(thing_id, revision=None):
            """Adds a new entry in the version table for the object specified by thing_id and returns the latest revision."""
            if thing_id not in versions:
                if revision is None:
                    d = web.query(
                        'UPDATE thing set latest_revision=latest_revision+1, last_modified=$timestamp WHERE id=$thing_id;' + \
                        'SELECT latest_revision FROM thing WHERE id=$thing_id', vars=locals())
                    revision = d[0].latest_revision
                    
                web.insert('version', False, 
                    thing_id=thing_id, 
                    revision=revision, 
                    created=timestamp,
                    comment=comment,
                    machine_comment=machine_comment,
                    ip=ip,
                    author_id=author and self.get_metadata(author).id
                    )
                versions[thing_id] = revision
            return versions[thing_id]
        
        result = web.storage(created=[], updated=[])
        web.transact()
        for action, key, data in queries:
            if action == 'create':
                self.create(key, data, timestamp, add_version)
                result.created.append(key)
            elif action == 'update':
                self.update(key, data, timestamp, add_version)
                result.updated.append(key)
        web.commit()
        return result
    
    def create(self, key, data, timestamp, add_version):
        type = data.pop('type').value
        type_id = self.get_metadata(type).id

        thing_id = self.new_thing(key=key, type=type_id, latest_revision=1, last_modified=timestamp, created=timestamp)
        add_version(thing_id, 1)
        
        _inserts = {}

        def insert(name, value, datatype, ordering=None):
            if datatype not in INDEXED_DATATYPES:
                return
                
            if datatype == 'ref':
                value = self.get_metadata(value).id

            table = self.schema.find_table(type, datatype, name)
            pid = self.get_property_id(table, name, create=True)
            
            if table not in _inserts:
                _inserts[table] = []
            
            row = dict(thing_id=thing_id, key_id=pid, value=value, ordering=ordering)
            _inserts[table].append(row)
            
        d = {}
        for name, datum in data.items():
            d[name] = (datum.datatype, datum.value)
            if isinstance(datum.value, list):
                for i, v in enumerate(datum.value):
                    insert(name, v, datum.datatype, ordering=i)
            else:
                insert(name, datum.value, datum.datatype)
                
        for table, rows in _inserts.items():
            multiple_insert(table, rows, seqname=False)
            
        d['key'] = 'key', key
        d['created'] = ('datetime', timestamp)
        d['last_modified'] = ('datetime', timestamp)
        d['id'] = 'int', thing_id
        d['revision'] = 'int', 1
        d['type'] = 'ref', type
        
        thing = common.Thing(self, key, data=d)
        web.insert('data', False, thing_id=thing_id, revision=1, data=thing.to_json())
        
    def unkey(self, data):
        """Replace keys with ids.
        TODO: explain better
        """
        for k, v in data.items():
            if v.datatype == 'ref':
                if isinstance(v.value, list):
                    v.xvalue = [self.get_metadata(key).id for key in v.value]
                else:
                    v.xvalue = self.get_metadata(v.value).id
            else:
                v.xvalue = v.value
		
    def get_property_id(self, table, name, create=False):
        if table is None:
            return None
        
        if (table, name) not in self.property_id_cache:
            self.property_id_cache[table, name] = self._get_property_id(table, name, create)
            
        return self.property_id_cache[table, name]
            
    def _get_property_id(self, table, name, create=False):
        if table is None:
            return None
        property_table = table.split('_')[0] + '_keys'
        d = web.select(property_table, where='key=$name', vars=locals())
        if d:
            return d[0].id
        elif create:
            return web.insert(property_table, key=name)
        else:
            return None
	    
    def update(self, key, actions, timestamp, add_version):
        thing = self.get(key).copy()
        thing_id = thing.id
        self.unkey(actions)
        
        thing.set('last_modified', timestamp, 'datetime')
        revision = add_version(thing.id)
        thing.set('revision', revision, 'int')
        
        if 'type' in actions:
            type = self.get(actions['type'].value)
            web.update('thing', where='id=$thing_id', type=type.id, vars=locals())
        else:
            type = thing.type
        
        for name, a in actions.items():
            table = self.schema.find_table(type.key, a.datatype, name)
            if a.connect == 'update':
                pid = self.get_property_id(table, name, create=True)
                #@@ TODO: table for delete should be found from the datatype of the existing value 
                table and web.delete(table, where='thing_id=thing_id and key_id=$pid', vars=locals())
                
                if a.value is not None:
                    table and web.insert(table, False, thing_id=thing_id, key_id=pid, value=a.xvalue)
                    thing.set(name, a.value, a.datatype)
                else:
                    if name in thing:
                        del thing[name]
    
            elif a.connect == 'insert':
                # using time as ordering so that insert always happens at the end.
                pid = self.get_property_id(table, name, create=True)
                d = web.query(
                    'SELECT max(ordering) as ordering FROM %s WHERE thing_id=$thing_id and key_id=$pid GROUP BY thing_id, key_id' % table,
                    vars=locals())
                ordering = (d and d[0].ordering + 1) or 0
                table and web.insert(table, False, thing_id=thing_id, key_id=pid, value=a.xvalue, ordering=ordering)
                value = thing.get_value(name) or []
                thing.set(name, value + [a.value], a.datatype)
            elif a.connect == 'delete':
                pid = self.get_property_id(table, name, create=False)
                if pid:
                    #@@ TODO: table for delete should be found from the datatype of the existing value 
                    table and web.delete(table, where='thing_id=thing_id and key_id=$pid and value=$a.xvalue', vars=locals())
                    value = [v for v in thing.get_value(name) or [] if v != a.value]
                    thing.set(name, value, a.datatype)
            elif a.connect == 'update_list':
                pid = self.get_property_id(table, name, create=True)
                
                #@@ TODO: table for delete should be found from the datatype of the existing value 
                table and web.delete(table, where='thing_id=thing_id and key_id=$pid', vars=locals())
                
                if a.value is not None:
                    for i, v in enumerate(a.xvalue):
                        table and web.insert(table, False, thing_id=thing_id, key_id=pid, value=v, ordering=i)
                thing.set(name, a.value, a.datatype)
                
        data = thing.to_json()
        web.insert('data', False, thing_id=thing_id, revision=revision, data=data)

    def things(self, query):
        type = query.get_type()
        
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
                table = self.schema.find_table(type, datatype, key)
                label = 'd%d' % len(tables)
                tables[key] = DBTable(table, label)
            return tables[key]
                    
        wheres = []
        
        for c in query.conditions:
            if c.datatype == 'ref':
                metadata = self.get_metadata(c.value)
                assert metadata is not None, 'Not found: ' + c.value
                c.value = metadata.id
                
            if c.op == '~':
                op = Literal('LIKE')
                c.value = c.value.replace('*', '%')
            else:
                op = Literal(c.op)
                
            if c.key in ['key', 'type', 'created', 'last_modified']:
                q = 'thing.%s %s $c.value' % (c.key, op)
                wheres += [web.reparam(q, locals())]
            else:
                assert type is not None, "Missing type"
                table = get_table(c.datatype, c.key)
                key_id = self.get_property_id(table.name, c.key)
                if not key_id:
                    return []
                
                q = '%(table)s.thing_id = thing.id AND %(table)s.key_id=$key_id AND %(table)s.value %(op)s $c.value' % {'table': table, 'op': op}
                wheres += [web.reparam(q, locals())]
        
        wheres = wheres or ['1 = 1']        
        tables = ['thing'] + [t.sql() for t in tables.values()]
        result = web.select(
            what='thing.key', 
            tables=tables, 
            where=self.sqljoin(wheres, ' AND '), 
            limit=query.limit, 
            offset=query.offset)
        return [r.key for r in result]
        
    def sqljoin(self, queries, delim):
        delim = web.SQLQuery(delim)
        result = web.SQLQuery('')
        for i, q in enumerate(queries):
            if i != 0:
                result = result + delim
            result = result + q
        return result
        
    def versions(self, query):
        what = 'thing.key, version.*'
        where = 'version.thing_id = thing.id'
        
        for c in query.conditions:
            key, value = c.key, c.value
            
            if key == 'key':
                key = 'thing_id'
                value = self.get_metadata(value).id
            elif key == 'author':
                key = 'author_id'
                value = self.get_metadata(value).id
                
            where += web.reparam(' AND %s=$value' % key, locals())
            
        sort = query.sort
        if sort and sort.startswith('-'):
            sort = sort[1:] + ' desc'
                
        result = web.select(['thing','version'], what=what, where=where, offset=query.offset, limit=query.limit, order=sort)
        result = result.list()
        author_ids = list(set(r.author_id for r in result if r.author_id))
        authors = self.get_metadata_list_from_ids(author_ids)
        
        for r in result:
            del r.thing_id
            r.author = r.author_id and authors[r.author_id].key
        return result
    
    def get_user_details(self, key):
        """Returns a storage object with user email and encrypted password."""
        metadata = self.get_metadata(key)
        if metadata is None:
            return None
            
        d = web.query("SELECT * FROM account WHERE thing_id=$metadata.id", vars=locals())
        return d and d[0] or None
        
    def update_user_details(self, key, email, enc_password):
        """Update user's email and/or encrypted password."""
        metadata = self.get_metadata(key)
        if metadata is None:
            return None
                    
        params = {}
        email and params.setdefault('email', email)
        enc_password and params.setdefault('password', enc_password)
        web.update('account', where='thing_id=$metadata.id', vars=locals(), **params)
            
    def register(self, key, email, enc_password):
        metadata = self.get_metadata(key)
        web.insert('account', False, email=email, password=enc_password, thing_id=metadata.id)
        
    def transact(self, f):
        web.transact()
        try:
            f()
        except:
            web.rollback()
            raise
        else:
            web.commit()
    
    def find_user(self, email):
        """Returns the key of the user with the specified email."""
        d = web.select('account', where='email=$email', vars=locals())
        thing_id = d and d[0].thing_id or None
        return thing_id and self.get_metadata_from_id(thing_id).key
    
    def initialize(self):
        if not self.initialized():
            web.transact()
            id = self.new_thing(key='/type/type')
            web.update('thing', type=id, where='id=$id', vars=locals())
            web.insert('version', False, thing_id=id, revision=1)
            web.insert('data', False, thing_id=id, revision=1, data='{"key": "/type/type", "id": %d, "revision": 1, "type": {"key": "/type/type"}}' % id)
            web.commit()
            
    def initialized(self):
        return self.get_metadata('/type/type') is not None

class DBStore(common.Store):
    """StoreFactory that works with single site. 
    It always returns a the same site irrespective of the sitename.
    """
    def __init__(self, schema):
        self.schema = schema
        self.sitestore = None
        
    def create(self, sitename):
        if self.sitestore is None:
            self.sitestore = DBSiteStore(self.schema)
        self.sitestore.initialize()
        return self.sitestore
        
    def get(self, sitename):
        if self.sitestore is None:
            sitestore = DBSiteStore(self.schema)
            if not sitestore.initialized():
                return None
            self.sitestore = sitestore
        return self.sitestore

    def delete(self, sitename):
        pass
            
class MultiDBStore(DBStore):
    """DBStore that works with multiple sites.
    """
    def __init__(self, schema):
        self.schema = schema
        self.sitestores = {}
        
    def create(self, sitename):
        web.transact()
        try:
            site_id = web.insert('site', name=sitename)
            sitestore = MultiDBSiteStore(self.schema, sitename, site_id)
            sitestore.initialize()
            self.sitestores[sitename] = sitestore
        except:
            web.rollback()
            raise
        else:
            web.commit()
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
        d = web.query('SELECT * FROM site WHERE name=$sitename', vars=locals())
        return d and d[0].id or None
            
class MultiDBSiteStore(DBSiteStore):
    def __init__(self, schema, sitename, site_id):
        DBStore.__init__(self, schema)
        self.sitename = sitename
        self.site_id = site_id
        
    def get_metadata(self, key):
        d = web.query('SELECT * FROM thing WHERE site_id=self.site_id AND key=$key', vars=locals())
        return d and d[0] or None
        
    def get_metadata_list(self, keys):
        where = web.reparam('site_id=$self.site_id', locals()) + web.sqlors('key=', keys)
        result = web.select('thing', what='*', where=where).list()
        d = dict((r.key, r) for r in result)
        return d
        
    def new_thing(self, **kw):
        kw['site_id'] = self.site_id
        return web.insert('thing', **kw)
        
    def new_account(self, thing_id, email, enc_password):
        return web.insert('account', False, site_id=self.site_id, thing_id=thing_id, email=email, password=enc_password)

    def find_user(self, email):
        """Returns the key of the user with the specified email."""
        d = web.select('account', where='site_id=$self.site_id, $email=email', vars=locals())
        thing_id = d and d[0].thing_id or None
        return thing_id and self.get_metadata_from_id(thing_id).key
                    
if __name__ == "__main__":
    schema = Schema()
    print schema.sql()
