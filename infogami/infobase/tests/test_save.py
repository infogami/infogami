from infogami.infobase import dbstore
from infogami.infobase._dbstore.save import SaveImpl

import web
import simplejson
import os
import datetime
import unittest

def setup_module(mod):
    utils.setup_db(mod)
    
def teardown_module(mod):
    utils.teardown_db(mod)

class DBTest(unittest.TestCase):
    def setUp(self):
        self.tx = db.transaction()
        db.insert("thing", key='/type/object')
        
    def tearDown(self):
        self.tx.rollback()
        
def update_doc(doc, revision, created, last_modified):
    """Add revision, latest_revision, created and latest_revision properties to the given doc.
    """    
    last_modified_repr = {"type": "/type/datetime", "value": last_modified.isoformat()}
    created_repr = {"type": "/type/datetime", "value": created.isoformat()}
    
    return dict(doc, 
        revision=revision,
        latest_revision=revision,
        created=created_repr,
        last_modified=last_modified_repr)

def assert_record(record, doc, revision, created, timestamp):
    d = update_doc(doc, revision, created, timestamp)
    print 'assert_record', d
    assert record.data == d
    
    assert record.key == doc['key']
    assert record.created == created
    assert record.last_modified == timestamp
    assert record.revision == revision
    
    if revision == 1:
        assert record.id is None
        assert record.prev.data is None
    else:
        assert record.id is not None
        assert record.prev.data is not None

class Test_get_records_for_save(DBTest):
    """Tests for _dbstore_save._get_records_for_save.
    """
    def test_new(self):
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 01, 01, 01, 01, 01)

        a = {"key": "/a", "type": {"key": "/type/object"}, "title": "a"}
        b = {"key": "/b", "type": {"key": "/type/object"}, "title": "b"}
        
        docs = [a, b]
        records = s._get_records_for_save(docs, timestamp)
        
        assert len(records) == 2
        assert_record(records[0], docs[0], 1, timestamp, timestamp)
        assert_record(records[1], docs[1], 1, timestamp, timestamp)
        
    def test_existing(self):
        def insert(doc, revision, created, last_modified):
            id =  db.insert('thing', key=doc['key'], latest_revision=revision, created=created, last_modified=last_modified)
            db.insert('data', seqname=False, thing_id=id, revision=revision, data=simplejson.dumps(doc))
        
        created = datetime.datetime(2010, 01, 01, 01, 01, 01)            
        a = {"key": "/a", "type": {"key": "/type/object"}, "title": "a"}
        insert(a, 1, created, created)

        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 02, 02, 02, 02, 02)            
        records = s._get_records_for_save([a], timestamp)
        
        assert_record(records[0], a, 2, created, timestamp)
        
class Test_save(DBTest):        
    def get_json(self, key):
        d = db.query("SELECT data.data FROM thing, data WHERE data.thing_id=thing.id AND data.revision = thing.latest_revision AND thing.key = '/a'")
        return simplejson.loads(d[0].data)
        
    def test_save(self):
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 01, 01, 01, 01, 01)
        a = {"key": "/a", "type": {"key": "/type/object"}, "title": "a"}
        
        status = s.save([a], 
                    timestamp=timestamp, 
                    ip="1.2.3.4",
                    author=None, 
                    comment="Testing create.", 
                    action="save")
                    
        assert status == [{"key": "/a", "revision": 1}]
        assert self.get_json('/a') == update_doc(a, 1, timestamp, timestamp) 
        
        a['title'] = 'b'
        timestamp2 = datetime.datetime(2010, 02, 02, 02, 02, 02) 
        status = s.save([a], 
                    timestamp=timestamp2, 
                    ip="1.2.3.4", 
                    author=None, 
                    comment="Testing update.", 
                    action="save")
        assert status == [{"key": "/a", "revision": 2}]
        assert self.get_json('/a') == update_doc(a, 2, timestamp, timestamp2) 
        
    def test_type_change(self):
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 01, 01, 01, 01, 01)
        a = {"key": "/a", "type": {"key": "/type/object"}, "title": "a"}
        status = s.save([a], 
                    timestamp=timestamp, 
                    ip="1.2.3.4",
                    author=None, 
                    comment="Testing create.", 
                    action="save")
                    
        # insert new type
        type_delete_id = db.insert("thing", key='/type/delete')
        a['type']['key'] = '/type/delete'

        timestamp2 = datetime.datetime(2010, 02, 02, 02, 02, 02) 
        status = s.save([a], 
                    timestamp=timestamp2, 
                    ip="1.2.3.4", 
                    author=None, 
                    comment="Testing type change.", 
                    action="save")
        
        assert status == [{"key": "/a", "revision": 2}]
        assert self.get_json('/a') == update_doc(a, 2, timestamp, timestamp2) 
        
        thing = db.select("thing", where="key='/a'")[0]
        assert thing.type == type_delete_id

    def test_with_author(self):
        pass
        
    def test_versions(self):
        pass