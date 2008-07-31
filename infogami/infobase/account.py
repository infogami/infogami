import hmac
import random
import datetime
import time
import web

import infobase
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
    }]
    
def admin_only(f):
    """Decorator to limit a function to admin user only."""
    def g(self, *a, **kw):
        user = self.get_user()
        if user is None or user.key != '/user/admin':
            raise infobase.InfobaseException('Permission denied')
        return f(self, *a, **kw)
    return g

class AccountManager:
    def __init__(self, site, secret_key):
        self.site = site
        self.secret_key = secret_key
        
    def register(self, username, email, password, data):
        key = '/user/' + username
        if self.site.get(key):
            raise Exception("User already exists: " + username)
        
        if self.site.store.find_user(email):
            raise Exception('Email is already used: ' + email)

        q = make_query(key, data)
        self.site.write(q)
        
        enc_password = self._generate_salted_hash(self.secret_key, password)
        self.site.store.update_user_details(key, email, enc_password)
        self.set_auth_token(key)
                        
    def update_user(self, old_password, new_password, email, password_encrypted=False, timestamp=None):
        user = self.get_user()
        if user is None:
            raise infobase.InfobaseException("Not logged in")

        if not self.checkpassword(user, old_password):
            raise infobase.InfobaseException('Invalid Password')
            
        new_password and self.assert_password(new_password)
        email and self.assert_email(email)
        
        password = new_password and self._generate_salted_hash(self.secret_key, new_password) 
        self.site.store.update_user_details(user.key, email, password)
    
    def _update_user(self, user, encrypted_password, email, timestamp=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        def _update_password(user, password):
            web.update('account', where='thing_id=$user.id', password=password, vars=locals())
            
        def _update_email(user, email):
            web.update('account', where='thing_id=$user.id', email=email, vars=locals())
        
        if encrypted_password:
            _update_password(user, encrypted_password)
            
        if email:
            _update_email(user, email)
        
        self.site.logger.on_update_account(self.site, timestamp, 
            username=user.key, 
            password=encrypted_password, 
            email=email, 
            ip=web.ctx.get('ip'))
            
    def assert_password(self, password):
        pass
        
    def assert_email(self, email):
        pass

    def assert_trusted_machine(self):
        if web.ctx.ip not in config.trusted_machines:
            raise infobase.InfobaseException('Permission denied to login as admin from ' + web.ctx.ip)
            
    @admin_only
    def get_user_email(self, username):
        details = self.site.store.get_user_details()
        
        if not details:
            raise infobase.InfobaseException('No user registered with username: ' + username)
        else:
            return details.email

    @admin_only
    def get_user_code(self, email):
        """Returns a code for resetting password of a user."""
        
        key = self.site.store.find_user(email)
        if not key:
            raise infobase.InfobaseException('No user registered with email: ' + email)
            
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
            raise infobase.InfobaseException('Password Reset code expired')
            
        username = '/user/' + username        
        details = self.site.store.get_user_details(username)
        
        text = details.password + '$' + timestamp
        
        if self._check_salted_hash(self.secret_key, text, code):
            enc_password = self._generate_salted_hash(self.secret_key, password)
            self.site.store.update_user_details(username, password=enc_password)
        else:
            raise infobase.InfobaseException('Invalid password reset code')
        
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
            user_key, login_time, digest = auth_token.split(',')
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
        return details is not None and self._check_salted_hash(self.secret_key, raw_password, details.password)
                
if __name__ == "__main__":
    web.transact()
    from infobase import Infobase
    site = Infobase().get_site('infogami.org')
    a = AccountManager(site)
    web.rollback()
    
