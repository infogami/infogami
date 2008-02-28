"""
bulkupload script to upload multiple objects at once. 
All the inserts are merged to give better performance.
"""
import web
from multiple_insert import multiple_insert
from infobase import TYPES, DATATYPE_REFERENCE

def sqlin(name, values):
    """
        >>> sqlin('id', [1, 2, 3, 4])
        <sql: 'id IN (1, 2, 3, 4)'>
        >>> sqlin('id', [])
        <sql: '1 = 2'>
    """
    def sqljoin(queries, sep):
        result = ""
        for q in queries:
            if result:
                result = result + sep
            result = result + q
        return result
    
    if not values:
        return web.reparam('1 = 2', {})
    else:
        values = [web.reparam('$v', locals()) for v in values]
        return name + ' IN ('+ sqljoin(values, ", ") + ')'

class BulkUpload:
    def __init__(self, site):
        self.site = site
        self.key2id = {}
        
    def upload(self, query):
        """Inserts"""
        assert isinstance(query, list)
        web.transact()
        try:
            self.process_creates(query)
            self.process_inserts(query)
        except:
            web.rollback()
            raise
        else:
            web.commit()
            
    def process_creates(self, query):
        keys = set(self.find_keys(query))
        tobe_created = set(self.find_creates(query))
        
        result = web.select('thing', what='id, key', where=sqlin('key', keys))
        for r in result:
            self.key2id[r.key] = r.id
        
        values = [dict(key=k, site_id=self.site.id) for k in tobe_created if k not in self.key2id]
        ids = multiple_insert('thing', values)
        for v, id in zip(values, ids):
            self.key2id[v['key']] = id
        multiple_insert('version', [dict(thing_id=id) for id in ids])
    
    def find_keys(self, query, result=None):
        if result is None:
            result = []
        if isinstance(query, list):
            for q in query: 
                self.find_creates(q, result)
        elif isinstance(query, dict) and 'key' in query:
            result.append(query['key'])
        return result
    
    def find_creates(self, query, result=None):
        """Find keys of all queries which have 'create' key.
        """
        if result is None: 
            result = []
            
        if isinstance(query, list):
            for q in query:
                self.find_creates(q, result)
        elif isinstance(query, dict):
            if 'create' in query:
                result.append(query['key'])
                self.find_creates(query.values(), result)
        return result
        
    def process_inserts(self, query):
        values = []
        for q in query:
            self.prepare_datum(q, values)
        multiple_insert('datum', values, seqname=False)
        
    def prepare_datum(self, query, result):
        """This is a funtion with side effect. 
        It append values to be inserted to datum table into result and return (value, datatype) for that query.
        """
        def append(thing_id, key, value, datatype, ordering):
            result.append(dict(
                thing_id=thing_id, 
                begin_revision=1, 
                key=key, 
                value=value, 
                datatype=datatype, 
                ordering=ordering))
        
        if isinstance(query, dict):
            if 'value' in query:
                return (query['value'], TYPES[query['type']])
            else:
                thing_id = self.key2id[query['key']]
                for key, value in query.items():
                    if 'key' == 'create': 
                        continue
                    if isinstance(value, list):
                        for i, v in enumerate(value):
                            _value, datatype = self.prepare_datum(v, result)
                            append(thing_id, key, _value, datatype, i)
                    else:
                        _value, datatype = self.prepare_datum(value, result)
                        append(thing_id, key, _value, datatype, None)
                return (thing_id, DATATYPE_REFERENCE)
        elif isinstance(query, basestring):
            return (query, TYPES['type/string'])
        elif isinstance(query, int):
            return (query, TYPES['type/int'])
        elif isinstance(query, float):
            return (query, TYPES['type/float'])
        elif isinstance(query, bool):
            return (query, TYPES['type/boolean'])
        else:
            raise Exception, 'invalid value: ' + repr(value)    

if __name__ == "__main__":
    web.config.db_parameters = dict(dbn='postgres', db='infobase', user='anand', pw='') 
    #web.config.db_printing = True
    web.load()
    from infobase import Infobase
    site = Infobase().get_site('infogami.org')
    
    def book(i):
        return {
            'create': 'unless_exists',
            'key': 'b/b%d' % i,
            'title': "title-%d" % i,
            'description': {'type': 'type/text', 'value': 'description-%d' % i},
            'author': {'create': 'unless_exists', 'key': 'a/a%d' % i, 'name': 'author %d' % i},
            'publisher': {'create': 'unless_exists', 'key': 'p/%d' % i, 'name': 'publisher %d' % i},
        }

    web.transact()
    for j in range(200):
        q = [book(j * 100 + i) for i in range(100)]
        BulkUpload(site).upload(q)
    web.rollback()
