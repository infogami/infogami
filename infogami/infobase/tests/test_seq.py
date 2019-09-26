import unittest

import simplejson

from infogami.infobase.tests import utils
from infogami.infobase._dbstore.sequence import SequenceImpl

def setup_module(mod):
    global db
    utils.setup_db(mod)
    mod.seq = SequenceImpl(db)


def teardown_module(mod):
    utils.teardown_db(mod)
    mod.seq = None


class TestSeq:
    def setup_method(self, method):
        global db
        db.delete("seq", where="1=1")

    def test_seq(self):
        global seq
        seq.get_value("foo") == 0
        seq.next_value("foo") == 1
        seq.get_value("foo") == 1

        seq.next_value("foo") == 2
        seq.next_value("foo") == 3
