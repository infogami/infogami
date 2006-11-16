import db
import time, datetime
import hmac
import web

def setcookie(user):
    t = datetime.datetime(*time.gmtime()[:6]).isoformat()
    text = "%d,%s" % (user.id, t)
    text += "," + _digest(text)
    web.setcookie("infogami_session", text)
    #print >> web.debug, 'setcookie', text
    
def get_user():
    """Returns the current user from the session."""
    session = web.cookies(infogami_session=None).infogami_session
    if session:
        user_id, login_time, digest = session.split(',')
        if _digest(user_id + "," + login_time) == digest:
            return db.get_user(int(user_id))

def _digest(text):
    #print >> web.debug, 'digest', text
    return hmac.HMAC(text).hexdigest()
