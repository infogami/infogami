import web

class NotFound(Exception): pass

class Thing:
    @staticmethod
    def _reserved(attr):
        return attr.startswith('_') or attr in [
          'id', 'name', 'd', 'latest', 'versions', 'save']
    
    def __init__(self, id, name, d):
        self.id, self.name, self.d = id and int(id), name, d
        self._dirty = False
    
    def __repr__(self):
        return '<Thing "%s" at %s>' % (self.name, self.id)
    
    def __cmp__(self, other):
        return cmp(self.id, other.id)
    
    def __getattr__(self, attr):
        if not Thing._reserved(attr) and self.d.has_key(attr):
            return self.d[attr]
        raise AttributeError, attr
    
    def __setattr__(self, attr, value):
        if Thing._reserved(attr):
            self.__dict__[attr] = value
        else:
            self.d[attr] = value
            self._dirty = True
    
    def save(self, comment):
        def savedatum(vid, key, value, ordering=None):
            if isinstance(value, str):
                dt = 0
            elif isinstance(value, Thing):
                dt = 1
                value = value.id
            elif isinstance(value, int):
                dt = 2
            elif isinstance(value, float):
                dt = 3
            web.insert('datum', False, 
              version_id=vid, key=key, value=value, data_type=dt, ordering=ordering)
        
        web.transact()
        if self.id is None:
            tid = web.insert('thing', name=self.name)
        else:
            tid = self.id
        vid = web.insert('version', thing_id=tid, comment=comment) #@@revision, author
        for k, v in self.d.items():
            if isinstance(v, list):
                for n, item in enumerate(v):
                    savedatum(vid, k, item, n)
            else:
                savedatum(vid, k, v)
        web.update('thing', latest_version_id=vid, where="thing.id = $tid", vars=locals())
        web.commit()
        self.id = tid
        self._dirty = False

class LazyThing(Thing):
    def __init__(self, id):
        self.id = int(id)

    def __getattr__(self, attr):
        id, name, d = withID(self.id, raw=True)
        Thing.__init__(self, id, name, d)
        self.__class__ = Thing
        return getattr(self, attr)

def new(name, d=None):
    if d == None: d = {}
    t = Thing(None, name, d)
    t._dirty = True
    return t

def withID(id, raw=False):
    try:
        thing_info = web.select('thing', where="thing.id = $id", vars=locals())[0]        
        data = web.select('datum', 
          where="version_id = $thing_info.latest_version_id", 
          order="key ASC, ordering ASC",
          vars=locals())
        d = {}
        for r in data:
            value = r.value
            if r.data_type == 0:
                pass # already a string
            elif r.data_type == 1:
                value = LazyThing(int(value))
            elif r.data_type == 2:
                value = int(value)
            elif r.data_type == 3:
                value = float(value)
            
            if r.ordering is not None:
                d.setdefault(r.key, []).append(value)
            else:
                d[r.key] = value
        if raw:
            return id, thing_info.name, d
        else:
            return Thing(id, thing_info.name, d)
    except IndexError:
        raise NotFound, id

def withName(name):
    try:
        id = web.select('thing', where='name = $name', vars=locals())[0].id
        return withID(id)
    except IndexError:
        raise NotFound, name

class Things:
    def __init__(self, **query):
        what = ['thing']
        n = 0
        where = "1=1"
        
        for k, v in query.items():
            n += 1
            what.append('datum AS d%s' % n)
            where += ' AND d%s.version_id = thing.latest_version_id AND ' % n + \
              web.reparam('d%s.key = $k AND d%s.value = $v' % (n, n), locals())
        
        self.values = [r.id for r in web.select(what, where=where)]
    
    def __iter__(self):
        for item in self.values:
            yield withID(item)
    
    def list(self):
        return list(self)