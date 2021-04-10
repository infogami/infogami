"""Bug#239238

https://bugs.launchpad.net/infogami/+bug/239238

Change author of a book from a1 to a2.
That book is not listed in a2.books.
"""

from . import webtest
from .test_infobase import InfobaseTestCase
from infogami.infobase import client


class Test(InfobaseTestCase):
    def create_site(self, name='test'):
        conn = client.connect(type='local')
        return client.Site(conn, 'test')

    def testBug(self):
        self.create_book_author_types()

        self.new('/a/a1', '/type/author')
        self.new('/a/a2', '/type/author')
        self.new('/b/b1', '/type/book', author='/a/a1')

        site = self.create_site()
        a1 = site.get('/a/a1')
        a2 = site.get('/a/a2')

        def keys(things):
            return [t.key for t in things]

        assert keys(a1.books) == ['/b/b1']
        assert keys(a2.books) == []

        site.write(
            {
                'key': '/b/b1',
                'author': {
                    'connect': 'update',
                    'key': '/a/a2',
                },
            }
        )

        site = self.create_site()
        a1 = site.get('/a/a1')
        a2 = site.get('/a/a2')

        assert keys(a1.books) == []
        assert keys(a2.books) == ['/b/b1']


if __name__ == "__main__":
    webtest.main()
