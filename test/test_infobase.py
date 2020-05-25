import unittest

import pytest
import simplejson
from six.moves.urllib_parse import urlencode, urljoin
from six.moves.urllib_request import Request
import web

from infogami.infobase import server


def browser():
    if web.config.get('test_url'):
        b = web.browser.Browser()
        b.open('http://0.0.0.0:8080')
        return b
    else:
        return server.app.browser()

b = browser()

def request(path, method="GET", data=None, headers={}):
    if method == 'GET' and data is not None:
        path = path + '?' + urlencode(data)
        data = None
    if isinstance(data, dict):
        data = simplejson.dumps(data)
    url = urljoin(b.url, path)
    req = Request(url, data, headers)
    req.get_method = lambda: method
    b.do_request(req)
    if b.status == 200:
        return b.data and simplejson.loads(b.data)
    else:
        return None

def get(key):
    d = request('/test/get?key=' + key)
    return d

def echo(msg):
    request('/_echo', method='POST', data=msg)

def save(query):
    return request('/test/save' + query['key'], method='POST', data=query)

def save_many(query, comment=''):
    return request('/test/save_many', method='POST', data=urlencode({'query': simplejson.dumps(query), 'comment': comment}))

class DatabaseTest(unittest.TestCase):
    pass

class InfobaseTestCase(unittest.TestCase):
    def clear_threadlocal(self):
        import threading
        t = threading.currentThread()
        if hasattr(t, '_d'):
            del t._d

    def setUp(self):
        self.clear_threadlocal()

        global b
        b = browser()
        try:
            # create new database with name "test"
            self.assertEquals2(request("/test", method="PUT"), {"ok": True})
        except Exception:
            self.tearDown()
            raise

        # reset browser cookies
        b.reset()

    def tearDown(self):
        self.clear_threadlocal()
        # delete test database
        request('/test', method="DELETE")

    def assertEquals2(self, a, b):
        """Asserts two objects are same.
        """
        # special case to say don't worry about this value.
        if b == '*':
            return True
        elif isinstance(a, dict):
            self.assertTrue(isinstance(b, dict))
            # key '*' means skip additional keys.
            skip_additional = b.pop('*', False)
            if not skip_additional:
                self.assertEqual(list(a.keys()), list(b.keys()))
            for k in list(b.keys()):
                self.assertEquals2(a[k], b[k])
        elif isinstance(a, list):
            self.assertEqual(len(a), len(b))
            for x, y in zip(a, b):
                self.assertEquals2(x, y)
        else:
            self.assertEqual(a, b)

@pytest.mark.skip(reason="Unsure how these browser tests were run. Try ./scripts/test infobase -d infobase_test")
class DocumentTest(InfobaseTestCase):
    def test_simple(self):
        self.assertEquals2(request('/'), {'infobase': 'welcome', 'version': '*'})
        self.assertEquals2(request('/test'), {'name': 'test'})
        self.assertEquals2(request('/test/get?key=/type/type'), {'key': '/type/type', 'type': {'key': '/type/type'}, '*': True})

        request('/test/get?key=/not-there')
        self.assertEqual(b.status, 404)

    def test_save(self):
        x = {'key': '/new_page', 'type': {'key': '/type/object'}, 'x': 1, 's': 'hello'}
        d = request('/test/save/new_page', method="POST", data=x)
        self.assertEqual(b.status, 200)
        self.assertEqual(d, {'key': '/new_page', 'revision': 1})

        # verify data
        d = request('/test/get?key=/new_page')
        expected = dict({'latest_revision': 1, 'revision': 1, '*': True}, **d)
        self.assertEquals2(d, expected)

        # nothing should be modified when saved with the same data.
        d = request('/test/save/new_page', method="POST", data=x)
        self.assertEqual(b.status, 200)
        self.assertEqual(d, {})

    def test_versions(self):
        x = {'key': '/new_page', 'type': {'key': '/type/object'}, 'x': 1, 's': 'hello'}
        d = request('/test/save/new_page', method="POST", data=x)

        # verify revisions
        q = {'key': '/new_page'}
        d = request('/test/versions', method='GET', data={'query': simplejson.dumps({'key': '/new_page'})})
        self.assertEquals2(d, [{'key': '/new_page', 'revision': 1, '*': True}])

        d = request('/test/versions', method='GET', data={'query': simplejson.dumps({'limit': 1})})
        self.assertEquals2(d, [{'key': '/new_page', 'revision': 1, '*': True}])

        # try a failed save and make sure new revisions are not created
        request('/test/save/new_page', method='POST', data={'key': '/new_page', 'type': '/type/no-such-type'})
        self.assertNotEqual(b.status, 200)

        q = {'key': '/new_page'}
        d = request('/test/versions', method='GET', data={'query': simplejson.dumps({'key': '/new_page'})})
        self.assertEquals2(d, [{'key': '/new_page', 'revision': 1, '*': True}])

        d = request('/test/versions', method='GET', data={'query': simplejson.dumps({'limit': 1})})
        self.assertEquals2(d, [{'key': '/new_page', 'revision': 1, '*': True}])

        # save the page and make sure new revision is created.
        d = request('/test/save/new_page', method='POST', data=dict(x, title='foo'))
        self.assertEqual(d, {'key': '/new_page', 'revision': 2})

        d = request('/test/versions', method='GET', data={'query': simplejson.dumps({'key': '/new_page'})})
        self.assertEquals2(d, [{'key': '/new_page', 'revision': 2, '*': True}, {'key': '/new_page', 'revision': 1, '*': True}])

    def test_save_many(self):
        q = [
            {'key': '/one', 'type': {'key': '/type/object'}, 'n': 1},
            {'key': '/two', 'type': {'key': '/type/object'}, 'n': 2}
        ]
        d = request('/test/save_many', method='POST', data=urlencode({'query': simplejson.dumps(q)}))
        self.assertEqual(d, [{'key': '/one', 'revision': 1}, {'key': '/two', 'revision': 1}])

        self.assertEquals2(get('/one'), {'key': '/one', 'type': {'key': '/type/object'}, 'n': 1, 'revision': 1,'*': True})
        self.assertEquals2(get('/two'), {'key': '/two', 'type': {'key': '/type/object'}, 'n': 2, 'revision': 1, '*': True})

        # saving with same data should not create new revisions
        d = request('/test/save_many', method='POST', data=urlencode({'query': simplejson.dumps(q)}))
        self.assertEqual(d, [])

        # try bad query
        q = [
            {'key': '/zero', 'type': {'key': '/type/object'}, 'n': 0},
            {'key': '/one', 'type': {'key': '/type/object'}, 'n': 11},
            {'key': '/two', 'type': {'key': '/type/no-such-type'}, 'n': 2}
        ]
        d = request('/test/save_many', method='POST', data=urlencode({'query': simplejson.dumps(q)}))
        self.assertNotEqual(b.status, 200)

        d = get('/zero')
        self.assertEqual(b.status, 404)

# create author, book and collection types to test validations
types = [{
    "key": "/type/author",
    "type": "/type/type",
    "kind": "regular",
    "properties": [{
        "name": "name",
        "expected_type": {"key": "/type/string"},
        "unique": True
    }, {
        "name": "bio",
        "expected_type": {"key": "/type/text"},
        "unique": True
    }]
}, {
    "key": "/type/book",
    "type": "/type/type",
    "kind": "regular",
    "properties": [{
        "name": "title",
        "expected_type": {"key": "/type/string"},
        "unique": True
    }, {
        "name": "authors",
        "expected_type": {"key": "/type/author"},
        "unique": False
    }, {
        "name": "publisher",
        "expected_type": {"key": "/type/string"},
        "unique": True
    }, {
        "name": "description",
        "expected_type": {"key": "/type/text"},
        "unique": True
    }]
}, {
    "key": "/type/collection",
    "type": "/type/type",
    "kind": "regular",
    "properties": [{
        "name": "name",
        "expected_type": {"key": "/type/string"},
        "unique": True
    }, {
        "name": "books",
        "expected_type": {"key": "/type/book"},
        "unique": False
    }]
}]

class MoreDocumentTest(DocumentTest):
    def setUp(self):
        DocumentTest.setUp(self)
        save_many(types)

    def test_save_validation(self):
        # ok: name is string
        d = save({'key': '/author/x', 'type': '/type/author', 'name': 'x'})
        self.assertEqual(b.status, 200)
        self.assertEqual(d, {"key": "/author/x", "revision": 1})

        # error: name is int instead of string
        d = save({'key': '/author/x', 'type': '/type/author', 'name': 42})
        self.assertEqual(b.status, 400)

        # error: name is list instead of single value
        d = save({'key': '/author/x', 'type': '/type/author', 'name': ['x', 'y']})
        self.assertEqual(b.status, 400)

    def test_validation_when_type_changes(self):
        # create an author and a book
        save({'key': '/author/x', 'type': '/type/author', 'name': 'x'})
        save({'key': '/book/x', 'type': '/type/book', 'title': 'x', 'authors': [{'key': '/author/x'}], 'publisher': 'publisher_x'})

        # change schema of "/type/book" and make expected_type of "publisher" as "/type/publisher"
        save({
            "key": "/type/publisher",
            "type": "/type/type",
            "kind": "regular",
            "properties": [{
                "name": "name",
                "expected_type": "/type/string",
                "unique": True
             }]
        })

        d = get('/type/book')
        assert d['properties'][2]['name'] == "publisher"
        d['properties'][2]['expected_type'] = {"key": "/type/publisher"}
        save(d)

        # now changing just the title of the book should not fail.
        d = get('/book/x')
        d['title'] = 'xx'
        save(d)
        self.assertEqual(b.status, 200)

if __name__ == "__main__":
    unittest.main()
