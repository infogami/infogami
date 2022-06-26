import unittest

import web

from infogami.infobase import server
from infogami.infobase.tests import utils


def setup_module(mod):
    utils.setup_site(mod)
    mod.app = server.app

    # overwrite _cleanup to make it possible to have transactions spanning multiple requests.
    mod.app.do_cleanup = mod.app._cleanup
    mod.app._cleanup = lambda: None


def reset():
    site.cache.clear()


def teardown_module(mod):
    utils.teardown_site(mod)


def subdict(d, keys):
    """Returns a subset of a dictionary.
    >>> subdict({'a': 1, 'b': 2}, ['a'])
    {'a': 1}
    """
    return {k: d[k] for k in keys}


class DBTest(unittest.TestCase):
    def setUp(self):
        global db
        self.t = db.transaction()
        # important to clear the caches
        site.store.cache.clear()
        site.store.property_manager.reset()

        web.ctx.pop("infobase_auth_token", None)

    def tearDown(self):
        self.t.rollback()

    def create_user(self, username, email, password, bot=False, data={}):
        site.account_manager.register(username, email, password, data, _activate=True)
        site.account_manager.update(username, bot=bot)

    def login(self, username, password):
        user = site.account_manager.login(username, password)
        # don't pollute global state
        web.ctx.infobase_auth_token = None
        return bool(user)


class TestInfobase(DBTest):
    global site

    def test_save(self):
        # save an object and make sure revision==1
        d = site.save('/foo', {'key': '/foo', 'type': '/type/object', 'n': 1, 'p': 'q'})
        assert d['revision'] == 1

        # save again without any change in data and make sure new revision is not added.
        reset()
        d = site.save('/foo', {'key': '/foo', 'type': '/type/object', 'n': 1, 'p': 'q'})
        assert d == {}

        # now save with some change and make sure new revision is created
        reset()
        d = site.save(
            '/foo', {'key': '/foo', 'type': '/type/object', 'n': 1, 'p': 'qq'}
        )
        assert d['revision'] == 2

    def test_versions(self):
        site.save('/foo', {'key': '/foo', 'type': '/type/object'}, comment='test 1')
        site.save('/bar', {'key': '/bar', 'type': '/type/object'}, comment='test 2')
        site.save(
            '/foo', {'key': '/foo', 'type': '/type/object', 'x': 1}, comment='test 3'
        )

        def versions(q):
            return [
                subdict(v, ['key', 'revision', 'comment']) for v in site.versions(q)
            ]

        assert versions({'limit': 3}) == [
            {'key': '/foo', 'revision': 2, 'comment': 'test 3'},
            {'key': '/bar', 'revision': 1, 'comment': 'test 2'},
            {'key': '/foo', 'revision': 1, 'comment': 'test 1'},
        ]

        self.create_user(
            'test', 'testt@example.com', 'test123', data={'displayname': 'Test'}
        )
        assert site._get_thing('/user/test')

        site.save(
            '/foo',
            {'key': '/foo', 'type': '/type/object', 'x': 2},
            comment='test 4',
            ip='1.2.3.4',
            author=site._get_thing('/user/test'),
        )

        assert versions({'author': '/user/test'})[:-3] == [
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
        self.create_user(
            'TestBot',
            'testbot@example.com',
            'test123',
            bot=True,
            data={'displayname': 'Test Bot'},
        )

        site.save(
            '/a', {'key': '/a', 'type': '/type/object'}, ip='1.2.3.4', comment='notbot'
        )
        site.save(
            '/b',
            {'key': '/b', 'type': '/type/object'},
            ip='1.2.3.4',
            comment='bot',
            author=site._get_thing('/user/TestBot'),
        )

        def f(q):
            return [v['key'] for v in site.versions(q)]

        assert f({'ip': '1.2.3.4'}) == ['/b', '/a']
        assert f({'ip': '1.2.3.4', 'bot': False}) == ['/a']
        assert f({'ip': '1.2.3.4', 'bot': True}) == ['/b']

    def test_property_cache(self):
        # Make sure a failed save_many query doesn't pollute property cache
        q = [
            {'key': '/a', 'type': '/type/object', 'a': 1},
            {'key': '/b', 'type': '/type/object', 'bad property': 1},
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
        assert site.things({'type': {'key': '/type/object'}}) == [
            {'key': '/a'},
            {'key': '/b'},
        ]

        assert site.things({'type': '/type/object', 'sort': 'created'}) == [
            {'key': '/a'},
            {'key': '/b'},
        ]
        assert site.things({'type': '/type/object', 'sort': '-created'}) == [
            {'key': '/b'},
            {'key': '/a'},
        ]

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
        site.save(
            '/a',
            {
                'key': '/a',
                'type': '/type/object',
                'links': [
                    {'name': 'x', 'url': 'http://example.com/x'},
                    {'name': 'y', 'url': 'http://example.com/y1'},
                ],
            },
        )

        site.save(
            '/b',
            {
                'key': '/b',
                'type': '/type/object',
                'links': [
                    {'name': 'y', 'url': 'http://example.com/y2'},
                    {'name': 'z', 'url': 'http://example.com/z'},
                ],
            },
        )

        site.things({'type': '/type/object', 'links.name': 'x'}) == [{'key': '/a'}]
        site.things({'type': '/type/object', 'links.name': 'y'}) == [
            {'key': '/a'},
            {'key': '/b'},
        ]
        site.things({'type': '/type/object', 'links.name': 'z'}) == [{'key': '/b'}]

        site.things(
            {
                'type': '/type/object',
                'links': {'name': 'x', 'url': 'http://example.com/y1'},
            }
        ) == [{'key': '/a'}]

        site.things({'type': '/type/object', 'links': {'name': 'x'}}) == [{'key': '/a'}]
        site.things({'type': '/type/object', 'links': {'name': 'y'}}) == [
            {'key': '/a'},
            {'key': '/b'},
        ]
        site.things({'type': '/type/object', 'links': {'name': 'z'}}) == [{'key': '/b'}]
