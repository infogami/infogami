from infogami.utils.delegate import app
import web

b = app.browser()

def test_home():
    b.open('/')
    b.status == 200

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
    except web.BrowserError, e:
        pass
    else:
        assert False, "expected 404"

def test_notfound():
    try:
        b.open('/notthere')
    except web.BrowserError:
        assert b.status == 404

