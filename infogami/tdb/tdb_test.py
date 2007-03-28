import random

import web

web.config.db_parameters = dict(dbn='postgres', db='tdbtest', user='postgres', pw='')
web.db._hasPooling = False
web.load()

import tdb
testname = "foo%s" % random.random()
t = tdb.new(testname, {'title': 'Foo', 'body': "Baz biz boz."})
assert t.name == testname
assert t.title == "Foo"
t.title = "The Story of Foo"
assert t.title == "The Story of Foo"
assert t.d['title'] == "The Story of Foo"
assert t._dirty
t.save('test cases')
assert not t._dirty
assert t.id
t = tdb.withID(t.id)
assert t.title == "The Story of Foo"

t.subjects = ['Foo', 'Stories']
assert t.subjects == ['Foo', 'Stories']
t.author = ['Joe Jacobson']
assert t.author == ['Joe Jacobson']
t.year = 1920
assert t.year == 1920
t.score = 2.5
assert t.score == 2.5
t.related = [tdb.withID(1)]
assert 1 in [x.id for x in t.related]
t.save('test cases')
t = tdb.withID(t.id)
assert t.subjects == ['Foo', 'Stories']
assert t.author == ['Joe Jacobson']
assert t.year == 1920
assert t.score == 2.5
assert 1 in [x.id for x in t.related]
assert t.related[0].name == 'test1'

t2 = tdb.withID(t.id - 1)
assert t != t2
assert t.d == t2.d
assert tdb.withID(1) == tdb.withID(1)


t = tdb.withID(1)
assert t.id == 1
assert t.name == 'test1'
assert t.title == 'this is a test'
assert repr(t) == '<Thing "test1" at 1>'

t = tdb.withName('test1')
assert t.id == 1
assert t.name == 'test1'
assert t.title == 'this is a test'
testtext = "Test no. %s" % random.random()
t.body = testtext
assert t._dirty
t.save("test cases")
assert not t._dirty
assert t.body == testtext

t = tdb.withName('test1')
assert t.body == testtext

t = tdb.Things(title='The Story of Foo', subjects='Foo')
tl = t.list()
assert len(tl) > 1
assert tl[0].title == 'The Story of Foo'
assert tl[1].title == 'The Story of Foo'
assert tl[0].id != tl[1].id

print "Success."