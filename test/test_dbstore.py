import sys
sys.path.insert(0, '.')

import unittest as webtest
import web
import os

from infogami.infobase import dbstore, infobase, common

class InfobaseTestCase(webtest.TestCase):
    def setUp(self):
        user = os.getenv('USER')


        web.config.db_parameters = dict(dbn='postgres', db='infobase_test', user=user, pw='')
        store = dbstore.DBStore(dbstore.Schema())
        self.t = store.db.transaction()
        store.db.printing = False

        self.ib = infobase.Infobase(store, 'secret')
        self.site = self.ib.create('test')

    def tearDown(self):
        self.t.rollback()

    def get_site_store(self):
        return self.ib.get('test')

class DBStoreTest(InfobaseTestCase):
    def testAdd(self):
        self.assertEquals(1+1, 2)

    def _test_save(self):
        store = self.get_site_store()

        d = dict(key='/x', type={'key': '/type/type'}, title='foo', x={'x': 1, 'y': 'foo'})
        store.save('/x', d)

        d = store.get('/x')._get_data()
        print d

        del d['title']
        d['body'] = 'bar'
        store.save('/x', d)

        print store.get('/x')._get_data()

class SaveTest(InfobaseTestCase):
    def testSave(self):
        d = dict(key='/foo', type='/type/object')
        assert self.site.save('/foo', d) == {'key': '/foo', 'revision': 1}

        d = dict(key='/foo', type='/type/object', x=1)
        assert self.site.save('/foo', d) == {'key': '/foo', 'revision': 2}
    
    def new(self, error=None, **d):
        try:
            key = d['key']
            self.assertEquals(self.site.save(key, d), {'key': key, 'revision': 1})
        except common.InfobaseException, e:
            self.assertEquals(str(e), error)
    
    def test_type(self):
        self.new(key='/a', type='/type/object')
        self.new(key='/b', type={'key': '/type/object'})
        self.new(key='/c', type='/type/noobject', error="Not Found: '/type/noobject'")
            
    def test_expected_type(self):
        def p(name, expected_type, unique=True):
            return locals()
        self.new(key='/type/test', type='/type/type', properties=[p('i', '/type/int'), p('s', '/type/string'), p('f', '/type/float'), p('t', '/type/type')])

        self.new(key='/a', type='/type/test', i='1', f='1.2', t='/type/test')
        self.new(key='/b', type='/type/test', i={'type': '/type/int', 'value': '1'}, f='1.2', t={'key': '/type/test'})
        self.new(key='/e1', type='/type/test', i='bad integer', error="invalid literal for int() with base 10: 'bad integer'")        

if __name__ == "__main__":
    webtest.main()
