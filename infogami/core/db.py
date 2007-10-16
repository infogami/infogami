import web
import pickle

import infogami
from infogami import tdb
from infogami.utils.view import public

def _create_type(site, name, properties=[], backreferences=[], description="", is_primitive=False):
    """Quick hack to create a type."""
    def _property(name, type, unique=True, description=""):
        return _get_thing(t, name, tproperty, dict(type=type, unique=unique, description=description))
        
    def _backreference(name, type, property_name):
        return _get_thing(t, name, tbackreference, dict(type=type, property_name=property_name))

    ttype = get_type(site, 'type/type')
    tproperty = get_type(site, 'type/property')
    tbackreference = get_type(site, 'type/backreference')

    t = _get_thing(site, name, ttype)

    d = {}
    d['is_primitive'] = is_primitive
    d['description'] = description
    d['properties'] = [_property(**p) for p in properties]

    if backreferences:
        d['backreferences'] = [_backreference(**b) for b in backreferences]
        
    t = new_version(site, name, ttype, d)
    t.save()
    return t

def _get_thing(parent, name, type, d={}):
    try:
        thing = tdb.withName(name, parent)
    except:
        thing = tdb.new(name, parent, type, d)
        thing.save()
    return thing

@infogami.install_hook
@infogami.action
def tdbsetup():
    """setup tdb for infogami."""
    from infogami import config
    # hack to disable tdb hooks
    tdb.tdb.hooks = []
    tdb.setup()

    site = _get_thing(tdb.root, config.site, tdb.root)
    from infogami.utils.context import context
    context.site = site 
    
    # type is created with tdb.root as type first and later its type is changed to itself.
    ttype = _get_thing(site, "type/type", tdb.root)
    tproperty = _get_thing(site, "type/property", ttype)
    tbackreference = _get_thing(site, "type/backreference", ttype)

    tint = _create_type(site, "type/int", is_primitive=True)
    tboolean = _create_type(site, "type/boolean", is_primitive=True)
    tstring = _create_type(site, "type/string", is_primitive=True)
    ttext = _create_type(site, "type/text", is_primitive=True)
    
    tproperty = _create_type(site, "type/property", [
       dict(name='type', type=ttype),
       dict(name='unique', type=tboolean),
       dict(name='description', type=ttext),
    ])
    
    tbackreference = _create_type(site, 'type/backreference', [
        dict(name='type', type=ttype),
        dict(name='property_name', type=tstring),
    ])

    ttype = _create_type(site, "type/type", [
       dict(name='description', type=ttext, unique=True),
       dict(name='is_primitive', type=tboolean, unique=True),
       dict(name='properties', type=tproperty, unique=False),
       dict(name='backreferences', type=tbackreference, unique=False),
    ])

    _create_type(site, 'type/page', [
        dict(name='title', type=tstring), 
        dict(name='body', type=ttext)])
        
    _create_type(site, 'type/user', [
        dict(name='displayname', type=tstring),
        dict(name='email', type=tstring), 
        dict(name='description', type=ttext)
    ])
        
    _create_type(site, 'type/delete', [])

    # for internal use
    _create_type(site, 'type/thing', [])
    
    import dbupgrade
    dbupgrade.mark_upgrades()
    
class ValidationException(Exception): pass

def get_version(site, path, revision=None):
    return tdb.withName(path, site, revision=revision and int(revision))

def new_version(site, path, type, data):
    # There are cases where site.id is None. 
    if site.id:
        try:
            p = tdb.withName(path, site)
            p.type = type
            p.setdata(data)
            return p
        except tdb.NotFound:
            pass
                
    return tdb.new(path, site, type, data)
    
def get_user(site, userid):
    try:
        u = tdb.withID(userid)
        if u.type == get_type(site, 'type/user'):
            return u
    except tdb.NotFound:
        return None
        
def get_user_by_name(site, username):
    try:
        return tdb.withName('user/' + username, site)
    except tdb.NotFound:
        return None

def get_user_by_email(site, email):
    result = tdb.Things(parent=site, type=get_type(site, 'type/user'), email=email).list()
    if result:
        return result[0]
    
def new_user(site, username, displayname, email, password):
    web.transact()
    try:
        d = dict(displayname=displayname, email=email)
        user = tdb.new('user/' + username, site, get_type(site, "type/user"), d)
        user.save()
    
        import auth
        auth.set_password(user, password)
    except:
        web.rollback()
        raise
    else:
        web.commit()
        return user

def get_user_preferences(user):
    try:
        return tdb.withName('preferences', user)
    except tdb.NotFound:
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
    return _list_pages(site, path, limit=100)
    
def _list_pages(site, path, limit=None):
    delete = get_type(site, 'type/delete')
    
    if path == "":
        pattern = '%'
    else:
        pattern = path + '/%'
        
    q = """SELECT t.id, t.name FROM thing t 
            JOIN version ON version.revision = t.latest_revision AND version.thing_id = t.id
            JOIN datum ON datum.version_id = version.id 
            WHERE t.parent_id=$site.id AND t.name LIKE $pattern 
            AND datum.key = '__type__' AND datum.value != $delete.id
            ORDER BY t.name"""
    if limit:
        q += ' LIMIT $limit'
    return web.query(q, vars=locals())
                   
def get_things(site, typename, prefix, limit):
    """Lists all things whose names start with typename"""
	
    pattern =  prefix+'%'
    type = get_type(site, typename)
    return web.query("""SELECT t.name FROM thing t 
            JOIN version ON version.revision = t.latest_revision 
						AND version.thing_id = t.id
            JOIN datum ON datum.version_id = version.id 
            WHERE t.parent_id=$site.id AND t.name LIKE $pattern
            AND datum.key = '__type__' AND datum.value = $type.id
            ORDER BY t.name LIMIT $limit""", vars=locals())

def get_site_permissions(site):
    if hasattr(site, 'permissions'):
        return pickle.loads(site.permissions)
    else:
        return [
            ('/(user/[^/]*)(/.*)?', [('$1', 'view,edit'), ('everyone', 'view')]),
            ('/.*', [('everyone', 'view,edit')])]
    
def set_site_permissions(site, permissions):
    site.permissions = pickle.dumps(permissions)
    site.save()
