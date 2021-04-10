from infogami.infobase import common
import web
from six import string_types


class Indexer:
    """Indexer computes the values to be indexed.

    >>> indexer = Indexer()
    >>> sorted(indexer.compute_index({"key": "/books/foo", "title": "The Foo Book", "authors": [{"key": "/authors/a1"}, {"key": "/authors/a2"}]}))
    [('ref', 'authors', '/authors/a1'), ('ref', 'authors', '/authors/a2'), ('str', 'title', 'The Foo Book')]
    """

    def compute_index(self, doc):
        """Returns an iterator with (datatype, key, value) for each value be indexed."""
        index = common.flatten_dict(doc)

        # skip special values and /type/text
        skip = [
            "id",
            "key",
            "type.key",
            "revision",
            "latest_revison",
            "last_modified",
            "created",
        ]
        index = set(
            (k, v)
            for k, v in index
            if k not in skip and not k.endswith(".value") and not k.endswith(".type")
        )

        for k, v in index:
            if k.endswith(".key"):
                yield 'ref', web.rstrips(k, ".key"), v
            elif isinstance(v, string_types):
                yield 'str', k, v
            elif isinstance(v, int):
                yield 'int', k, v

    def diff_index(self, old_doc, new_doc):
        """Compute the difference between the index of old doc and new doc.
        Returns the indexes to be deleted and indexes to be inserted.

        >>> i = Indexer()
        >>> r1 = {"key": "/books/foo", "title": "The Foo Book", "authors": [{"key": "/authors/a1"}, {"key": "/authors/a2"}]}
        >>> r2 = {"key": "/books/foo", "title": "The Bar Book", "authors": [{"key": "/authors/a2"}]}
        >>> deletes, inserts = i.diff_index(r1, r2)
        >>> sorted(deletes)
        [('ref', 'authors', '/authors/a1'), ('str', 'title', 'The Foo Book')]
        >>> list(inserts)
        [('str', 'title', 'The Bar Book')]
        """

        def get_type(doc):
            return doc.get('type', {}).get('key', None)

        new_index = set(self.compute_index(new_doc))

        # nothing to delete when the old doc is not specified
        if not old_doc:
            return [], new_index

        old_index = set(self.compute_index(old_doc))
        if get_type(old_doc) != get_type(new_doc):
            return old_index, new_index
        else:
            return old_index.difference(new_index), new_index.difference(old_index)
