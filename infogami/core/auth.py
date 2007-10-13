import db
import time, datetime
import hmac, random
import web
import urllib
from infogami import config
from infogami.utils.context import context as ctx
from web.utils import utf8

SECRET = config.encryption_key

def setcookie(user, remember=False):
    t = datetime.datetime(*time.gmtime()[:6]).isoformat()
    text = "%d,%s" % (user.id, t)
    text += "," + _generate_salted_hash(SECRET, text)

    expires = (remember and 3600*24*7) or ""
    web.setcookie("infogami_session", text, expires=expires)
    
def get_user(site):
    """Returns the current user from the session."""
    session = web.cookies(infogami_session=None).infogami_session
    if session:
        user_id, login_time, digest = session.split(',')
        if _check_salted_hash(SECRET, user_id + "," + login_time, digest):
            return db.get_user(site, int(user_id))

def login(site, username, password, remember=False):
    """Returns the user if login is successful, None otherwise."""
    u = db.get_user_by_name(site, username)
    if check_password(u, password):
        setcookie(u, remember)
        return u
    else:
        return None
        
def _generate_salted_hash(key, text):
    salt = hmac.HMAC(key, str(random.random())).hexdigest()[:5]
    hash = hmac.HMAC(key, salt + utf8(text)).hexdigest()
    return '%s$%s' % (salt, hash)
    
def _check_salted_hash(key, text, salted_hash):
    salt, hash = salted_hash.split('$', 1)
    return hmac.HMAC(key, salt + utf8(text)).hexdigest() == hash
    
def check_password(user, raw_password):
    prefs = user and db.get_user_preferences(user)
    return _check_salted_hash(SECRET, raw_password, prefs.password)

def set_password(user, raw_password):
    p = db.get_user_preferences(user)
    p.password = _generate_salted_hash(SECRET, raw_password)
    p.save()
    
def random_password():
    import string
    n = random.randint(8, 16)
    chars = string.letters + string.digits
    password = "".join([random.choice(chars) for i in range(n)])
    return password

def require_login(f):
    def g(*a, **kw):
        if not get_user(ctx.site):
            return login_redirect()
        return f(*a, **kw)
        
    return g

def login_redirect(path=None):
    if path is None:
        path = web.ctx.fullpath
    
    query = urllib.urlencode({"redirect":path})
    web.seeother("/account/login?" + query)
    raise StopIteration

def has_permission(site, user, path, mode):
    """Tests whether user has permision to do `mode` on site/path.
    """
    path = '/' + path
    perms = db.get_site_permissions(site)

    def replace(who, args):
        """Replace $1, $2.. in who with args."""
        if not args:
            return who
            
        import string, re
        # replace $1 with $g1
        who = re.sub("(\$\d)",  lambda x: '$g' + x.group(1)[1:], who)
        mapping = dict([("g%d" % (i+1), x) for i, x in enumerate(args)])
        return string.Template(who).safe_substitute(mapping)
        
    def get_items():
        import re
        for pattern, items in perms:
            match = re.match('^' + pattern + '$', path)
            if match:
                # pattern can have groups rememred using (). 
                # $1, $2 etc can be used in who to replace the remembered groups.
                args = match.groups()
                return [(replace(who, args), what) for who, what in items]

    def has_perm(who, what):
        if mode in what:
            return (who == 'everyone') \
                or (user is not None and who in (user.name, 'loggedin-users'))
        else: 
            return False

    def any(seq):
        for x in seq:
            if x: 
                return True
        return False

    items = get_items() or []
    return any(has_perm(who, what) for who, what in items)
