"""
Infogami read/write API.
"""
import web
import simplejson

from infogami.core import db, auth
from infogami.utils import delegate
from infogami.utils.context import context
from infogami.plugins.pages import code as pages
from infogami import tdb

def error(code, message):
    return dict(code=code, message=message)
    
def permission_denied(path, action):
    return error('/api/status/permission_denied', 
        'Permission denied for action %s on path "%s"' % (action, path))
        
def has_permission(site, path, action):
    modes = dict(read='view', write='edit')
    user = auth.get_user(site)
    return (user # no access for anonymous users
        and not path.startswith('user/') # protect user emails from robots
        and auth.has_permission(site, user, path, modes[action])) # real permission check
    
def input():
    """Reads JSON data from a POST request."""
    def stringify(d):
        if isinstance(d, dict):
            return dict([(str(k), stringify(v)) for k, v in d.items()])
        else:
            return d
            
    try:
        d = simplejson.loads(web.data())
        return stringify(d)
    except:
        print error('/api/status/baddata', 'Expecting JSON input')        
        raise StopIteration
        
def jsonify(f):
    """Decorator to support json."""
    def g(*a, **kw):
        try:
            if web.ctx.path == "/api/account/login" or \
                auth.has_permission(context.site, context.user, web.ctx.path[1:], "view"):
                web.header('Content-Type', 'text/plain')
                result = f(*a, **kw)
            else:            
                result = permission_denied('*', 'api')
                
            if 'code' not in result:
                result['code'] = '/api/status/ok'
        except Exception, e:
            import traceback
            traceback.print_exc()
            result = dict(code='/api/status/internal_error', message=str(e))
        print simplejson.dumps(result)
        raise StopIteration
    return g
    
class read(delegate.page):
    path = "/api/service/read"
    
    @jsonify
    def GET(self, site):
        queries = web.input("queries").queries
        queries = simplejson.loads(queries)
        
        result = {}
        # there could be multiple queries
        for key, q in queries.items():
            try:
                name = q['name'] # query with name is supported.
                if has_permission(site, name, 'read'):
                    thing = db.get_version(site, name)
                    result[key] = dict(code='/api/status/ok', result=pages.thing2dict(thing))
                else:
                    result[key] = permission_denied(name, 'read')
            except tdb.NotFound:
                result[key] = dict(code='/api/status/notfound', name=name)
                
        return result

class write(delegate.page):
    path = "/api/service/write"
    
    @jsonify
    def POST(self, site):
        queries = input()
        
        #TODO: validate data
        
        # only one query is supported in write service
        key, q = queries.items()[0]
        if 'create' in q:
            result = {}
            result[key] = self.create(site, key, q)
            return result
        else:
            return error('/api/status/error', 'Expecting key: create')
        
    def create(self, site, key, q):
        """Creates a new version of a page.
        As of now, there is no dictionction between create and update.
        """
        q = pages.storify(q)
        if has_permission(site, q.name, 'write'):
            page = pages._savepage(q, create_dependents=False)
            result = pages.thing2dict(page)
            result['create'] = 'created'
            return result
        else:
            return permission_denied(q.name, 'write')

class login(delegate.page):
    path = "/api/account/login"
    
    @jsonify
    def POST(self, site):
        i = web.input()
        if 'username' not in i or 'password' not in i:
            return error('/api/status/baddata', 'Expecting username and password.')
        
        # this sets the required cookie 
        user = auth.login(site, i.username, i.password)
        if user:
            return dict(code='/api/status/ok')
        else:
            return error('/api/status/error', 'Incorrect username or password.')
