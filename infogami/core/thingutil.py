from infogami import tdb
import db
import web

def get_site(thing):
    """Returns the site in which the given thing is part of."""
    # parent of site is tdb.root
    if thing.parent == tdb.root:
        return thing
    else:
        return get_site(thing.parent)

def thingtidy(thing, fill_missing=True):
    """Tidy a thing by filling missing properties, filling backreferences etc."""
    def strip_underscore(d):
        for k in d.keys():
            if k.startswith('_'):
                del d[k]
                    
    def new_child(d, type):
        """Create a child thing using d as data."""
        name = d.pop('name')
        child = db.new_version(thing, name, type, d)
        thingtidy(child, fill_missing=fill_missing)
        return child

    def process_property(value, type):
        if isinstance(value, list):
            return [process_property(v, type) for v in value]
        elif type.is_primitive:
            return primitive_value(type, value)
        elif isinstance(value, dict):
            return new_child(value, type)
        elif isinstance(value, (tdb.Thing, DefaultThing)):
            return value
        elif isinstance(value, str):
            # Name is found when a thing is expected. 
            # Replacing that with a thing of that name.
            return db.get_version(get_site(thing), value)
        else:
            raise Exception, "huh?"

    def process_all_properties(d, type):
        for p in type.properties:
            if p.name in d:
                d[p.name] = process_property(d[p.name], p.d.type)

    def fill_missing_properties():
        for p in thing.type.properties:
            unique = p.d.get('unique', False)
            if p.name not in thing.d:
                if unique:
                    thing.d[p.name] = default_value(p)
                else:
                    thing.d[p.name] = []
            else:
                # correct the case where atom is extected and list is found.
                if unique and isinstance(thing.d[p.name], list):
                    thing.d[p.name] = web.listget(thing.d[p.name], 0, default_value(p.type))

                # correct the case where list is extected and atom is found.
                if not unique and not isinstance(thing.d[p.name], list):
                    thing.d[p.name] = [thing.d[p.name]]
                    
    def fill_backreferences():
        for r in thing.type.get('backreferences', []):
            q = {'type': r.d.type, r.d.property_name: thing}
            thing.d[r.name] = tdb.Things(limit=20, **q).list()

    strip_underscore(thing.d)
    if fill_missing:
        fill_missing_properties()
    process_all_properties(thing.d, thing.type)
    
    if fill_missing:
        fill_backreferences()
        
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