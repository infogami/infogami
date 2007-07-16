from infogami.utils import delegate
import web
from infogami import tdb
import infogami
from infogami.tdb import NotFound
import pickle
from infogami.utils.view import public
        
@infogami.install_hook
def tdbsetup():
    """setup tdb for infogami."""
    from infogami import config
    # hack to disable tdb hooks
    tdb.tdb.hooks = []
    tdb.setup()
    try:
        site = tdb.withName(config.site, tdb.root)
    except:
        site = tdb.new(config.site, tdb.root, tdb.root)
        site.save()

    from infogami.utils.context import context
    context.site = site
    
    try:
        type = tdb.withName('type/type', site)
    except tdb.NotFound:
        type = tdb.new('type/type', site, None, {'*':'string'})
        type.save()

    new_type(site, 'type/page', {'title': 'string', 'body': 'text'})
    new_type(site, 'type/user', {'email': 'email'})
    new_type(site, 'type/delete', {})
    
    # for internal use
    new_type(site, 'type/thing', {})
    
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
    try:
        return tdb.withID(userid)
    except NotFound:
        return None

def get_user_by_name(site, username):
    try:
        return tdb.withName('user/' + username, site)
    except NotFound:
        return None
    
def login(site, username, password):
    try:
        u = get_user_by_name(site, username)
        if u and (get_user_preferences(u).get("password") == password):
            return u
        else:
            return None
    except tdb.NotFound:
        return None
    
def new_user(site, username, email):
    d = dict(email=email)
    return tdb.new('user/' + username, site, get_type(site, "type/user"), d)

def get_password(user):
    return db.get_user_preferences(user).d.get('password')

def set_password(user, password):
    p = get_user_preferences(user)
    p.password = password
    p.save()

def get_user_preferences(user):
    try:
        return tdb.withName('preferences', user)
    except NotFound:
        site = user.parent
        type = get_type(site, 'type/thing')
        return tdb.new('preferences', user, type)
    
@public
def get_type(site, name):
    return tdb.withName(name, site)

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
def get_recent_changes(site, author=None, limit=None):
    if author:
        return tdb.Versions(parent=site, author=author, limit=limit)
    else:
        return tdb.Versions(parent=site, limit=limit)

@public
def list_pages(site, path):
    """Lists all pages with name path/*"""
    delete = get_type(site, 'type/delete')
    
    if path == "":
        pattern = '%'
    else:
        pattern = path + '/%'
        
    return web.query("""SELECT t.id, t.name FROM thing t 
            JOIN version ON version.revision = t.latest_revision AND version.thing_id = t.id
            JOIN datum ON datum.version_id = version.id 
            WHERE t.parent_id=$site.id AND t.name LIKE $pattern 
            AND datum.key = '__type__' AND datum.value != $delete.id
            ORDER BY t.name""", vars=locals())
       
@public
def get_schema(type, keep_back_references=False):
    schema = web.storage(type.d)
    if not keep_back_references:
        schema = web.storage([(k, v) for k, v in schema.items() if not v.startswith('#')])
    return schema
    
            
def get_site_permissions(site):
    if hasattr(site, 'permissions'):
        return pickle.loads(site.permissions)
    else:
        return [('/.*', [('everyone', 'view,edit')])]
    
def set_site_permissions(site, permissions):
    site.permissions = pickle.dumps(permissions)
    site.save()
