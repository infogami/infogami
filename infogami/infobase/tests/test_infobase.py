import os
import simplejson

import py.test

import web
from infogami.infobase import config, dbstore, infobase, server

def _create_site(name):
    schema = dbstore.default_schema or dbstore.Schema()
    store = dbstore.DBStore(schema)
    _infobase = infobase.Infobase(store, config.secret_key)
    return _infobase.create(name)

def setup_module(mod):
    os.system('dropdb infobase_test; createdb infobase_test')
    web.config.db_parameters = dict(dbn='postgres', db='infobase_test', user=os.getenv('USER'), pw='')    
    mod.site = _create_site('test')
    mod.db = mod.site.store.db
    mod.app = server.app
    
    # overwrite _cleanup to make it possible to have transactions spanning multiple requests.
    mod.app.do_cleanup = mod.app._cleanup
    mod.app._cleanup = lambda: None
    
def subdict(d, keys):
    """Returns a subset of a dictionary.
        >>> subdict({'a': 1, 'b': 2}, ['a'])
        {'a': 1}
    """
    return dict((k, d[k]) for k in keys)
    
import unittest
class DBTest(unittest.TestCase):
    def setUp(self):
        self.t = db.transaction()
        # important to clear the caches
        site.store.cache.clear()
        site.store.property_id_cache.clear()
        
    def tearDown(self):
        self.t.rollback()
        
    def create_user(self, username, email, password, data={}):
        site.account_manager.register(username, email, password, data)
        # register does automatic login. Undo that.
        web.ctx.infobase_auth_token = None
        
    def login(self, username, password):
        user = site.account_manager.login(username, password)
        # don't pollute global state
        web.ctx.infobase_auth_token = None
        return bool(user)
        
class TestInfobase(DBTest):
    def test_save(self):
        # save an object and make sure revision==1
        d = site.save('/foo', {'key': '/foo', 'type': '/type/object', 'n': 1, 'p': 'q'})
        assert d == {'key': '/foo', 'revision': 1}

        # save again without any change in data and make sure new revision is not added.
        d = site.save('/foo', {'key': '/foo', 'type': '/type/object', 'n': 1, 'p': 'q'})
        assert d == {}

        # now save with some change and make sure new revision is created
        d = site.save('/foo', {'key': '/foo', 'type': '/type/object', 'n': 1, 'p': 'qq'})
        assert d == {'key': '/foo', 'revision': 2}
                
    def test_versions(self):
        d1 = site.save('/foo', {'key': '/foo', 'type': '/type/object'}, comment='test 1')
        d2 = site.save('/bar', {'key': '/bar', 'type': '/type/object'}, comment='test 2')
        d3 = site.save('/foo', {'key': '/foo', 'type': '/type/object', 'x': 1}, comment='test 3')
        
        assert d1 == {'key': '/foo', 'revision': 1}
        
        def versions(q):
            return [subdict(v, ['key', 'revision', 'comment']) for v in site.versions(q)]
            
        assert versions({'limit': 3}) == [
            {'key': '/foo', 'revision': 2, 'comment': 'test 3'},
            {'key': '/bar', 'revision': 1, 'comment': 'test 2'},
            {'key': '/foo', 'revision': 1, 'comment': 'test 1'},
        ]
        
        self.create_user('test', 'testt@example.com', 'test123', data={'displayname': 'Test'})
        site.save('/foo', {'key': '/foo', 'type': '/type/object', 'x': 2}, comment='test 4', ip='1.2.3.4', author=site.get('/user/test'))
        
        assert versions({'author': '/user/test'}) == [
            {'key': '/foo', 'revision': 3, 'comment': 'test 4'}
        ]

        assert versions({'ip': '1.2.3.4'}) == [
            {'key': '/foo', 'revision': 3, 'comment': 'test 4'}
        ]
        
        # should return empty result for bad queries
        assert versions({'bad': 1}) == []

        assert versions({'author': '/user/noone'}) == []
        
    def test_versions_by_bot(self):
        # create user TestBot and mark him as bot
        self.create_user('TestBot', 'testbot@example.com', 'test123', data={'displayname': 'Test Bot'})
        testbot_id = db.where('thing', key='/user/TestBot')[0].id
        db.update('account', where='thing_id=$testbot_id', bot=True, vars=locals())
        
        site.save('/a', {'key': '/a', 'type': '/type/object'}, ip='1.2.3.4', comment='notbot')
        site.save('/b', {'key': '/b', 'type': '/type/object'}, ip='1.2.3.4', comment='bot', author=site.get('/user/TestBot'))
        
        def f(q):
            return [v['key'] for v in site.versions(q)]
        
        assert f({'ip': '1.2.3.4'}) == ['/b', '/a']
        assert f({'ip': '1.2.3.4', 'bot': False}) == ['/a']
        assert f({'ip': '1.2.3.4', 'bot': True}) == ['/b']
        
    def test_ban_user(self):
        # create user and verify login
        self.create_user('TestUser', 'testuser@example.com', 'test123', data={'displayname': 'Test User'})
        assert self.login('TestUser', 'test123') == True
        
        # ban the user
        id = db.where('thing', key='/user/TestUser')[0].id
        db.update('account', where='thing_id=$id', active=False, vars=locals())
        
        # make sure he can't login
        assert self.login('TestUser', 'test123') == False
        
    def test_property_cache(self):
        # Make sure a failed save_many query doesn't pollute property cache
        q = [
            {'key': '/a', 'type': '/type/object', 'a': 1},
            {'key': '/b', 'type': '/type/object', 'bad property': 1}
        ]
        try:
            site.save_many(q)
        except Exception:
            pass

        q = [
            {'key': '/a', 'type': '/type/object', 'a': 1},
        ]
        site.save_many(q)
        
    def test_things(self):
        site.save('/a', {'key': '/a', 'type': '/type/object', 'x': 1, 'name': 'a'})
        site.save('/b', {'key': '/b', 'type': '/type/object', 'x': 2, 'name': 'b'})
        
        assert site.things({'type': '/type/object'}) == [{'key': '/a'}, {'key': '/b'}]
        assert site.things({'type': {'key': '/type/object'}}) == [{'key': '/a'}, {'key': '/b'}]
        
        assert site.things({'type': '/type/object', 'sort': 'created'}) == [{'key': '/a'}, {'key': '/b'}]
        assert site.things({'type': '/type/object', 'sort': '-created'}) == [{'key': '/b'}, {'key': '/a'}]
        
        assert site.things({'type': '/type/object', 'x': 1}) == [{'key': '/a'}]
        assert site.things({'type': '/type/object', 'x': '1'}) == []
        
        assert site.things({'type': '/type/object', 'name': 'a'}) == [{'key': '/a'}]

        # should return empty result when queried with non-existing or bad property
        assert site.things({'type': '/type/object', 'foo': 'bar'}) == []
        assert site.things({'type': '/type/object', 'bad property': 'bar'}) == []

        # should return empty result when queried for non-existing objects
        assert site.things({'type': '/type/object', 'foo': {'key': '/foo'}}) == []
        assert site.things({'type': '/type/bad'}) == []
        
    def test_nested_things(self):
        if not py.test.config.getvalue('runall'):
            py.test.skip("this is marked as failing, use --runall to run this.")

        site.save('/a', {
            'key': '/a', 
            'type': '/type/object',
            'links': [{
                'name': 'x',
                'url': 'http://example.com/x'
            },
            {
                'name': 'y',
                'url': 'http://example.com/y1'
            }]
        })

        site.save('/b', {
            'key': '/b', 
            'type': '/type/object',
            'links': [{
                'name': 'y',
                'url': 'http://example.com/y2'
            },
            {
                'name': 'z',
                'url': 'http://example.com/z'
            }]
        })
        
        site.things({'type': '/type/object', 'links.name': 'x'}) == [{'key': '/a'}]
        site.things({'type': '/type/object', 'links.name': 'y'}) == [{'key': '/a'}, {'key': '/b'}]
        site.things({'type': '/type/object', 'links.name': 'z'}) == [{'key': '/b'}]

        site.things({'type': '/type/object', 'links': {'name': 'x', 'url': 'http://example.com/y1'}}) == [{'key': '/a'}]

        site.things({'type': '/type/object', 'links': {'name': 'x'}}) == [{'key': '/a'}]
        site.things({'type': '/type/object', 'links': {'name': 'y'}}) == [{'key': '/a'}, {'key': '/b'}]
        site.things({'type': '/type/object', 'links': {'name': 'z'}}) == [{'key': '/b'}]

class TestServer(DBTest):
    def test_home(self):
        b = app.browser()
        b.open('/')
        assert simplejson.loads(b.data) == {"infobase": "welcome", "version": "0.5dev"}
    
