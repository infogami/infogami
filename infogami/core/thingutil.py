from infogami import tdb
import db
import web

def thingify(parent, name, type, d):
    def get_thing():
        try:
            return db.get_version(parent, name)
        except:
            t = db.new_version(parent, name, type, {})
            t.save()
            return t
        
    def process(value, type):
        if isinstance(value, list):
            return [process(v, type) for v in value]
        
        if type.is_primitive:
            return primitive_value(type, value)
        elif isinstance(value, dict):
            #@@ value should not be multi-level dict
            name = value.pop('name')
            process_all(value, type)
            t = db.new_version(get_thing(), name, type, value)
            t.save()
            return t
        elif isinstance(value, tdb.Thing):
            return value
        else:
            return db.get_version(parent, value)
            
    def process_all(d, type):
        for p in type.properties:
            if p.name in d:
                _check_unique(p.unique, d[p.name])
                d[p.name] = process(d[p.name], p.d.type)
            else:
                if p.unique:
                    d[p.name] = default_value(p)
                else:
                    d[p.name] = []
                    
    process_all(d, type)
    return db.new_version(parent, name, type, d)

def thingtidy(thing):
    for p in thing.type.properties:
        if p.name not in thing.d:
            if p.unique:
                thing.d[p.name] = default_value(p)
            else:
                thing.d[p.name] = []
        else:
            # correct the case: expecting atom, found list
            if p.unique and isinstance(thing.d[p.name], list):
                thing.d[p.name] = web.listget(thing.d[p.name], default_value(p.type))

            # correct the case: expecting list, found atom
            if not p.unique and not isinstance(thing.d[p.name], list):
                thing.d[p.name] = [thing.d[p.name]]
                
    for r in thing.type.get('backreferences', []):
        q = {'type': r.d.type, r.d.property_name: thing}
        thing.d[r.name] = tdb.Things(limit=20, **q).list()
        
def _check_unique(unique, value):
    pass
        
def primitive_value(type, value):
    def xbool(v):
        return str(v).lower() != 'false'

    d = {
        'type/int': int,
        'type/string': str,
        'type/text': str,
        'type/boolean': xbool,
    }
               
    if type.name in d:
        return d[type.name](value)
    else:
        return value

def default_value(type):
    d = {
        'type/int': 0,
        'type/boolean': False
    }
    return d.get(type.name, '')

class DefaultThing:
    def __init__(self, type):
        self.name = ""
        self.type = type
        self.d = DefaultThingData(type)
        
    def __getattr__(self, key):
        if key in self.__dict__:
            return self.__dict__[key]
        else:
            return getattr(self.d, key)
            
class DefaultThingData:
    def __init__(self, type):
        self.type = type
        self.properties = dict([(p.name, p) for p in type.properties])
        
    def __getattr__(self, key):
        p = self.properties.get(key)
        if p is None:
            raise AttributeError, key
            
        if p.unique:
            if p.type.is_primitive:
                return default_value(p.type)
            else:
                return DefaultThing(p.type)
        else:
            return []            
        
    def __getitem__(self, key):
        try:
            getattr(self, key)
        except AttributeError:
            raise KeyError, key

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default