import hmac
import random
import datetime
import time
import web
import logging

import common
import config

logger = logging.getLogger("infobase.account")

def get_user_root():
    user_root = config.get("user_root", "/user")
    return user_root.rstrip("/") + "/"

def make_query(user):
    q = [{
        'key': user.key + '/usergroup',
        'type': {'key': '/type/usergroup'},
        'members': [{'key': user.key}]
    }, 
    {
        'key': user.key + '/permission',
        'type': {'key': '/type/permission'},
        'readers': [{'key': '/usergroup/everyone'}],
        'writers': [{'key': user.key + '/usergroup'}],
        'admins': [{'key': user.key + '/usergroup'}]
    }]
    user.permission = {'key': user.key + '/permission'}
    q.append(user)
    return q

def admin_only(f):
    """Decorator to limit a function to admin user only."""
    def g(self, *a, **kw):
        user = self.get_user()
        if user is None or user.key != get_user_root() + 'admin':
            raise common.PermissionDenied(message='Permission Denied')
        return f(self, *a, **kw)
    return g

class AccountManager:
    def __init__(self, site, secret_key):
        self.site = site
        self.secret_key = secret_key
        
    def register(self, username, email, password, data, _activate=False):
        logger.info("new account registration username=%s", username)
        enc_password = self._generate_salted_hash(self.secret_key, password)

        try:
            self.store_account_info(username, email, enc_password, data)
            if _activate:
                self.activate(username)
        except:
            logger.error("Failed to store registration info. username=%s", username, exc_info=True)
            raise

    def store_account_info(self, username, email, enc_password, data):
        """Store account info in the store so that the account can be created after verifying the email.
        """
        user_key = get_user_root() + username
        if self.site.store.get(user_key) or self.site.store.store.get("account/" + username):
            raise common.BadData(message="User already exists: %s" % username)

        if self.site.store.find_user(email):
            raise common.BadData(message='Email is already used: ' + email)

        if self.site.store.store.query(type="pending-account", name="email", value=email):
            raise common.BadData(message='Email is already used: ' + email)

        now = datetime.datetime.utcnow()
        expires_on = now + datetime.timedelta(days=14) # 2 weeks

        key = "account/" + username
        doc = {
            "_key": key,
            "type": "pending-account",
            "registered_on": now.isoformat(),
            "expires_on": expires_on.isoformat(),

            "username": username,
            "email": email,
            "password": enc_password,
            "data": data
        }
        store = self.site.store.store
        store.put(key, doc)
        
    def find_account(self, email=None, username=None):
        if email:
            return self._find_account_by_email(email)
        elif username:
            return self._find_account_by_username(username)
            
    def _find_account_by_email(self, email):
        username = a.find_user_by_email(i.email)
        
        if username:
            # account exists
            key = get_user_root() + username
            return self.site.store.get_user_details(key)
        else:
            store = self.site.store.store
            rows = store.query(type="pending-account", name="email", value=i.email, include_docs=True)
            if rows:
                return rows[0]['doc']
        
    def _find_account_by_username(self, username):
        key = get_user_root() + username
        details = self.site.store.get_user_details(key)

        if details:
            # Account exists
            return details
        else:
            # Acccount does not exist. see if there is any pending-account.
            return self.site.store.store.get("account/" + username)        

    def activate(self, username):
        store = self.site.store.store
        
        doc = store.get("account/" + username)
        if doc:
            logger.info("activated account: %s", username)
            self.register1(doc['username'], doc['email'], doc['password'], doc['data'])
            return "ok"
        
        key = get_user_root() + username
        details = self.site.store.get_user_details(key)
        
        if details:
            self.update_user_details(username, verified=True)
            logger.info("Marked account as verified: %s", username)
            return "ok"
        else:
            logger.error("account activation failed: %s", username)
            return "account_not_found" 

    def register1(self, username, email, enc_password, data, ip=None, timestamp=None):
        ip = ip or web.ctx.ip
        key = get_user_root() + username
        if self.site.get(key):
            raise common.BadData(message="User already exists: " + username)

        if self.site.store.find_user(email):
            raise common.BadData(message='Email is already used: ' + email)

        def f():
            web.ctx.disable_permission_check = True

            d = web.storage({"key": key, "type": {"key": "/type/user"}})
            d.update(data)
            self.site.save(key, d, timestamp=timestamp, author=d, comment="Created new account")

            q = make_query(d)
            account_bot = config.get('account_bot')
            account_bot = account_bot and web.storage({"key": account_bot, "type": {"key": "/type/user"}})
            self.site.save_many(q, ip=ip, timestamp=timestamp, author=account_bot, action='register', comment="Setup new account")
            self.site.store.register(key, email, enc_password)
            self.update_user_details(username, verified=True, active=True)

            # Add account doc to store
            olddoc = self.site.store.store.get("account/" + username) or {}
            
            doc = {
                "_key": "account/" + username,
                "_rev": olddoc.get("_rev"),
                "type": "account",
                "registered_on": olddoc['registered_on'],
                "activated_on": timestamp.isoformat(),
                "last_login": timestamp.isoformat()
            }
            self.site.store.store.put("account/" + username, doc)

        timestamp = timestamp or datetime.datetime.utcnow()
        self.site.store.transact(f)

        event_data = dict(data, username=username, email=email, password=enc_password)
        self.site._fire_event("register", timestamp=timestamp, ip=ip or web.ctx.ip, username=None, data=event_data)

        self.set_auth_token(key)
        return username

    def update(self, username, **kw):
        key = get_user_root() + username
        details = self.site.store.get_user_details(key)
        
        if not details:
            return "account_not_found"
        else:
            self.site.store.update_user_details(key, **kw)
            return "ok"
                        
    def update_user(self, old_password, new_password, email):
        user = self.get_user()
        if user is None:
            raise common.PermissionDenied(message="Not logged in")

        if not self.checkpassword(user.key, old_password):
            raise common.BadData(message='Invalid Password')
        
        new_password and self.assert_password(new_password)
        email and self.assert_email(email)
        
        enc_password = new_password and self._generate_salted_hash(self.secret_key, new_password)
        self.update_user1(user, enc_password, email)
        
    def update_user1(self, user, enc_password, email, ip=None, timestamp=None):
        self.site.store.update_user_details(user.key, email=email, password=enc_password)
        
        timestamp = timestamp or datetime.datetime.utcnow()
        event_data = dict(username=user.key, email=email, password=enc_password)
        self.site._fire_event("update_user", timestamp=timestamp, ip=ip or web.ctx.ip, username=None, data=event_data)
        
    def update_user_details(self, username, **params):
        """Update user details like email, active, bot, verified.
        """
        key = get_user_root() + username
        self.site.store.update_user_details(key, **params)
        
    def assert_password(self, password):
        pass
        
    def assert_email(self, email):
        pass

    def assert_trusted_machine(self):
        if web.ctx.ip not in config.trusted_machines:
            raise common.PermissionDenied(message='Permission denied to login as admin from ' + web.ctx.ip)
            
    @admin_only
    def get_user_email(self, username):
        logger.debug("get_user_email", username)
        
        if username.startswith("/"):
            # this is user key
            userkey = username
            username = username.split("/")[-1]
        else:
            userkey = get_user_root() + username
        
        details = self.site.store.get_user_details(username)
        
        logger.debug("get_user_email details %s %s", username, details)
        
        if details:
            return details.email
        
        doc = self.site.store.store.get("account/" + username)
        logger.debug("get_user_email doc %s", doc)
        
        if doc and doc.get("type") == "pending-account":
            return doc['email']
        
        raise common.BadData(message='No user registered with username: ' + username, error="account_not_found")
            
    def get_email(self, user):
        """Used internally by server."""
        details = self.site.store.get_user_details(user.key)
        return details.email

    @admin_only
    def get_user_code(self, email):
        """Returns a code for resetting password of a user."""
        
        key = self.site.store.find_user(email)
        if not key:
            raise common.UserNotFound(email=email)
            
        username = web.lstrips(key, get_user_root())
        details = self.site.store.get_user_details(key)

        # generate code by combining encrypt password and timestamp. 
        # encrypted_password for verification and timestamp for expriry check.
        timestamp = str(int(time.time()))
        text = details.password + '$' + timestamp
        return username, timestamp + '$' + self._generate_salted_hash(self.secret_key, text)
    
    def find_user_by_email(self, email):
        return self.site.store.find_user(email)

    def reset_password(self, username, code, password):
        self.check_reset_code(username, code)
        enc_password = self._generate_salted_hash(self.secret_key, password)
        self.site.store.update_user_details(get_user_root() + username, password=enc_password, verified=True)
            
    def check_reset_code(self, username, code):
        SEC_PER_WEEK = 7 * 24 * 3600
        timestamp, code = code.split('$', 1)
        
        # code is valid only for a week
        if int(timestamp) + SEC_PER_WEEK < int(time.time()):
            raise common.BadData(message='Password Reset code expired')

        username = get_user_root() + username 
        details = self.site.store.get_user_details(username)
        
        if not details:
            raise common.BadData(message="Invalid username")
        
        text = details.password + '$' + timestamp
        
        if not self._check_salted_hash(self.secret_key, text, code):
            raise common.BadData(message="Invaid password reset code")
        
    def login(self, username, password):
        """Returns "ok" on success and an error code on failure.
        
        Error code can be one of:
            * account_bad_password
            * account_not_found
            * account_not_verified
            * account_not_active
        """
        if username == 'admin':
            self.assert_trusted_machine()
            
        key = get_user_root() + username
        details = self.site.store.get_user_details(key)
        
        if details:
            # Account exists
            return self._login_account(details, password)
        else:
            # Acccount does not exist. 
            # If there is a pending-account and the password match, return not-verified.
            doc = self.site.store.store.get("account/" + username)
            return self._login_pending_account(doc, password)
    
    def _login_account(self, details, password):
        if "active" in details and details['active'] != True:
            return "account_not_active"
            
        matched = self.verify_password(password, details["password"])
        
        if not matched:
            return "account_bad_password"
        elif not details.get("verified"):
            return "account_not_verified"
        else:
            return "ok"
            
    def _login_pending_account(self, doc, password):
        if not doc:
            return "account_not_found"
        elif doc.get("type") == "pending-account" and self.verify_password(password, doc['password']):
            return "account_not_verified"
        else:
            return "account_bad_password"
    
    def get_user(self):
        """Returns the current user from the session."""
        #@@ TODO: call assert_trusted_machine when user is admin.
        auth_token = web.ctx.get('infobase_auth_token')
        if auth_token:
            try:
                user_key, login_time, digest = auth_token.split(',')
            except ValueError:
                return
            if self._check_salted_hash(self.secret_key, user_key + "," + login_time, digest):
                return self.site._get_thing(user_key)

    def set_auth_token(self, user_key):
        t = datetime.datetime(*time.gmtime()[:6]).isoformat()
        text = "%s,%s" % (user_key, t)
        text += "," + self._generate_salted_hash(self.secret_key, text)
        web.ctx.infobase_auth_token = text

    def _generate_salted_hash(self, key, text, salt=None):
        salt = salt or hmac.HMAC(key, str(random.random())).hexdigest()[:5]
        hash = hmac.HMAC(key, web.utf8(salt) + web.utf8(text)).hexdigest()
        return '%s$%s' % (salt, hash)
        
    def _check_salted_hash(self, key, text, salted_hash):
        salt, hash = salted_hash.split('$', 1)
        return self._generate_salted_hash(key, text, salt) == salted_hash

    def checkpassword(self, username, raw_password):
        details = self.site.store.get_user_details(username)
        if details is None or details.get('active', True) == False:
            return False
        else:
            return self._check_salted_hash(self.secret_key, raw_password, details.password)
            
    def verify_password(self, raw_password, enc_password):
        """Verifies if the raw_password and encrypted password match."""
        return self._check_salted_hash(self.secret_key, raw_password, enc_password)
