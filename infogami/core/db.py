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
    
    assert type is not None    
    return web.ctx.site.new(path, {'key': path, 'type': type})

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
    return get_version(user.key + '/preferences')
    
@public
def get_recent_changes(key=None, author=None, limit=None, offset=None):
    q = {'sort': '-created'}
    if key is not None:
        q['key'] = key

    if author:
        q['author'] = author.key
    
    q['limit'] = limit or 100
    q['offset'] = offset or 0
    return web.ctx.site.versions(q)

@public
def list_pages(path, limit=100, offset=0):
    """Lists all pages with name path/*"""
    return _list_pages(path, limit=limit, offset=offset)
    
def _list_pages(path, limit, offset):
    if path == "/":
        pattern = '/*'
    else:
        pattern = path + '/*'
    
    q = {
        'key~': pattern,
        'sort': 'key'
    }
    q['limit'] = limit
    q['offset'] = offset
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
    