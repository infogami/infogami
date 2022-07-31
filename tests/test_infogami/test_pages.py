import json
from urllib.parse import urlencode

import pytest
import web

from infogami.utils.delegate import app

b = app.browser()


@pytest.mark.skip(reason="Site is None")
def test_home():
    b.open('/')
    b.status == 200


@pytest.mark.skip(reason="Site is None")
def test_write():
    b.open('/sandbox/test?m=edit')
    b.select_form(name="edit")
    b['title'] = 'Foo'
    b['body'] = 'Bar'
    b.submit()
    assert b.path == '/sandbox/test'

    b.open('/sandbox/test')
    assert 'Foo' in b.data
    assert 'Bar' in b.data


@pytest.mark.skip(reason="Site is None")
def test_delete():
    b.open('/sandbox/delete?m=edit')
    b.select_form(name="edit")
    b['title'] = 'Foo'
    b['body'] = 'Bar'
    b.submit()
    assert b.path == '/sandbox/delete'

    b.open('/sandbox/delete?m=edit')
    b.select_form(name="edit")
    try:
        b.submit(name="_delete")
    except web.BrowserError as e:
        pass
    else:
        assert False, "expected 404"


@pytest.mark.skip(reason="Site is None")
def test_notfound():
    try:
        b.open('/notthere')
    except web.BrowserError:
        assert b.status == 404


@pytest.mark.skip(reason="Site is None")
def test_recent_changes():
    b.open('/recentchanges')


def save(key, **data):
    b.open(key + '?m=edit')
    b.select_form(name="edit")

    if "type" in data:
        data['type.key'] = [data.pop('type')]

    for k, v in data.items():
        b[k] = v
    b.submit()


def query(**kw):
    url = '/query.json?' + urlencode(kw)
    return [d['key'] for d in json.loads(b.open(url).read())]


@pytest.mark.skip(reason="Site is None")
def test_query():
    save('/test_query_1', title="title 1", body="body 1", type="/type/page")
    assert query(type='/type/page', title='title 1') == ['/test_query_1']

    save('/test_query_1', title="title 2", body="body 1", type="/type/page")
    assert query(type='/type/page', title='title 1') == []
