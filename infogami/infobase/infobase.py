import web
from multiple_insert import multiple_insert

KEYWORDS = "id", "create", "limit", "offset", "index"

DATETYPE_REFERENCE = 0

PRIMITIVE_TYPES = {}
PRIMITIVE_TYPES['type/key'] = 1
PRIMITIVE_TYPES['type/string'] = 2
PRIMITIVE_TYPES['type/text'] = 3
PRIMITIVE_TYPES['type/uri'] = 4
PRIMITIVE_TYPES['type/boolean'] = 5
PRIMITIVE_TYPES['type/int'] = 6
PRIMITIVE_TYPES['type/float'] = 7
PRIMITIVE_TYPES['type/datetime'] = 8

class InfobaseException(Exception):
    pass
    
class SiteNotFound(InfobaseException):
    pass

def transactify(f):
    def g(*a, **kw):
        web.transact()
        try:
            result = f(*a, **kw)
        except:
            web.rollback()
            raise
        else:
            web.commit()
        return result
    return g

class Infobase:
    def get_site(self, name):
        d = web.select('site', where='name=$name', vars=locals())
        if d:
            return Infosite(d.id, d.name)
        else:
            raise SiteNotFound(name)
    
    def create_site(self, name):
        id = web.insert('site', name=name)
        site = Infosite(id, name)
        import bootstrap
        site.create(bootstrap.types)
        return site
    
    def delete_site(self, name):
        pass
        
class Infosite:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        
    @transactify
    def create(self, data):
        """Creates a new thing."""
        env = {}
        self._create_things(data, env)
        self._populate_data(data, env)
        
    def _create_things(self, data, env):
        if isinstance(data, list):
            for d in data:
                self._create_things(d, env)
        elif isinstance(data, dict) and 'create' in data:
            assert 'key' in data
            key = data['key']
            env[key] = web.insert('thing', site_id=self.id, key=key)
            self._create_things(data.values(), env)
            
    def _populate_data(self, data, env):
        if isinstance(data, list):
            for d in data:
                self._populate_data(d, env)
        elif isinstance(data, dict) and 'create' in data:
            self._populate_data(data.values(), env)
            assert 'key' in data
            del data['create']
            key = data['key']
            thing_id = env[key]
            version_id = web.insert('version', thing_id=thing_id)
            version = web.select('version', where='id=$version_id', vars=locals())[0]
            multiple_insert('datum', self._process_values(data, thing_id, version.revision), seqname=False)

    def _process_values(self, d, thing_id, begin_revision):
        def query(key):
            site_id = self.id
            d = web.select('thing', what='id', where='site_id = $site_id AND key=$key', vars=locals())
            assert d
            return d[0].id

        def parse(d):
            if isinstance(d, dict):
                if 'key' in d:
                    return query(d['key']), DATETYPE_REFERENCE
                else:
                    assert 'type' in d and 'value' in d
                    assert d['type'] in PRIMITIVE_TYPES
                    return d['value'], PRIMITIVE_TYPES[d['type']]
            else:
                return d, PRIMITIVE_TYPES['type/string']

        result = []
        def add(key, value, datatype):
            if key == 'key': 
                datatype = PRIMITIVE_TYPES['type/key']
            result.append(dict(thing_id=thing_id, key=key, value=value, datatype=datatype, begin_revision=begin_revision))

        for key, val in d.items():
            if isinstance(val, list):
                for v in val:
                    val, datatype = parse(v)
                    add(key, val, datatype)
            else:
                val, datatype = parse(val)
                add(key, val, datatype)

        return result

if __name__ == "__main__":
    import os
    os.system('dropdb infobase; createdb infobase; createlang plpgsql infobase; psql infobase < schema.sql')
    web.config.db_parameters = dict(dbn='postgres', db='infobase', user='anand', pw='') 
    web.config.db_printing = True
    web.load()
    infobase = Infobase()
    site = infobase.create_site('infogami.org')

