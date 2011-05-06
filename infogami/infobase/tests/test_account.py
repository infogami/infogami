import utils
import web

from infogami.infobase import server, account, bootstrap, common

def setup_module(mod):
    utils.setup_site(mod)

def teardown_module(mod):
    site.cache.clear()
    utils.teardown_site(mod)

class TestAccount:
    def setup_method(self, method):
        self.tx = db.transaction()
    
    def teardown_method(self, method):
        self.tx.rollback()
        site.cache.clear()

    def test_register(self):
        a = site.account_manager
        activation_code = a.register(username="joe", email="joe@example.com", password="secret", data={})
        assert activation_code is not None

        a.activate(email='joe@example.com', activation_code=activation_code)

        assert a.login('joe', 'secret') is not None
        assert a.login('joe', 'wrong-password') is None
    
    def test_register_failures(self, _activate=True):
        a = site.account_manager
        a.register(username="joe", email="joe@example.com", password="secret", data={}, _activate=_activate)
        
        try:
            a.register(username="joe", email="joe2@example.com", password="secret", data={})
            assert False
        except common.BadData, e:
            assert e.d['message'] == "User already exists: joe"
            
        try:
            a.register(username="joe2", email="joe@example.com", password="secret", data={})
            assert False
        except common.BadData, e:
            assert e.d['message'] == "Email is already used: joe@example.com"

    def test_register_failures2(self):
        # test registeration without activation + registration with same username/email
        self.test_register_failures(_activate=False)
