"""Infobase server to expose the API.
"""
import web
import infobase
import _json as simplejson
import time
from infobase import config

import common
import cache

def setup_remoteip():
    web.ctx.ip = web.ctx.env.get('HTTP_X_REMOTE_IP', web.ctx.ip)

urls = (
    "/([^/]*)/get", "withkey",
    "/([^/]*)/get_many", "get_many",
    '/([^/]*)/save(/.*)', 'save',
    '/([^/]*)/save_many', 'save_many',
    "/([^/]*)/new_key", "new_key",
    "/([^/]*)/things", "things",
    "/([^/]*)/versions", "versions",
    "/([^/]*)/write", "write",
    "/([^/]*)/account/(.*)", "account",
    "/([^/]*)/permission", "permission",
)

app = web.application(urls, globals())

app.add_processor(web.loadhook(setup_remoteip))
app.add_processor(web.loadhook(cache.loadhook))
app.add_processor(web.loadhook(cache.unloadhook))

def process_exception(e):
    if isinstance(e, common.InfobaseException):
        status = e.status
    else:
        status = "500 Internal Server Error"

    msg = str(e)
    raise web.HTTPError(status, {}, msg)

def jsonify(f):
    def g(self, *a, **kw):
        if not web.ctx.get('infobase_localmode'):
            cookies = web.cookies(infobase_auth_token=None)
            web.ctx.infobase_auth_token = cookies.infobase_auth_token
                
        try:
            d = f(self, *a, **kw)
        except common.InfobaseException, e:
            if web.ctx.get('infobase_localmode'):
                raise
            
            process_exception(e)
        except Exception, e:
            common.record_exception()
            # call web.internalerror to send email when web.internalerror is set to web.emailerrors
            web.internalerror()
            
            if web.ctx.get('infobase_localmode'):
                raise common.InfobaseException(str(e))
            else:
                process_exception(e)
        
        result = simplejson.dumps(d)

        if web.ctx.get('infobase_localmode'):
            return result
        else:
            # set auth-token as cookie for remote connection.
            if web.ctx.get('infobase_auth_token'):
                web.setcookie('infobase_auth_token', web.ctx.infobase_auth_token)
            return result
    return g    
    
def input(*required, **defaults):
    if 'infobase_input' in web.ctx:
        d = web.ctx.infobase_input
    else:
        d = web.input()
        
    for k in required:
        if k not in d:
            raise MissingArgument(k)
            
    result = web.storage(defaults)
    result.update(d)
    return result
    
def to_int(value, key):
    try:
        return int(value)
    except:
        raise common.BadData("Bad integer value for %s: %s" % (repr(key), repr(value)))
        
def assert_key(key):
    rx = web.re_compile(r'^/([^ ]*[^/])?$')
    if not rx.match(key):
        raise common.BadData("Invalid key: %s" % repr(key))
        
def from_json(s):
    try:
        return simplejson.loads(s)
    except ValueError, e:
        raise common.BadData("Bad JSON: " + str(e))
        
_infobase = None
def get_site(sitename):
    import config
    global _infobase
    if not _infobase:
        import dbstore
        schema = dbstore.Schema()
        store = dbstore.DBStore(schema)
        _infobase = infobase.Infobase(store, config.secret_key)
    return _infobase.get(sitename)

class write:
    @jsonify
    def POST(self, sitename):
        site = get_site(sitename)
        i = input('query', comment=None, machine_comment=None, action=None)
        query = from_json(i.query)
        result = site.write(query, comment=i.comment, machine_comment=i.machine_comment, action=i.action)
        return result

class withkey:
    @jsonify
    def GET(self, sitename):
        i = input("key", revision=None, expand=False)
        site = get_site(sitename)
        revision = i.revision and to_int(i.revision, "revision")
        assert_key(i.key)
        thing = site.withKey(i.key, revision=revision)
        if not thing:
            raise common.NotFound(i.key)
        return thing.format_data()

class get_many:
    @jsonify
    def GET(self, sitename):
        i = input("keys")
        keys = from_json(i['keys'])
        site = get_site(sitename)
        things = site.get_many(keys)
        return things

class save:
    @jsonify
    def POST(self, sitename, key):
        #@@ This takes payload of json instead of form encoded data.
        data = web.ctx.infobase_input
        data = from_json(data)

        comment = data.pop('_comment', None)
        machine_comment = data.pop('_machine_comment', None)
        site = get_site(sitename)
        return site.save(key, data, comment=comment, machine_comment=machine_comment)

class save_many:
    @jsonify
    def POST(self, sitename):
        i = input('query', comment=None, machine_comment=None, action=None)
        data = from_json(i.query)
        site = get_site(sitename)
        return site.save_many(data, comment=i.comment, machine_comment=i.machine_comment, action=i.action)
        
class new_key:
    @jsonify
    def GET(self, sitename):
        i = input('type')
        site = get_site(sitename)
        return site.new_key(i.type)

class things:
    @jsonify
    def GET(self, sitename):
        site = get_site(sitename)
        i = input('query', details="false")
        q = from_json(i.query)
        result = site.things(q)
        
        if i.details == "false":
            return [r['key'] for r in result]
        else:
            return result

class versions:
    @jsonify
    def GET(self, sitename):
        site = get_site(sitename)
        i = input('query')
        q = from_json(i.query)
        return site.versions(q)
        
class permission:
    @jsonify
    def GET(self, sitename):
        site = get_site(sitename)
        i = input('key')
        return site.get_permissions(i.key)
        
class account:
    """Code for handling /account/.*"""
    def get_method(self):
        if web.ctx.get('infobase_localmode'):
            return web.ctx.infobase_method
        else:
            return web.ctx.method
        
    @jsonify
    def delegate(self, sitename, method):
        site = get_site(sitename)
        methodname = "%s_%s" % (self.get_method(), method)
        
        m = getattr(self, methodname, None)
        if m:
            return m(site)
        else:
            raise web.notfound()
        
    GET = POST = delegate

    def POST_login(self, site):
        i = input('username', 'password')
        a = site.get_account_manager()
        user = a.login(i.username, i.password)
        if user:
            return user.format_data()
        else:
            raise common.BadData('Invalid username or password')

    def POST_register(self, site):
        i = input('username', 'password', 'email')
        a = site.get_account_manager()
        username = i.pop('username')
        password = i.pop('password')
        email = i.pop('email')
        a.register(username=username, email=email, password=password, data=i)
        return ""

    def GET_get_user(self, site):
        a = site.get_account_manager()
        user = a.get_user()
        if user:
            d = user.format_data()
            d['email'] = a.get_email(user)
            return d

    def GET_get_reset_code(self, site):
        i = input('email')
        a = site.get_account_manager()
        username, code = a.get_user_code(i.email)
        return dict(username=username, code=code)
        
    def GET_get_user_email(self, site):
        i = input('username')
        a = site.get_account_manager()
        email = a.get_user_email(i.username)
        return dict(email=email)

    def POST_reset_password(self, site):
        i = input('username', 'code', 'password')
        a = site.get_account_manager()
        return a.reset_password(i.username, i.code, i.password)
    
    def POST_update_user(self, site):
        i = input('old_password', new_password=None, email=None)
        a = site.get_account_manager()
        return a.update_user(i.old_password, i.new_password, i.email)
        
def request(path, method, data):
    """Fakes the web request.
    Useful when infobase is not run as a separate process.
    """    
    web.ctx.infobase_localmode = True
    web.ctx.infobase_input = data or {}
    web.ctx.infobase_method = method
    
    try:
        # hack to make cache work for local infobase connections
        cache.loadhook()
            
        for pattern, classname in web.group(urls, 2):
            m = web.re_compile('^' + pattern + '$').match(path)
            if m:
                args = m.groups()
                cls = globals()[classname]
                tocall = getattr(cls(), method)
                return tocall(*args)
        raise web.notfound()
    finally:
        # hack to make cache work for local infobase connections
        cache.unloadhook()
        
def run():
    app.run()
