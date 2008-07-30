"""
Infobase: structured database.

Infobase contains multiple sites and each site can store any number of objects. 
Each object has a key, that is unique to the site it belongs.
"""
import web

import common
import readquery
import writequery

class Infobase:
    def __init__(self, store):
        self.store = store
    
    def get(self, key, revision=None):
        thing = self.store.get(key, revision)
        print >> web.debug, 'get', key, revision, thing
        return thing
        
    withKey = get
        
    def write(self, query, timestamp, comment=None, machine_comment=None, ip=None, author=None):
        q = writequery.make_query(self.store, query)
        return self.store.write(q, timestamp=timestamp, comment=comment, machine_comment=machine_comment, ip=ip, author=author)
        
    def things(self, query):
        q = readquery.make_query(self.store, query)
        return self.store.things(q)
        
    def versions(self, query):
        raise NotImplementedError
