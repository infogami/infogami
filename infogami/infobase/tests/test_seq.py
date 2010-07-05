from infogami.infobase._dbstore.sequence import SequenceImpl
import utils

import unittest
import simplejson

def setup_module(mod):
    utils.setup_db(mod)
    mod.seq = SequenceImpl(db)
    
def teardown_module(mod):
    utils.teardown_db(mod)
    mod.seq = None

class TestSeq:
    def setup_method(self, method):
        db.delete("seq", where="1=1")
            
    def test_seq(self):
        seq.get_value("foo") == 0
        seq.next_value("foo") == 1
        seq.get_value("foo") == 1

        seq.next_value("foo") == 2
        seq.next_value("foo") == 3
        