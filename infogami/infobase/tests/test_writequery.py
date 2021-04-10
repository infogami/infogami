import web

from infogami.infobase import common, writequery
from infogami.infobase.tests import utils


def setup_module(mod):
    utils.setup_site(mod)

    type_book = {
        "key": "/type/book",
        "kind": "regular",
        "type": {"key": "/type/type"},
        "properties": [
            {"name": "title", "expected_type": {"key": "/type/string"}, "unique": True},
            {
                "name": "authors",
                "expected_type": {"key": "/type/author"},
                "unique": False,
            },
            {
                "name": "publish_year",
                "expected_type": {"key": "/type/int"},
                "unique": True,
            },
            {"name": "links", "expected_type": {"key": "/type/link"}, "unique": False},
        ],
    }
    type_author = {
        "key": "/type/author",
        "kind": "regular",
        "type": {"key": "/type/type"},
        "properties": [
            {"name": "name", "expected_type": {"key": "/type/string"}, "unique": True}
        ],
    }
    type_link = {
        "key": "/type/link",
        "kind": "embeddable",
        "type": {"key": "/type/type"},
        "properties": [
            {"name": "title", "expected_type": {"key": "/type/string"}, "unique": True},
            {"name": "url", "expected_type": {"key": "/type/string"}, "unique": True},
        ],
    }
    mod.site.save_many([type_book, type_author, type_link])


def teardown_module(mod):
    utils.teardown_site(mod)


class DBTest:
    def setup_method(self, method):
        global db
        self.tx = db.transaction()

    def teardown_method(self, method):
        self.tx.rollback()


class TestSaveProcessor(DBTest):
    global site

    def test_errors(self):
        def save_many(query):
            try:
                site.save_many(query)
            except common.InfobaseException as e:
                return e.dict()

        q = {
            "key": "/authors/1",
        }
        assert save_many([q]) == {
            'error': 'bad_data',
            'message': 'missing type',
            'at': {'key': '/authors/1'},
        }

        q = {"key": "/authors/1", "type": "/type/author", "name": ["a", "b"]}
        assert save_many([q]) == {
            'error': 'bad_data',
            'message': 'expected atom, found list',
            'at': {'key': '/authors/1', 'property': 'name'},
            'value': ['a', 'b'],
        }

        q = {"key": "/authors/1", "type": "/type/author", "name": 123}
        assert save_many([q]) == {
            'error': 'bad_data',
            'message': 'expected /type/string, found /type/int',
            'at': {'key': '/authors/1', 'property': 'name'},
            "value": 123,
        }

        q = {
            "key": "/books/1",
            "type": "/type/book",
            "authors": [{"key": "/authors/1"}],
        }
        assert save_many([q]) == {
            'error': 'notfound',
            'key': '/authors/1',
            'at': {'key': '/books/1', 'property': 'authors'},
        }

        q = {"key": "/books/1", "type": "/type/book", "publish_year": "not-int"}
        assert save_many([q]) == {
            'error': 'bad_data',
            'message': "invalid literal for int() with base 10: 'not-int'",
            'at': {'key': '/books/1', 'property': 'publish_year'},
            "value": "not-int",
        }

        q = {"key": "/books/1", "type": "/type/book", "links": ["foo"]}
        assert save_many([q]) == {
            'error': 'bad_data',
            'message': 'expected /type/link, found /type/string',
            'at': {'key': '/books/1', 'property': 'links'},
            'value': 'foo',
        }

        q = {"key": "/books/1", "type": "/type/book", "links": [{"title": 1}]}
        assert save_many([q]) == {
            'error': 'bad_data',
            'message': 'expected /type/string, found /type/int',
            'at': {'key': '/books/1', 'property': 'links.title'},
            'value': 1,
        }

    def test_process_value(self):
        def property(expected_type, unique=True, name='foo'):
            return web.storage(
                expected_type=web.storage(key=expected_type, kind='regular'),
                unique=unique,
                name=name,
            )

        p = writequery.SaveProcessor(site.store, None)
        assert p.process_value(1, property('/type/int')) == 1
        assert p.process_value('1', property('/type/int')) == 1
        assert p.process_value(['1', '2'], property('/type/int', unique=False)) == [
            1,
            2,
        ]
