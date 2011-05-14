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
        
        # login should fail before activation 
        assert a.login('joe', 'secret') == "not_verified"
        assert a.login('joe', 'wrong-password') == "failed"

        a.activate(email='joe@example.com', activation_code=activation_code)

        assert a.login('joe', 'secret') == "ok"
        assert a.login('joe', 'wrong-password') == "failed"
    
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
        
    def encrypt(self, password):
        """Generates encrypted password from raw password."""
        a = site.account_manager
        return a._generate_salted_hash(a.secret_key, password)
        
    def test_login_account(self):
        f = site.account_manager._login_account
        enc_password = self.encrypt("secret")
        
        assert f(dict(password=enc_password, verified=True, active=True), "secret") == "ok"
        assert f(dict(password=enc_password, verified=True, active=True), "bad-password") == "failed"

        # when active is False, it should return "non_active" without checking the password
        assert f(dict(password=enc_password, verified=True, active=False), "secret") == "not_active"
        assert f(dict(password=enc_password, verified=True, active=False), "bad-password") == "not_active"
        
        # when verified is False, it should return "not_verified" only if the password is correct
        assert f(dict(password=enc_password, verified=False, active=True), "secret") == "not_verified"
        assert f(dict(password=enc_password, verified=False, active=True), "bad-password") == "failed"

    def test_login_pending_account(self):
        f = site.account_manager._login_pending_account
        enc_password = self.encrypt("secret")
        
        f(None, "secret") == "not_found"
        f(dict(type="pending-account", password=enc_password), "secret") == "not_verified"
        f(dict(type="pending-account", password=enc_password), "bad-password") == "failed"
        f(dict(), "bad-password") == "not_found"
