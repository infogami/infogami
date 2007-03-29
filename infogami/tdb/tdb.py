import web

class NotFound(Exception): pass

class Thing:
    @staticmethod
    def _reserved(attr):
        return attr.startswith('_') or attr in [
          'id', 'parent_id', 'parent', 'name', 'type_id', 'type', 'v', 'h', 'd', 'latest', 'versions', 'save']
    
    def __init__(self, id, name, parent_id, type_id, d, v):
        self.id, self.name, self.parent_id, self.type_id, self.d, self.v = \
            id and int(id), name, parent_id, type_id, d, v
        self.parent = LazyThing(parent_id)
        self.type = LazyThing(type_id)
        self.h = (self.id and History(self.id)) or None
        self._dirty = False
    
    def __repr__(self):
        return '<Thing "%s" at %s>' % (self.name, self.id)

    def __str__(self): return '<Thing "%s" with %s>' % (self.name, self.d)
    
    def __cmp__(self, other):
        return cmp(self.id, other.id)

    def __eq__(self, other):
        return self.id == other.id and self.name == other.name and self.d == other.d

    def __ne__(self, other):
        return not (self == other)
    
    def __getattr__(self, attr):
        if not Thing._reserved(attr) and self.d.has_key(attr):
            return self.d[attr]
        raise AttributeError, attr
    
    def __setattr__(self, attr, value):
        if Thing._reserved(attr):
            self.__dict__[attr] = value
            
            # type and type_id must always be in sync.
            if attr == 'type':
                self.__dict__['type_id'] = self.type.id
                self._dirty = True
            elif attr == 'type_id':
                self.__dict__['type'] = LazyThing(self.type_id)
                self._dirty = True
        else:
            self.d[attr] = value
            self._dirty = True
    
    def save(self, comment='', author_id=None, ip=None):
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
            tid = web.insert('thing', name=self.name, parent_id=self.parent_id)
        else:
            tid = self.id
        vid = web.insert('version', thing_id=tid, comment=comment, author_id=author_id, ip=ip)
        web.query('UPDATE version SET revision=(SELECT max(revision)+1 \
                   FROM version WHERE thing_id=$tid) WHERE id=$vid', 
                   vars=locals())
        for k, v in self.d.items():
            if isinstance(v, list):
                for n, item in enumerate(v):
                    savedatum(vid, k, item, n)
            else:
                savedatum(vid, k, v)
        savedatum(vid, '__type__', LazyThing(self.type_id))
        web.update('thing', latest_version_id=vid, where="thing.id = $tid", vars=locals())
        web.commit()
        self.id = tid
        self.v = LazyVersion(vid)
        self.h = History(self.id)
        self._dirty = False

class LazyThing(Thing):
    def __init__(self, id, revision=None):
        self.id = int(id)
        self._revision = revision

    def __getattr__(self, attr):
        if attr in ['id', '_revision']:
            return self.__dict__[attr]
        elif attr.startswith('__'):
            Thing.__getattr__(self, attr)
        else:
            id, name, parent_id, type_id, d, v = withID(self.id, self._revision, raw=True)
            Thing.__init__(self, id, name, parent_id, type_id, d, v)
            self.__class__ = Thing
            return getattr(self, attr)
            
class Version:
    def __init__(self, id, thing_id, revision, author_id, ip, comment, created):
        web.autoassign(self, locals())
        self.thing = LazyThing(thing_id, revision)
        self.author = (author_id and LazyThing(author_id)) or None
        
    def __eq__(self, other):
        return self.id == other.id
        
    def __ne__(self, other):
        return not (self == other)
    
    def __repr__(self): 
        return '<Version %s@%s at %s>' % (self.thing_id, self.revision, self.id)

class LazyVersion(Version):
    def __init__(self, id):
        self.id = int(id)
        
    def __getattr__(self, attr):
        if attr.startswith('__') or attr == 'id':
            Version.__getattr__(self, attr)
        else:
            v = web.select('version', where='id=$self.id', vars=locals())[0]
            Version.__init__(self, **v)
            self.__class__ = Version
            return getattr(self, attr)

def new(name, parent_id, type_id, d=None):
    if d == None: d = {}
    t = Thing(None, name, parent_id, type_id, d, None)
    t._dirty = True
    return t

def withID(id, revision=None, raw=False):
    try:
        t = web.select('thing', where="thing.id = $id", vars=locals())[0]
        if revision is None:
            v = web.select('version', 
                where='version.id = $t.latest_version_id',
                vars=locals())[0]
        else:
            v = web.select('version', 
                where='version.thing_id = $id AND version.revision = $revision', 
                vars=locals())[0]
        v = Version(**v)             
        data = web.select('datum', 
                where="version_id = $v.id", 
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
        
        type = d.pop('__type__')
        if raw:
            return id, t.name, t.parent_id, type.id, d, v
        else:
            return Thing(id, t.name, t.parent_id, type.id, d, v)
    except IndexError:
        raise NotFound, id

def withName(name, parent_id):
    try:
        id = web.select('thing', where='parent_id = $parent_id AND name = $name', vars=locals())[0].id
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

class Versions:
    def __init__(self, **query):
        self.query = query
        self.versions = None
    
    def init(self):
        where = '1 = 1'
        for k, v in self.query.items():
            where += web.reparam(' AND %s = $v' % (k,), locals())
        self.versions = [Version(**v) for v in web.select('version', where=where, order='id desc')]
        
    def __getitem__(self, index):
        if self.versions is None:
            self.init()
        return self.versions[index]
    
    def __len__(self):
        if self.versions is None:
            self.init()
        return len(self.versions)
        
    def __str__(self):
        return str(self.versions)

class History(Versions):
    def __init__(self, thing_id):
        Versions.__init__(self, thing_id=thing_id)

metatype = LazyThing(1)
usertype = LazyThing(2)

def setup():
    try:
       withID(1)
    except NotFound:
        # create metatype and user type
        new("metatype", 1, 1).save()
        new("user", 1, 1).save()
