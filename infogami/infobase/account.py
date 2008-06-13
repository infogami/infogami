import hmac
import random
import datetime
import time
import web

import infobase
import config

def make_query(username, displayname):
    group = username + '/usergroup'
    permission = username + '/permission'
    return [{
        'create': 'unless_exists',
        'key': username,
        'displayname': displayname,
        'type': '/type/user'
    }, {
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
    def __init__(self, site):
        self.site = site
    
    def register(self, username, displayname, email, password, password_encrypted=False, timestamp=None):
        username = '/user/' + username
        web.ctx.infobase_bootstrap = True

        if self.site.get(username):
            raise infobase.InfobaseException('Username is already used')

        if self.has_user(email):
            raise infobase.InfobaseException('Email is already used')
             
        web.transact()
        try:
            q = make_query(username, displayname)
            self.site._write(q, timestamp=timestamp, ip=web.ctx.get('ip'), log=False)
            user = self.site.withKey(username)
            if not password_encrypted:
                password = self._generate_salted_hash(self.site.secret_key, password)
            web.insert('account', False, thing_id=user.id, email=email, password=password)    
        except:
            import traceback
            traceback.print_exc()
            web.rollback()
            raise
        else:
            web.commit()
            timestamp = timestamp or datetime.datetime.utcnow()
            self.site.logger.on_new_account(self.site, timestamp, web.lstrips(user.key, '/user/'), email=email, password=password, displayname=displayname)
            self.set_auth_token(user)
            return user
            
    def has_user(self, email):
        d = web.query('SELECT * from account'
            + ' JOIN thing ON account.thing_id = thing.id'
            + ' WHERE thing.site_id=$self.site.id AND account.email=$email', vars=locals())
        return bool(d)
        
    def get_email(self, user):
        d = web.query('SELECT email FROM account WHERE thing_id=$user.id', vars=locals())
        return d and d[0].email
        
    def get_user(self):
        """Returns the current user from the session."""
        #@@ TODO: call assert_trusted_machine when user is admin.
        auth_token = web.ctx.get('infobase_auth_token')
        if auth_token:
            user_id, login_time, digest = auth_token.split(',')
            if self._check_salted_hash(self.site.secret_key, user_id + "," + login_time, digest):
                return self.site.withID(int(user_id))
                
    def update_user(self, old_password, new_password, email, password_encrypted=False, timestamp=None):
        user = self.get_user()
        if user is None:
            raise infobase.InfobaseException("Not logged in")

        if not self.checkpassword(user, old_password):
            raise infobase.InfobaseException('Invalid Password')
            
        new_password and self.assert_password(new_password)
        email and self.assert_email(email)
        
        password = new_password and self._generate_salted_hash(self.site.secret_key, new_password) 
        self._update_user(user, password, email)
    
    def _update_user(self, user, encrypted_password, email, timestamp=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        def _update_password(user, password):
            web.update('account', where='thing_id=$user.id', password=password, vars=locals())
            self.site.logger.on_update_account(self.site, timestamp, user.key, email=None, password=password)
            
        def _update_email(user, email):
            web.update('account', where='thing_id=$user.id', email=email, vars=locals())
            self.site.logger.on_update_account(self.site, timestamp, user.key, email=email, password=None)
        
        if encrypted_password:
            _update_password(user, encrypted_password)
            
        if email:
            _update_email(user, email)
        
            
    def assert_password(self, password):
        pass
        
    def assert_email(self, email):
        pass

    def assert_trusted_machine(self):
        if web.ctx.ip not in config.trusted_machines:
            raise infobase.InfobaseException('Permission denied to login as admin from ' + web.ctx.ip)

    @admin_only
    def get_user_code(self, email):
        """Returns a code for resetting password of a user."""
        d = web.query('SELECT * FROM account' +
            ' JOIN thing ON account.thing_id = thing.id' + 
            ' WHERE thing.site_id=$self.site.id AND account.email=$email', vars=locals())
        
        if not d:
            raise infobase.InfobaseException('No user registered with email: ' + email)
        d = d[0]    
        user = self.site.withID(d.thing_id)

        timestamp = str(int(time.time()))
        text = d.password + '$' + timestamp
        username = web.lstrips(user.key, '/user/')
        return username, timestamp + '$' + self._generate_salted_hash(self.site.secret_key, text)
        
    @admin_only
    def get_user_email(self, username):
        d = web.query("SELECT * FROM account" +
            " JOIN thing ON account.thing_id = thing.id" +
            " WHERE thing.site_id=$self.site.id AND thing.key=$username", vars=locals())
        if not d:
            raise infobase.InfobaseException('No user registered with username: ' + username)
        else:
            return d[0].email
        
    def reset_password(self, username, code, password):
        SEC_PER_WEEK = 7 * 24 * 3600
        timestamp, code = code.split('$', 1)
        
        # code is valid only for a week
        if int(timestamp) + SEC_PER_WEEK < int(time.time()):
            raise infobase.InfobaseException('Password Reset code expired')
            
        username = '/user/' + username
        user = self.site.get(username)
        
        d = web.select('account', where='thing_id=$user.id', vars=locals())
        text = d[0].password + '$' + timestamp
        if self._check_salted_hash(self.site.secret_key, text, code):
            password = self._generate_salted_hash(self.site.secret_key, password)
            web.update('account', where='thing_id=$user.id', password=password, vars=locals())
            self.site.logger.on_update_account(user.key, email=None, password=password)
        else:
            raise infobase.InfobaseException('Invalid password reset code')
        
    def login(self, username, password):
        if username == 'admin':
            self.assert_trusted_machine()
            
        username = '/user/' + username
        user = self.site.get(username)
        if user and self.checkpassword(user, password):
            self.set_auth_token(user)
            return user
        else:
            return None

    def set_auth_token(self, user):
        t = datetime.datetime(*time.gmtime()[:6]).isoformat()
        text = "%d,%s" % (user.id, t)
        text += "," + self._generate_salted_hash(self.site.secret_key, text)
        web.ctx.infobase_auth_token = text

    def _generate_salted_hash(self, key, text, salt=None):
        salt = salt or hmac.HMAC(key, str(random.random())).hexdigest()[:5]
        hash = hmac.HMAC(key, salt + web.utf8(text)).hexdigest()
        return '%s$%s' % (salt, hash)
        
    def _check_salted_hash(self, key, text, salted_hash):
        salt, hash = salted_hash.split('$', 1)
        return self._generate_salted_hash(key, text, salt) == salted_hash

    def checkpassword(self, user, raw_password):
        d = web.select('account', where='thing_id=$user.id', vars=locals())
        return self._check_salted_hash(self.site.secret_key, raw_password, d[0].password)
        
if __name__ == "__main__":
    web.transact()
    from infobase import Infobase
    site = Infobase().get_site('infogami.org')
    a = AccountManager(site)
    web.rollback()
    
