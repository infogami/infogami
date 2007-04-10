from infogami.utils import delegate
import web
from infogami import tdb
import infogami
from infogami.tdb import NotFound

#@@ move to some better place
@infogami.action
def tdbsetup():
    """setup tdb for infogami."""
    from infogami import config
    web.load()
    # hack to disable tdb hooks
    tdb.tdb.hooks = []
    tdb.setup()
    sitetype = get_type('site') or new_type('site')
    sitetype.save()
    pagetype = get_type('page') or new_type('page')
    pagetype.save()

    try:
        tdb.withName(config.site, sitetype)
    except:
        tdb.new(config.site, sitetype, sitetype).save()
    
class ValidationException(Exception): pass

def get_version(site, path, revision=None):
    return tdb.withName(path, site, revision=revision and int(revision))

def new_version(site, path, type, data):
    try:
        p = tdb.withName(path, site)
        p.type = type
        p.setdata(data)
    except tdb.NotFound:
        p = tdb.new(path, site, type, data)
    
    return p
    
def get_user(userid):
    return tdb.withID(userid)

def get_user_by_name(username):
    try:
        return tdb.withName(username, tdb.usertype)
    except NotFound:
        return None
    
def login(username, password):
    try:
        u = get_user_by_name(username)
        if u and (u.password == password):
            return u
        else:
            return None
    except tdb.NotFound:
        return None
    
def new_user(username, email, password):
    d = dict(email=email, password=password)
    return tdb.new(username, tdb.usertype, tdb.usertype, d)
    
def get_recent_changes(site):
    raise Exception, "Not implemented"
    
def pagelist(site):
    raise Exception, "Not implemented"

def get_type(name, create=False):
    try:
        return tdb.withName(name, tdb.metatype)
    except tdb.NotFound:
        if create:
            type = new_type(name)
            type.save()
            return type
        else:
            return None

def new_type(name):
    return tdb.new(name, tdb.metatype, tdb.metatype)

def get_site(name):
    return tdb.withName(name, get_type("site"))
