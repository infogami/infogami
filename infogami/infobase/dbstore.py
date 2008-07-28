"""Infobase Implementation based on database.
"""
import common
import web
import _json as simplejson
import datetime

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
        
INDEXED_DATATYPES = ["str", "int", "float", "ref"]
        
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
        
    def find_table(self, type, datatype, name):
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
        
        type = data.pop('type')
        type_id = self.get_metadata(type.value).id

        # replace key with id for all reference items
        for k, v in data.items():
            if v.datatype == 'ref':
                v.value = self.get_metadata(v.value).id

        thing_id = web.insert('thing', key=key, type=type_id, latest_revision=1, last_modified=timestamp, created=timestamp)

        web.ctx.infobase_context = web.storage(user=None, ip='127.0.0.1')
        ctx = web.ctx.infobase_context
        web.insert('version', False, thing_id=thing_id, created=timestamp, user_id=ctx.user and ctx.user.id, ip=ctx.ip, revision=1)
        
        d = {}
        for name, datum in data.items():
            d[k] = datum.value
            if datum.datatype == 'ref':
                datatype.value = self.get_metadata(datatype.value).id
            self._insert(thing_id, type, name, datum.datatype, datum.value)
            
        d['key'] = key
        d['created'] = timestamp
        d['last_modified'] = timestamp
        d['id'] = thing_id
            
        web.insert('data', False, thing_id=thing_id, revision=1, data=simplejson.dumps(d))
        web.commit()
		
    def _insert(self, thing_id, type, name, datatype, value):
        table = self.schema.find_table(type, datatype, name)
        pid = self.get_property_id(table, name, create=True)
        web.insert(table, False, thing_id=thing_id, key_id=pid, value=value)
            
    def get_property_id(self, table, name, create=False):
        property_table = table.split('_')[0] + '_keys'
        d = web.select(property_table, where='key=$name', vars=locals())
        if d:
            return d[0].id
        else:
            return web.insert(property_table, key=name)
	    
    def update(self, key, actions):
        thing = self.get(key)

        for a in actions:
            table = self.schema.find_table(thing.type.key, a.datatype, a.name)
            if a.connect == 'update':
                web.insert()
            elif a.connect == 'insert':
                pass
            elif a.connect == 'delete':
                pass
            elif a.connect == 'update':
                pass
                                
    def do_update(self, thing, name, datatype, value):
        pass
        
    def do_insert(self, thing, name, datatype, value, ordering):
        pass
        
    def do_delete(self, thing, name, datatype, value):
        pass
                    
    def things(self, query):
        pass
    
if __name__ == "__main__":
    import web
    import writequery
    web.config.db_parameters = dict(dbn='postgres', db='infobase2', user='anand', pw='')
    web.config.db_printing = True
    web.load()
    schema = Schema()
    store = DBStore(schema)
    query = {
        'create': 'unless_exists',
        'key': '/type/page',
        'type': '/type/type',
        'name': 'Page',
        'pages': 42,
        'description': 'Page type'
    }
    web.transact()
    for q in writequery.make_query(store, query):
        action, key, data = q
        if action == 'create':
            store.create(key, datetime.datetime.utcnow(), data)
    web.rollback()
