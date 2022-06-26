import datetime

import pytest
import json
import web

from infogami.infobase._dbstore.save import SaveImpl, IndexUtil, PropertyManager
from infogami.infobase.tests import utils
from infogami.infobase.tests.pytest_wildcard import wildcard  # noqa: F401


def setup_module(mod):
    utils.setup_db(mod)


def teardown_module(mod):
    utils.teardown_db(mod)


class DBTest:
    def setup_method(self, method):
        self.tx = db.transaction()
        db.insert("thing", key='/type/type')
        db.insert("thing", key='/type/object')

    def teardown_method(self, method):
        self.tx.rollback()


def update_doc(doc, revision, created, last_modified):
    """Add revision, latest_revision, created and latest_revision properties to the given doc."""
    last_modified_repr = {"type": "/type/datetime", "value": last_modified.isoformat()}
    created_repr = {"type": "/type/datetime", "value": created.isoformat()}

    return dict(
        doc,
        revision=revision,
        latest_revision=revision,
        created=created_repr,
        last_modified=last_modified_repr,
    )


def assert_record(record, doc, revision, created, timestamp):
    d = update_doc(doc, revision, created, timestamp)
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
    """Tests for _dbstore_save._get_records_for_save."""

    def test_new(self):
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 1, 1, 1, 1, 1)

        a = {"key": "/a", "type": {"key": "/type/object"}, "title": "a"}
        b = {"key": "/b", "type": {"key": "/type/object"}, "title": "b"}

        docs = [a, b]
        records = s._get_records_for_save(docs, timestamp)

        assert len(records) == 2
        assert_record(records[0], docs[0], 1, timestamp, timestamp)
        assert_record(records[1], docs[1], 1, timestamp, timestamp)

    def test_existing(self):
        def insert(doc, revision, created, last_modified):
            id = db.insert(
                'thing',
                key=doc['key'],
                latest_revision=revision,
                created=created,
                last_modified=last_modified,
            )
            db.insert(
                'data',
                seqname=False,
                thing_id=id,
                revision=revision,
                data=json.dumps(doc),
            )

        created = datetime.datetime(2010, 1, 1, 1, 1, 1)
        a = {"key": "/a", "type": {"key": "/type/object"}, "title": "a"}
        insert(a, 1, created, created)

        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 2, 2, 2, 2, 2)
        records = s._get_records_for_save([a], timestamp)

        assert_record(records[0], a, 2, created, timestamp)


class Test_save(DBTest):
    def get_json(self, key):
        d = db.query(
            "SELECT data.data FROM thing, data WHERE data.thing_id=thing.id AND data.revision = thing.latest_revision AND thing.key = '/a'"
        )
        return json.loads(d[0].data)

    def test_save(self):
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 1, 1, 1, 1, 1)
        a = {"key": "/a", "type": {"key": "/type/object"}, "title": "a"}

        status = s.save(
            [a],
            timestamp=timestamp,
            ip="1.2.3.4",
            author=None,
            comment="Testing create.",
            action="save",
        )

        assert status['changes'][0]['revision'] == 1
        assert self.get_json('/a') == update_doc(a, 1, timestamp, timestamp)

        a['title'] = 'b'
        timestamp2 = datetime.datetime(2010, 2, 2, 2, 2, 2)
        status = s.save(
            [a],
            timestamp=timestamp2,
            ip="1.2.3.4",
            author=None,
            comment="Testing update.",
            action="save",
        )
        assert status['changes'][0]['revision'] == 2
        assert self.get_json('/a') == update_doc(a, 2, timestamp, timestamp2)

    def test_type_change(self):
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 1, 1, 1, 1, 1)
        a = {"key": "/a", "type": {"key": "/type/object"}, "title": "a"}
        status = s.save(
            [a],
            timestamp=timestamp,
            ip="1.2.3.4",
            author=None,
            comment="Testing create.",
            action="save",
        )

        # insert new type
        type_delete_id = db.insert("thing", key='/type/delete')
        a['type']['key'] = '/type/delete'

        timestamp2 = datetime.datetime(2010, 2, 2, 2, 2, 2)
        status = s.save(
            [a],
            timestamp=timestamp2,
            ip="1.2.3.4",
            author=None,
            comment="Testing type change.",
            action="save",
        )

        assert status['changes'][0]['revision'] == 2
        assert self.get_json('/a') == update_doc(a, 2, timestamp, timestamp2)

        thing = db.select("thing", where="key='/a'")[0]
        assert thing.type == type_delete_id

    def test_with_author(self):
        pass

    def test_versions(self):
        pass

    def _get_book_author(self, n):
        author = {
            "key": "/author/%d" % n,
            "type": {"key": "/type/object"},
            "name": "author %d" % n,
        }
        book = {
            "key": "/book/%d" % n,
            "type": {"key": "/type/object"},
            "author": {"key": "/author/%d" % n},
        }
        return author, book

    def test_save_with_cross_refs(self):
        author, book = self._get_book_author(1)
        self._save([author, book])

        author, book = self._get_book_author(2)
        self._save([book, author])

    def _save(self, docs):
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 1, 1, 1, 1, 1)
        return s.save(
            docs,
            timestamp=timestamp,
            comment="foo",
            ip="1.2.3.4",
            author=None,
            action="save",
        )

    def test_save_with_new_type(self):
        docs = [
            {"key": "/type/foo", "type": {"key": "/type/type"}},
            {"key": "/foo", "type": {"key": "/type/foo"}},
        ]
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 1, 1, 1, 1, 1)

        s.save(
            docs,
            timestamp=timestamp,
            comment="foo",
            ip="1.2.3.4",
            author=None,
            action="save",
        )

        type = db.query("SELECT * FROM thing where key='/type/foo'")[0]
        thing = db.query("SELECT * FROM thing where key='/foo'")[0]
        assert thing.type == type.id

    def test_save_with_all_datatypes(self):
        doc = {
            "key": "/foo",
            "type": {"key": "/type/object"},
            "xtype": {"key": "/type/object"},
            "int": 1,
            "str": "foo",
            "text": {"type": "/type/text", "value": "foo"},
            "date": {"type": "/type/datetime", "value": "2010-01-02T03:04:05"},
        }
        self._save([doc])

    def test_save_with_long_string(self):
        docs = [
            {"key": "/type/foo", "type": {"key": "/type/type"}, "title": "a" * 4000}
        ]
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 1, 1, 1, 1, 1)
        s.save(
            docs,
            timestamp=timestamp,
            comment="foo",
            ip="1.2.3.4",
            author=None,
            action="save",
        )

    def test_transaction(self, wildcard):
        docs = [
            {
                "key": "/foo",
                "type": {"key": "/type/object"},
            }
        ]
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 1, 1, 1, 1, 1)
        changeset = s.save(
            docs,
            timestamp=timestamp,
            comment="foo",
            ip="1.2.3.4",
            author=None,
            action="save",
        )
        changeset.pop("docs")
        changeset.pop("old_docs")

        assert changeset == {
            "id": wildcard,
            "kind": "save",
            "timestamp": timestamp.isoformat(),
            "bot": False,
            "comment": "foo",
            "ip": "1.2.3.4",
            "author": None,
            "changes": [{"key": "/foo", "revision": 1}],
            "data": {},
        }


class MockDB:
    def __init__(self):
        self.reset()

    def delete(self, table, vars={}, **kw):
        self.deletes.append(dict(kw, table=table))

    def insert(self, table, **kw):
        self.inserts.append(dict(kw, table=table))

    def reset(self):
        self.inserts = []
        self.deletes = []


class MockSchema:
    def find_table(self, type, datatype, name):
        return "datum_" + datatype


@pytest.fixture
def testdata(request):
    return {
        "doc1": {
            "key": "/doc1",
            "type": {"key": "/type/object"},
            "xtype": {"key": "/type/object"},
            "x": "x0",
            "y": ["y1", "y2"],
            "z": {"a": "za", "b": "zb"},
            "n": 5,
            "text": {"type": "/type/text", "value": "foo"},
        },
        "doc1.index": {
            ("/type/object", "/doc1", "int", "n"): [5],
            ("/type/object", "/doc1", "ref", "xtype"): ['/type/object'],
            ("/type/object", "/doc1", "str", "x"): ["x0"],
            ("/type/object", "/doc1", "str", "y"): ["y1", "y2"],
            ("/type/object", "/doc1", "str", "z.a"): ["za"],
            ("/type/object", "/doc1", "str", "z.b"): ["zb"],
        },
    }


class TestIndex:
    def setup_method(self, method):
        self.indexer = IndexUtil(MockDB(), MockSchema())

    def monkeypatch_indexer(self):
        self.indexer.get_thing_ids = lambda keys: {k: "id:" + k for k in keys}
        self.indexer.get_property_id = lambda type, name: "p:{}-{}".format(
            type.split("/")[-1],
            name,
        )
        self.indexer.get_table = lambda type, datatype, name: "{}_{}".format(
            type.split("/")[-1],
            datatype,
        )

    def test_monkeypatch(self):
        self.monkeypatch_indexer()
        assert self.indexer.get_thing_ids(["a", "b"]) == {"a": "id:a", "b": "id:b"}
        assert self.indexer.get_property_id("/type/book", "title") == "p:book-title"
        assert self.indexer.get_table("/type/book", "foo", "bar") == "book_foo"

    def process_index(self, index):
        """Process index to remove order in the values, so that it is easier to compare."""
        return {k: set(v) for k, v in index.items()}

    def test_compute_index(self, testdata):
        index = self.indexer.compute_index(testdata['doc1'])
        assert self.process_index(index) == self.process_index(testdata['doc1.index'])

    def test_dict_difference(self):
        f = self.indexer._dict_difference
        d1 = {"w": 1, "x": 2, "y": 3}
        d2 = {"x": 2, "y": 4, "z": 5}

        assert f(d1, d2) == {"w": 1, "y": 3}
        assert f(d2, d1) == {"y": 4, "z": 5}

    def test_diff_index(self):
        doc1 = {
            "key": "/books/1",
            "type": {"key": "/type/book"},
            "title": "foo",
            "author": {"key": "/authors/1"},
        }
        doc2 = dict(doc1, title='bar')

        deletes, inserts = self.indexer.diff_index(doc1, doc2)
        assert deletes == {("/type/book", "/books/1", "str", "title"): ["foo"]}
        assert inserts == {("/type/book", "/books/1", "str", "title"): ["bar"]}

        deletes, inserts = self.indexer.diff_index(None, doc1)
        assert deletes == {}
        assert inserts == {
            ("/type/book", "/books/1", "ref", "author"): ["/authors/1"],
            ("/type/book", "/books/1", "str", "title"): ["foo"],
        }

        # when type is changed all the old properties must be deleted
        doc2 = dict(doc1, type={"key": "/type/object"})
        deletes, inserts = self.indexer.diff_index(doc1, doc2)
        assert deletes == {
            ("/type/book", "/books/1", "ref", None): [],
            ("/type/book", "/books/1", "str", None): [],
            ("/type/book", "/books/1", "int", None): [],
        }

    def test_diff_records(self):
        doc1 = {
            "key": "/books/1",
            "type": {"key": "/type/book"},
            "title": "foo",
            "author": {"key": "/authors/1"},
        }
        doc2 = dict(doc1, title='bar')
        record = web.storage(key='/books/1', data=doc2, prev=web.storage(data=doc1))

        deletes, inserts = self.indexer.diff_records([record])
        assert deletes == {("/type/book", "/books/1", "str", "title"): ["foo"]}
        assert inserts == {("/type/book", "/books/1", "str", "title"): ["bar"]}

    def test_compile_index(self):
        self.monkeypatch_indexer()

        index = {
            ("/type/book", "/books/1", "str", "name"): ["Getting started with py.test"],
            ("/type/book", "/books/2", "ref", "author"): ["/authors/1"],
        }
        self.indexer.compile_index(index) == {
            ("book_str", "id:/books/1", "p:book-name"): [
                "Getting started with py.test"
            ],
            ("book_ref", "id:/books/2", "p:book-author"): ["id:/authors/1"],
        }

        # When the type is changed, property_name will be None to indicate that all the properties are to be removed.
        index = {("/type/books", "/books/1", "str", None): []}
        self.indexer.compile_index(index) == {("book_str", "id:/books/1", None): []}

    def test_too_long(self):
        assert self.indexer._is_too_long("a" * 10000) is True
        assert self.indexer._is_too_long("a" * 2047) is False
        c = '\u20AC'  # 3 bytes in utf-8
        assert self.indexer._is_too_long(c * 1000) is False


class TestIndexWithDB(DBTest):
    def _save(self, docs):
        s = SaveImpl(db)
        timestamp = datetime.datetime(2010, 1, 1, 1, 1, 1)
        return s.save(
            docs,
            timestamp=timestamp,
            comment="foo",
            ip="1.2.3.4",
            author=None,
            action="save",
        )

    def test_reindex(self):
        a = {"key": "/a", "type": {"key": "/type/object"}, "title": "a"}
        self._save([a])

        thing = db.query("SELECT * FROM thing WHERE key='/a'")[0]
        key_id = db.query(
            "SELECT * FROM property WHERE type=$thing.type AND name='title'",
            vars=locals(),
        )[0].id

        # there should be only one entry in the index
        d = db.query(
            "SELECT * FROM datum_str WHERE thing_id=$thing.id AND key_id=$key_id",
            vars=locals(),
        )
        assert len(d) == 1

        # corrupt the index table by adding bad entries
        for i in range(10):
            db.insert("datum_str", thing_id=thing.id, key_id=key_id, value="foo %d" % i)

        # verify that the bad entries are added
        d = db.query(
            "SELECT * FROM datum_str WHERE thing_id=$thing.id AND key_id=$key_id",
            vars=locals(),
        )
        assert len(d) == 11

        # reindex now and verify again that there is only one entry
        SaveImpl(db).reindex(["/a"])
        d = db.query(
            "SELECT * FROM datum_str WHERE thing_id=$thing.id AND key_id=$key_id",
            vars=locals(),
        )
        assert len(d) == 1


class TestPropertyManager(DBTest):
    global db

    def test_get_property_id(self):
        p = PropertyManager(db)
        assert p.get_property_id("/type/object", "title") is None

        pid = p.get_property_id("/type/object", "title", create=True)
        assert pid is not None

        assert p.get_property_id("/type/object", "title") == pid
        assert p.get_property_id("/type/object", "title", create=True) == pid

    def test_rollback(self):
        # cache is not invalidated on rollback. This test confirms that behavior.

        tx = db.transaction()
        p = PropertyManager(db)
        pid = p.get_property_id("/type/object", "title", create=True)
        tx.rollback()

        assert p.get_property_id("/type/object", "title") == pid

    def test_copy(self):
        p = PropertyManager(db)
        pid = p.get_property_id("/type/object", "title", create=True)

        # copy should inherit the cache
        p2 = p.copy()
        assert p2.get_property_id("/type/object", "title") == pid

        # changes to the cache of the copy shouldn't affect the source.
        tx = db.transaction()
        p2.get_property_id("/type/object", "title2", create=True)
        tx.rollback()
        assert p.get_property_id("/type/object", "title2") is None
