"""
TDB Log parser.
"""

import tdb
import time

_impl = None

def tdbimpl():
    if _impl is None:
        _impl = tdb.CachedTDBImpl()
    return _impl

def parse(filename, infinite=False):
    fd = open(filename)
    return parse1(fd, infinite)

def parse1(fd, infinite=False):
    """Parses a tdb log file and returns an iteratable over the contents.
    If argument 'infinite' is true, the iterable never terminates.
    It instead expects the file to keep growing as new log records
    arrive, so on reaching end of file it blocks until more data
    becomes available.   If 'infinite' is false, generator terminates
    when it reaches end of log file.
    """
    if not infinite and fd.tell() != 0:
        raise NotImplementedError, "can't seek in non-tailing logfile"

    def parse_items():
        """Parses the file and returns an iteratable over the items."""
        lines = []

        def infinite_lines(fd):
            def charstream(fd):
                # generate a sequence of the lines in fd, never
                # terminating.  On reaching end of fd, 
                # sleep til more characters are available.
                while True:
                    c = fd.read(1)
                    if c=='': time.sleep(1)
                    else: yield c
            while True:
                yield ''.join(iter(charstream(fd).next, '\n'))

        if infinite:
            xlines = infinite_lines(fd)
        else:
            xlines = (x.strip() for x in fd.xreadlines())
        
        for line in xlines:
            if line == "":
                yield lines
                lines = []
            else:
                lines.append(line)

    class LazyThing(tdb.LazyThing):
        def __init__(self, id):
            tdb.LazyThing.__init__(self, lambda: tdbimpl().withID(id), id=id)

        def __repr__(self):
            return 't' + str(self.id)

    class env(dict):
        def __getitem__(self, name):
            """Returns LazyThing(xx) for key txx"""
            if name.startswith('t'):
                return LazyThing(int(name[1:]))
            else:
                raise KeyError, name

    # dirty hack to decode the value using eval
    def decode(value):
        return eval(value, env())
                        
    def parse_data(lines):
        """Parses each line containing name-value pair and 
        returns the result as a dictionary."""
        from logger import _keydecode
        d = {}
        for line in lines:
            name, value = line.split(":", 1)
            name = _keydecode(name)
            d[name] = decode(value)
        return d
        
    for item in parse_items():
        key, id = item[0].split()
        data = parse_data(item[1:])
        yield key, id, data

def parse2(p1):
    from tdb import Thing

    while 1:
        thing = p1.next()
        version = p1.next()
        data = p1.next()

        yield Thing(tdbimpl(), 
                id=thing[1], 
                name=thing[2]['name'],
                parent=tdbimpl().withID(thing[2]['parent_id'], lazy=True),
                latest_revision=0,
                v=None,
                type=data[2].pop('__type__'), 
                d=data[2])
        
def parse2a(p1):
    """Generate sequence of things retrieved from tdb, given a parsed logfile
    stream (from logger.parse) as input"""
    from tdb import withID
    
    while 1:
        x = p1.next()
        if x[0] != 'version': continue
        yield withID(x[2]['thing_id'])

def parse2b(p1):
    from tdb import Thing
    
    while 1:
        x = p1.next()
        
        if x[0] == 'thing':
            thing = x
            version = p1.next()
            data = p1.next()
            
            yield Thing(tdbimpl(), 
                    id=thing[1], 
                    name=thing[2]['name'],
                    parent=tdbimpl().withID(thing[2]['parent_id'], lazy=True),
                    latest_revision=None,
                    v=None,
                    type=data[2].pop('__type__'), 
                    d=data[2])
        elif x[0] == 'version':
            yield tdbimpl().withID(x[2]['thing_id'])
        else:
            raise ValueError, "I wasn't expecting that..."

def load(filename):
    """Loads a tdb log file into database."""

    import web, tdb
    # assumes web.load is already called
    web.transact()
    for key, id, data in parse(filename):
        if key == 'thing':
            web.insert('thing', seqname=False, id=id, **data)
        elif key == 'version':
            tid = data['thing_id']
            web.insert('version', seqname=False, id=id, **data)
            web.update('thing', where='id=$tid', latest_revision=data['revision'], vars=locals())
        elif key == 'data':
            vid = id
            for k, v in data.items():
                tdb.SimpleTDBImpl.savedatum(vid, k, v)
    web.commit()
