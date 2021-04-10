import unittest
import web
import os
import pytest

from infogami.infobase import dbstore, infobase, common


class InfobaseTestCase(unittest.TestCase):
    def get_site_store(self):
        return self.ib.get('test')


@pytest.fixture(scope="session")
def site():
    # TODO: this does not clear data between tests. Make this work in scope=class
    user = os.getenv('USER')
    web.config.db_parameters = dict(
        host='postgres', dbn='postgres', db='infobase_test', user=user, pw=''
    )
    store = dbstore.DBStore(dbstore.Schema())
    store.db.printing = False
    ib = infobase.Infobase(store, 'secret')
    return ib.create('test')


class DBStoreTest(InfobaseTestCase):
    @pytest.mark.skip(reason="is already skipped with an underscore")
    def _test_save(self):
        store = self.get_site_store()

        d = dict(
            key='/x', type={'key': '/type/type'}, title='foo', x={'x': 1, 'y': 'foo'}
        )
        store.save('/x', d)

        d = store.get('/x')._get_data()

        del d['title']
        d['body'] = 'bar'
        store.save('/x', d)


class TestSaveTest:
    def testSave(self, site):
        d = dict(key='/foo', type='/type/object')
        assert site.save('/foo', d) == {'key': '/foo', 'revision': 1}

        d = dict(key='/foo', type='/type/object', x=1)
        assert site.save('/foo', d) == {'key': '/foo', 'revision': 2}

    def new(self, site, error=None, **d):
        try:
            key = d['key']
            assert site.save(key, d) == {'key': key, 'revision': 1}
        except common.InfobaseException as e:
            assert str(e) == error, (str(e), error)

    def test_type(self, site):
        self.new(site, key='/a', type='/type/object')
        self.new(site, key='/b', type={'key': '/type/object'})
        self.new(
            site,
            key='/c',
            type='/type/noobject',
            error='{"error": "notfound", "key": "/type/noobject", "at": {"key": "/c", "property": "type"}}',
        )

    def test_expected_type(self, site):
        def p(name, expected_type, unique=True):
            return locals()
        self.new(
            site,
            key='/type/test',
            type='/type/type',
            properties=[
                p('i', '/type/int'),
                p('s', '/type/string'),
                p('f', '/type/float'),
                p('t', '/type/type'),
            ],
        )

        self.new(site, key='/aa', type='/type/test', i='1', f='1.2', t='/type/test')
        self.new(
            site,
            key='/bb',
            type='/type/test',
            i={'type': '/type/int', 'value': '1'},
            f='1.2',
            t={'key': '/type/test'},
        )
        self.new(
            site,
            key='/e1',
            type='/type/test',
            i='bad integer',
            error='{"error": "bad_data", "message": "invalid literal for int() with base 10: \'bad integer\'", "at": {"key": "/e1", "property": "i"}, "value": "bad integer"}',
        )

    @pytest.mark.skip(
        reason="d is expected to be json (DBSiteStore.get()), but is actually a string from DBStore.get()"
    )
    def test_embeddable_types(self, site):
        def test(site, key, type):
            self.new(
                site,
                key=key,
                type=type,
                link=dict(title='foo', link='http://infogami.org'),
            )
            d = site.get(key)._get_data()
            self.assertEqual(d['link']['title'], 'foo')
            self.assertEqual(d['link']['link'], 'http://infogami.org')

        def p(name, expected_type, unique=True, **d):
            return locals()

        self.new(
            site,
            key='/type/link',
            type='/type/type',
            properties=[p('title', '/type/string'), p('link', '/type/string')],
            kind='embeddable',
        )
        self.new(
            site,
            key='/type/book',
            type='/type/type',
            properties=[p('link', '/type/link')],
        )

        test(site, '/aaa', '/type/object')
        test(site, '/bbb', '/type/book')

    @pytest.mark.skip(
        reason="site.things(query) always returns [], suspect these tests are old and superseded by those in infogami/infobase/tests"
    )
    def test_things_with_embeddable_types(self, site):
        def link(title, url):
            return dict(title=title, url='http://example.com/' + url)

        self.new(
            site, key='/x', type='/type/object', links=[link('a', 'a'), link('b', 'b')]
        )
        self.new(
            site, key='/y', type='/type/object', links=[link('a', 'b'), link('b', 'a')]
        )

        def things(site, query, result):
            x = site.things(query)
            assert sorted(x) == sorted(result)

        things(
            site,
            {
                'type': '/type/object',
                'links': {'title': 'a', 'url': 'http://example.com/a'},
            },
            ['/x'],
        )
        things(
            site,
            {
                'type': '/type/object',
                'links': {'title': 'a', 'url': 'http://example.com/b'},
            },
            ['/y'],
        )
        things(site, {'type': '/type/object', 'links': {'title': 'a'}}, ['/x', '/y'])
        things(
            site,
            {'type': '/type/object', 'links': {'url': 'http://example.com/a'}},
            ['/x', '/y'],
        )
