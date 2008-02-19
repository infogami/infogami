import hmac
import web
import infobase
import random

def make_query(username, displayname):
    group = username + '/usergroup'

    return [{
        'key': username,
        'displayname': displayname,
        'type': 'type/user'
    }, {
        'key': group,
        'type': 'type/usergroup',
        'members': [username]
    }]

class AccountManager:
    def __init__(self, site):
        self.site = site

    def register(self, username, displayname, email, password):
        username = 'user/' + username

        try:
            self.site.withKey(username)
        except infobase.NotFound:
            pass
        else:
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
            
        session = web.cookies(infobase_session=None).infobase_session
        if session:
            user_id, login_time, digest = session.split(',')
            if self._check_salted_hash(self.site.secret_key, user_id + "," + login_time, digest):
                return self.site.withID(user_id)

    def login(self, username, password):
        username = 'user/' + username
        user = self.site.withKey(username)
        if user and self.checkpassword(user, password):
            self.setcookie(user)
            return user
        else:
            return None

    def setcookie(self, user, remember=False):
        import datetime, time
        t = datetime.datetime(*time.gmtime()[:6]).isoformat()
        text = "%d,%s" % (user.id, t)
        text += "," + self._generate_salted_hash(self.site.secret_key, text)

        expires = (remember and 3600*24*7) or ""
        web.setcookie("infobase_session", text, expires=expires)

    def _generate_salted_hash(self, key, text):
        salt = hmac.HMAC(key, str(random.random())).hexdigest()[:5]
        hash = hmac.HMAC(key, salt + web.utf8(text)).hexdigest()
        return '%s$%s' % (salt, hash)
        
    def _check_salted_hash(self, key, text, salted_hash):
        salt, hash = salted_hash.split('$', 1)
        return hmac.HMAC(key, salt + web.utf8(text)).hexdigest() == hash

    def checkpassword(self, user, raw_password):
        d = web.select('account', where='thing_id=$user.id', vars=locals())
        d = d[0]
        return self._check_salted_hash(self.site.secret_key, raw_password, d.password)

if __name__ == "__main__":
    web.transact()
    from infobase import Infobase
    site = Infobase().get_site('infogami.org')
    a = AccountManager(site)
    web.rollback()
    
