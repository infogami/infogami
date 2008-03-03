import web
import pickle

import infogami
from infogami import tdb
from infogami.utils.view import public

def get_version(path, revision=None):
    return web.ctx.site.get(path, revision)

@public
def get_type(path):
    return get_version(path)
    
def new_version(path, type):
    if isinstance(type, basestring):
        type = get_type(type)
    return web.ctx.site.new(path, {'type': type})

class ValidationException(Exception): pass

def get_user(site, userid):
    try:
        u = tdb.withID(userid)
        if u.type == get_type(site, '/type/user'):
            return u
    except tdb.NotFound:
        return None
        
def get_user_by_name(site, username):
    try:
        return tdb.withName('/user/' + username, site)
    except tdb.NotFound:
        return None

def get_user_by_email(site, email):
    result = tdb.Things(parent=site, type=get_type(site, '/type/user'), email=email).list()
    if result:
        return result[0]
    
def new_user(site, username, displayname, email, password):
    tdb.transact()
    try:
        d = dict(displayname=displayname, email=email)
        user = tdb.new('/user/' + username, site, get_type(site, "/type/user"), d)
        user.save()
    
        import auth
        auth.set_password(user, password)
    except:
        tdb.rollback()
        raise
    else:
        tdb.commit()
        return user

def get_user_preferences(user):
    try:
        return tdb.withName('preferences', user)
    except tdb.NotFound:
        site = user.parent
        type = get_type(site, 'type/thing')
        return tdb.new('preferences', user, type)
    
def new_type(site, name, data):
    try:
        return get_type(site, name)
    except tdb.NotFound:
        t = tdb.new(name, site, get_type(site, 'type/type'), data)
        t.save()
        return t

def get_site(name):
    return tdb.withName(name, tdb.root)

@public
def get_recent_changes(key=None, author=None, limit=None):
    q = {'sort': '-created'}
    if key is not None:
        q['key'] = key

    if author:
        q['author'] = author.key
    
    if limit:
        q['limit'] = limit or 100
    return web.ctx.site.versions(q)

@public
def list_pages(path):
    """Lists all pages with name path/*"""
    return _list_pages(path, limit=100)
    
def _list_pages(path, limit=None):
    if path == "/":
        pattern = '/*'
    else:
        pattern = path + '/*'
    
    q = {
        'key~': pattern,
        'sort': 'key'
    }
    if limit:
        q['limit'] = limit
    return [web.ctx.site.get(key, lazy=True) for key in web.ctx.site.things(q)]    
                   
def get_things(typename, prefix, limit):
    """Lists all things whose names start with typename"""	
    q = {
        'key~': prefix + '*',
        'type': typename,
        'sort': 'key',
        'limit': limit
    }
    return [web.ctx.site.get(key, lazy=True) for key in web.ctx.site.things(q)]    
    
def get_site_permissions(site):
    if hasattr(site, 'permissions'):
        return pickle.loads(str(site.permissions))
    else:
        return [
            ('/(user/[^/]*)(/.*)?', [('$1', 'view,edit'), ('everyone', 'view')]),
            ('/.*', [('everyone', 'view,edit')])]
    
def set_site_permissions(site, permissions):
    site.permissions = pickle.dumps(permissions)
    site.save()
