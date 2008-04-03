import hmac
import web
import infobase
import random
import time

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
    
    def register(self, username, displayname, email, password):
        username = '/user/' + username
        web.ctx.infobase_bootstrap = True

        if self.site.get(username):
            raise infobase.InfobaseException('Username is already used')

        if self.has_user(email):
            raise infobase.InfobaseException('Email is already used')
             
        web.transact()
        try:
            q = make_query(username, displayname)
            self.site.write(q)
            user = self.site.withKey(username)
            password = self._generate_salted_hash(self.site.secret_key, password)
            web.insert('account', False, thing_id=user.id, email=email, password=password)
        except:
            import traceback
            traceback.print_exc()
            web.rollback()
            raise
        else:
            web.commit()
            self.setcookie(user)
            return user
            
    def has_user(self, email):
        d = web.query('SELECT * from account'
            + ' JOIN thing ON account.thing_id = thing.id'
            + ' WHERE thing.site_id=$self.site.id AND account.email=$email', vars=locals())
        return bool(d)
        
    def get_user(self):
        """Returns the current user from the session."""
        if not web.ctx.get('env'):
            return None
        
        if web.ctx.get('current_user'):
            return web.ctx.current_user
            
        #@@ TODO: call assert_trusted_machine when user is admin.
        session = web.cookies(infobase_session=None).infobase_session
        if session:
            user_id, login_time, digest = session.split(',')
            if self._check_salted_hash(self.site.secret_key, user_id + "," + login_time, digest):
                return self.site.withID(user_id)
                
    def update_user(self, old_password, new_password, email):
        def _update_password(user, password):
            password = self._generate_salted_hash(self.site.secret_key, password)            
            web.update('account', where='thing_id=$user.id', password=password, vars=locals())
            
        def _update_email(user, email):
            web.update('account', where='thing_id=$user.id', email=email, vars=locals())
        
        user = self.get_user()
        if user is None:
            raise NotFound("Not logged in")

        if not self.checkpassword(user, old_password):
            raise infobase.InfobaseException('Invalid Password')
        
        if new_password:
            self.assert_password(new_password)
            _update_password(user, new_password)
            
        if email:
            self.assert_email(email)
            _update_email(user, email)
            
    def assert_password(self, password):
        pass
        
    def assert_email(self, email):
        pass

    def assert_trusted_machine(self):
        trusted_machines = web.config.get('trusted_machines', []) + ['127.0.0.1']
        if web.ctx.ip not in trusted_machines:
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
        else:
            raise infobase.InfobaseException('Invalid password reset code')
        
    def login(self, username, password):
        if username == 'admin':
            self.assert_trusted_machine()
            
        username = '/user/' + username
        user = self.site.get(username)
        if user and self.checkpassword(user, password):
            self.setcookie(user)
            return user
        else:
            return None

    def setcookie(self, user, remember=False):
        web.ctx.current_user = user
        import datetime, time
        t = datetime.datetime(*time.gmtime()[:6]).isoformat()
        text = "%d,%s" % (user.id, t)
        text += "," + self._generate_salted_hash(self.site.secret_key, text)

        expires = (remember and 3600*24*7) or ""
        web.setcookie("infobase_session", text, expires=expires)

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
    
