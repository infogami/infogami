import utils
import web

from infogami.infobase import server, account, bootstrap, common

import pytest


def setup_module(mod):
    utils.setup_site(mod)


def teardown_module(mod):
    site.cache.clear()
    utils.teardown_site(mod)


class TestAccount:
    global site

    def setup_method(self, method):
        global db
        self.tx = db.transaction()

    def teardown_method(self, method):
        self.tx.rollback()
        site.cache.clear()

    def test_register(self):
        a = site.account_manager
        a.register(username="joe", email="joe@example.com", password="secret", data={})

        # login should fail before activation 
        assert a.login('joe', 'secret') == "account_not_verified"
        assert a.login('joe', 'wrong-password') == "account_bad_password"

        a.activate(username="joe")

        assert a.login('joe', 'secret') == "ok"
        assert a.login('joe', 'wrong-password') == "account_bad_password"

    def test_register_failures(self, _activate=True):
        a = site.account_manager
        a.register(username="joe", email="joe@example.com", password="secret", data={}, _activate=_activate)

        try:
            a.register(username="joe", email="joe2@example.com", password="secret", data={})
            assert False
        except common.BadData as e:
            assert e.d['message'] == "User already exists: joe"

        try:
            a.register(username="joe2", email="joe@example.com", password="secret", data={})
            assert False
        except common.BadData as e:
            assert e.d['message'] == "Email is already used: joe@example.com"

    def test_register_failures2(self):
        # test registeration without activation + registration with same username/email
        self.test_register_failures(_activate=False)

    def encrypt(self, password):
        """Generates encrypted password from raw password."""
        a = site.account_manager
        return a._generate_salted_hash(a.secret_key, password)

    def test_login_account(self):
        f = site.account_manager._verify_login
        enc_password = self.encrypt("secret")

        assert f(dict(enc_password=enc_password, status="active"), "secret") == "ok"
        assert f(dict(enc_password=enc_password, status="active"), "bad-password") == "account_bad_password"

        # pending accounts should return "account_not_verified" if the password is correct
        assert f(dict(enc_password=enc_password, status="pending"), "secret") == "account_not_verified"
        assert f(dict(enc_password=enc_password, status="pending"), "bad-password") == "account_bad_password"

    def test_update(self):
        a = site.account_manager
        a.register(username="foo", email="foo@example.com", password="secret", data={})
        a.activate("foo")
        assert a.login("foo", "secret") == "ok"

        # test update password
        assert a.update("foo", password="more-secret") == "ok"
        assert a.login("foo", "secret") == "account_bad_password"
        assert a.login("foo", "more-secret") == "ok"

        ## test update email

        # registering with the same email should fail.
        assert pytest.raises(common.BadData, a.register, username="bar", email="foo@example.com", password="secret", data={})

        assert a.update("foo", email="foo2@example.com") == "ok"

        # someone else should be able to register with the old email
        a.register(username="bar", email="foo@example.com", password="secret", data={})

        # and no one should be allowed to register with new email
        assert pytest.raises(common.BadData, a.register, username="bar", email="foo2@example.com", password="secret", data={})


