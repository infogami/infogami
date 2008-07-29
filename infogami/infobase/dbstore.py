"""Infobase Implementation based on database.
"""
import common
import web
import _json as simplejson
import datetime, time

class Table:
    """Interface to database table

        >>> t = Table('datum_str')
        >>> t.query('d', 'name', '=', 'foo')
        <sql: "d.key = 'name' AND d.value = 'foo'">
        >>> t = Table('book_author_ref', 'author')
        >>> t.query('d', 'author', '=', 34)
        <sql: 'd.value = 34'>
    """
    def __init__(self, name, key=None):
        self.name = name
        self.key = key
    
    def query(self, label, key, op, value):
        q = "%s.value %s $value" % (label, op)
        
        if self.key is None:
            q = "%s.key = $key" % (label) + ' AND ' + q
        return web.reparam(q, locals())
        
INDEXED_DATATYPES = ["str", "int", "float", "ref", "boolean", "url", "datetime"]
        
class Schema:
    """Schema to map <type, datatype, key> to database table.
    
        >>> schema = Schema()
        >>> schema.add_entry('page_str', '/type/page', 'str', None)
        >>> schema.find_table('/type/page', 'str', 'title')
        'page_str'
        >>> schema.find_table('/type/article', 'str', 'title')
        'datum_str'
    """
    def __init__(self):
        self.entries = []
        
    def add_entry(self, table, type, datatype, name):
        entry = web.storage(table=table, type=type, datatype=datatype, name=name)
        self.entries.append(entry)
        
    def add_table_group(self, prefix, type):
        for d in INDEXED_DATATYPES:
            schema.add_entry(prefix + "_" + d, type, d, None)
        
    def find_table(self, type, datatype, name):
        if datatype not in INDEXED_DATATYPES:
            return None
            
        def match(a, b):
            return a is None or a == b
        for e in self.entries:
            if match(e.type, type) and match(e.datatype, datatype) and match(e.name, name):
                return e.table
        
        return 'datum_' + datatype
        
    @staticmethod
    def parse(filename):
        def unstar(item):
            if item == '*':
                return None
            else:
                return item
                
        schema = Schema()
        entries = [line.strip().split() for line in open(filename).readlines() if line.strip() and not line.strip().startswith('#')]
        entries = [map(unstar, e) for e in entries]
        
        for table, type, datatype, name in entries:
            if datatype is None:
                for d in INDEXED_DATATYPES:
                    schema.add_entry(table + "_" + d, type, d, name)
            else:
                schema.add_entry(table, type, datatype, name)
        return schema
        
    def __str__(self):
        lines = ["%s\t%s\t%s\t%s" % (e.table, e.type, e.datatype, e.name) for e in self.entries]
        return "\n".join(lines)
                
class DBStore:
    """
    """
    def __init__(self, schema):
        self.schema = schema

    def get_metadata(self, key):
        d = web.query('SELECT * FROM thing WHERE key=$key', vars=locals())
        return d and d[0] or None
        
    def get_metadata_from_id(self, id):
        d = web.query('SELECT * FROM thing WHERE id=$id', vars=locals())
        return d and d[0] or None
        
    def get(self, key, revision=None):
        metadata = self.get_metadata(key)
        if not metadata: 
            return None
        revision = revision or metadata.latest_revision
        d = web.query('SELECT data FROM data WHERE thing_id=$metadata.id AND revision=$revision', vars=locals())
        data = d and d[0].data or '{}'
        thing = common.Thing.from_json(self, key, data)
        thing.set('type', self.get_metadata_from_id(metadata.type), 'ref')
        return thing
    
    def create(self, key, timestamp, data):
        web.transact()
        
        type = data.pop('type').value
        type_id = self.get_metadata(type).id

        thing_id = web.insert('thing', key=key, type=type_id, latest_revision=1, last_modified=timestamp, created=timestamp)

        web.ctx.infobase_context = web.storage(user=None, ip='127.0.0.1')
        ctx = web.ctx.infobase_context
        web.insert('version', False, thing_id=thing_id, created=timestamp, user_id=ctx.user and ctx.user.id, ip=ctx.ip, revision=1)
        
        def insert(name, value, datatype, ordering=None):
            if datatype not in INDEXED_DATATYPES:
                return
                
            if datatype == 'ref':
                value = self.get_metadata(value).id
            self._insert(thing_id, type, name, datatype, value, ordering=ordering)
        
        d = {}
        for name, datum in data.items():
            d[name] = (datum.datatype, datum.value)
            if isinstance(datum.value, list):
                for i, v in enumerate(datum.value):
                    insert(name, v, datum.datatype, ordering=i)
            else:
                insert(name, datum.value, datum.datatype)
            
        d['key'] = 'key', key
        d['created'] = ('datetime', timestamp)
        d['last_modified'] = ('datetime', timestamp)
        d['id'] = 'int', thing_id
        
        thing = common.Thing(store, key, data=d)
            
        web.insert('data', False, thing_id=thing_id, revision=1, data=thing.to_json())
        web.commit()
		
    def _insert(self, thing_id, type, name, datatype, value, ordering=None):
        table = self.schema.find_table(type, datatype, name)
        pid = self.get_property_id(table, name, create=True)
        web.insert(table, False, thing_id=thing_id, key_id=pid, value=value, ordering=ordering)
            
    def get_property_id(self, table, name, create=False):
        property_table = table.split('_')[0] + '_keys'
        d = web.select(property_table, where='key=$name', vars=locals())
        if d:
            return d[0].id
        elif create:
            return web.insert(property_table, key=name)
        else:
            return None
	    
    def update(self, key, timestamp, actions):
        thing = self.get(key)
        thing_id = thing.id
        
        thing.set('last_modified', timestamp, 'datetime')
        d = web.query(
            'UPDATE thing set latest_revision=latest_revision+1, last_modified=$timestamp WHERE id=$thing_id;' + \
            'SELECT latest_revision FROM thing WHERE id=$thing_id', vars=locals())
        revision = d[0].latest_revision
        
        web.insert('version', False, thing_id=thing_id, revision=revision, created=timestamp)
        
        for name, a in actions.items():
            table = self.schema.find_table(thing.type.key, a.datatype, name)
            if a.connect == 'update':
                pid = self.get_property_id(table, name, create=True)
                #@@ TODO: table for delete should be found from the datatype of the existing value 
                table and web.delete(table, where='thing_id=thing_id and key_id=$pid', vars=locals())
                
                if a.value is not None:
                    table and web.insert(table, False, thing_id=thing_id, key_id=pid, value=a.value)
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
                table and web.insert(table, False, thing_id=thing_id, key_id=pid, value=a.value, ordering=ordering)
                value = thing.get_value(name) or []
                thing.set(name, value + [a.value], a.datatype)
            elif a.connect == 'delete':
                pid = self.get_property_id(table, name, create=False)
                if pid:
                    #@@ TODO: table for delete should be found from the datatype of the existing value 
                    table and web.delete(table, where='thing_id=thing_id and key_id=$pid and value=$a.value', vars=locals())
                    value = [v for v in thing.get_value(name) or [] if v != a.value]
                    thing.set(name, value, a.datatype)
            elif a.connect == 'update_list':
                pid = self.get_property_id(table, name, create=True)
                
                #@@ TODO: table for delete should be found from the datatype of the existing value 
                table and web.delete(table, where='thing_id=thing_id and key_id=$pid', vars=locals())
                
                if a.value is not None:
                    for i, v in enumerate(a.value):
                        table and web.insert(table, False, thing_id=thing_id, key_id=pid, value=v, ordering=i)
                thing.set(name, a.value, a.datatype)
                
        data = thing.to_json()
        web.insert('data', False, thing_id=thing_id, revision=revision, data=data)

    def things(self, query):
        pass
    
if __name__ == "__main__":
    import web
    import writequery
    web.config.db_parameters = dict(dbn='postgres', db='infobase2', user='anand', pw='')
    web.config.db_printing = True
    web.load()
    schema = Schema()
    schema.add_table_group('sys', '/type/type')
    store = DBStore(schema)
    query = {
        'create': 'unless_exists',
        'key': '/bar',
        'type': {
            'create': 'unless_exists',
            'key': '/type/page',
            'type': '/type/type',
            'name': 'Page',
            'description': 'Page type'
        },
        'x': {'connect': 'delete', 'value': 42},   
        'title': 'Welcome',
        'description': {'type': '/type/text', 'value': 'blah blah'}
    }
    web.transact()
    for q in writequery.make_query(store, query):
        action, key, data = q
        if action == 'create':
            store.create(key, datetime.datetime.utcnow(), data)
        elif action == 'update':
            store.update(key, datetime.datetime.utcnow(), data)
    web.commit()