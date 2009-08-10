import hmac
import random
import datetime
import time
import web

import common
import config

def make_query(username, data):
    group = username + '/usergroup'
    permission = username + '/permission'
    q = {
        'create': 'unless_exists',
        'key': username,
        'type': '/type/user'    
    }
    q.update(data)
    return [q, 
        {
            'create': 'unless_exists',
            'key': group,
            'type': '/type/usergroup',
            'members': [username]
        },
        {
            'create': 'unless_exists',
            'key': permission,
            'type': '/type/permission',
            'readers': ['/usergroup/everyone'],
            'writers': [group],
            'admins': [group]
        },
        {
            'key': username,
            'permission': {
                'connect': 'update',
                'key': permission
            }
        }
    ]
    
def admin_only(f):
    """Decorator to limit a function to admin user only."""
    def g(self, *a, **kw):
        user = self.get_user()
        if user is None or user.key != '/user/admin':
            raise common.PermissionDenied('Permission denied')
        return f(self, *a, **kw)
    return g

class AccountManager:
    def __init__(self, site, secret_key):
        self.site = site
        self.secret_key = secret_key
        
    def register(self, username, email, password, data):
        enc_password = self._generate_salted_hash(self.secret_key, password)
        self.register1(username, email, enc_password, data)
        
    def register1(self, username, email, enc_password, data, ip=None, timestamp=None):
        ip = ip or web.ctx.ip
        key = '/user/' + username
        if self.site.get(key):
            raise common.BadData("User already exists: " + username)
        
        if self.site.store.find_user(email):
            raise common.BadData('Email is already used: ' + email)

        def f():
            web.ctx.disable_permission_check = True
            q = make_query(key, data)
            self.site.write(q, ip=ip, timestamp=timestamp, _internal=True, author=None, action='register')
            self.site.store.register(key, email, enc_password)
        
        timestamp = timestamp or datetime.datetime.utcnow()
        
        self.site.store.transact(f)
        
        event_data = dict(data, username=username, email=email, password=enc_password)
        self.site._fire_event("register", timestamp=timestamp, ip=ip or web.ctx.ip, username=None, data=event_data)
        
        self.set_auth_token(key)
                        
    def update_user(self, old_password, new_password, email):
        user = self.get_user()
        if user is None:
            raise common.PermissionDenied("Not logged in")

        if not self.checkpassword(user.key, old_password):
            raise common.BadData('Invalid Password')
        
        new_password and self.assert_password(new_password)
        email and self.assert_email(email)
        
        enc_password = new_password and self._generate_salted_hash(self.secret_key, new_password)
        self.update_user1(user, enc_password, email)
        
    def update_user1(self, user, enc_password, email, ip=None, timestamp=None):
        self.site.store.update_user_details(user.key, email, enc_password)
        
        timestamp = timestamp or datetime.datetime.utcnow()
        event_data = dict(username=user.key, email=email, password=enc_password)
        self.site._fire_event("update_user", timestamp=timestamp, ip=ip or web.ctx.ip, username=None, data=event_data)
        
    def assert_password(self, password):
        pass
        
    def assert_email(self, email):
        pass

    def assert_trusted_machine(self):
        if web.ctx.ip not in config.trusted_machines:
            raise common.PermissionDenied('Permission denied to login as admin from ' + web.ctx.ip)
            
    @admin_only
    def get_user_email(self, username):
        details = self.site.store.get_user_details(username)
        
        if not details:
            raise common.BadData('No user registered with username: ' + username)
        else:
            return details.email
            
    def get_email(self, user):
        """Used internally by server."""
        details = self.site.store.get_user_details(user.key)
        return details.email

    @admin_only
    def get_user_code(self, email):
        """Returns a code for resetting password of a user."""
        
        key = self.site.store.find_user(email)
        if not key:
            raise common.NotFound('No user registered with email: ' + email)
            
        username = web.lstrips(key, '/user/')
        details = self.site.store.get_user_details(key)

        # generate code by combining encrypt password and timestamp. 
        # encrypted_password for verification and timestamp for expriry check.
        timestamp = str(int(time.time()))
        text = details.password + '$' + timestamp
        return username, timestamp + '$' + self._generate_salted_hash(self.secret_key, text)
            
    def reset_password(self, username, code, password):
        SEC_PER_WEEK = 7 * 24 * 3600
        timestamp, code = code.split('$', 1)
        
        # code is valid only for a week
        if int(timestamp) + SEC_PER_WEEK < int(time.time()):
            raise common.BadData('Password Reset code expired')
            
        username = '/user/' + username        
        details = self.site.store.get_user_details(username)
        
        if not details:
            raise common.NotFound("No such user: " + username)
        
        text = details.password + '$' + timestamp
        
        if self._check_salted_hash(self.secret_key, text, code):
            enc_password = self._generate_salted_hash(self.secret_key, password)
            self.site.store.update_user_details(username, email=None, enc_password=enc_password)
        else:
            raise common.BadData('Invalid password reset code')
        
    def login(self, username, password):
        if username == 'admin':
            self.assert_trusted_machine()
            
        username = '/user/' + username
        if self.checkpassword(username, password):
            self.set_auth_token(username)
            return self.site.get(username)
        else:
            return None

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
                return self.site.get(user_key)

    def set_auth_token(self, user_key):
        t = datetime.datetime(*time.gmtime()[:6]).isoformat()
        text = "%s,%s" % (user_key, t)
        text += "," + self._generate_salted_hash(self.secret_key, text)
        web.ctx.infobase_auth_token = text

    def _generate_salted_hash(self, key, text, salt=None):
        salt = salt or hmac.HMAC(key, str(random.random())).hexdigest()[:5]
        hash = hmac.HMAC(key, salt + web.utf8(text)).hexdigest()
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

if __name__ == "__main__":
    web.transact()
    from infobase import Infobase
    site = Infobase().get_site('infogami.org')
    a = AccountManager(site)
    web.rollback()
    
