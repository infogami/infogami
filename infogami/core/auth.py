import db
import time, datetime
import hmac
import web

SECRET = "ofu889e4i5kfem" #@@ make configurable

def setcookie(user, remember=False):
    t = datetime.datetime(*time.gmtime()[:6]).isoformat()
    text = "%d,%s" % (user.id, t)
    text += "," + _digest(text)

    expires = (remember and 3600*24*7) or ""
    web.setcookie("infogami_session", text, expires=expires)
    
def get_user():
    """Returns the current user from the session."""
    session = web.cookies(infogami_session=None).infogami_session
    if session:
        user_id, login_time, digest = session.split(',')
        if _digest(user_id + "," + login_time) == digest:
            return db.get_user(int(user_id))

def _digest(text):
    return hmac.HMAC(SECRET, text).hexdigest()
