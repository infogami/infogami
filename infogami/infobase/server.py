"""Infobase server to expose the API.
"""
import web
import infobase
import simplejson
import time

urls = (
    "/([^/]*)/get", "withkey",
    "/([^/]*)/things", "things",
    "/([^/]*)/versions", "versions",
    "/([^/]*)/write", "write",
    "/([^/]*)/account/(.*)", "account",
    "/([^/]*)/permission", "permission",
)

def jsonify(f):
    def g(self, *a, **kw):
        t1 = time.time()
        
        d = {'status': 'ok'}
        try:
            d['result'] = f(self, *a, **kw)
        except (infobase.InfobaseException, AssertionError), e:
            import traceback
            traceback.print_exc()
            d['status'] = 'fail'
            d['message'] = str(e)
            d['traceback'] = traceback.format_exc()
        except Exception, e:
            import traceback
            traceback.print_exc()
            d['status'] = 'fail'
            d['message'] = 'InternalError: %s' % str(e)
            d['traceback'] = traceback.format_exc()
        
        t2 = time.time()
        i = input(prettyprint=None, stats=None)
        
        if i.stats:
            d['stats'] = dict(time_taken=t2-t1)

        if i.prettyprint:
            result = simplejson.dumps(d, indent=4)
        else:
            result = simplejson.dumps(d)
        
            
        if web.ctx.get('infobase_localmode'):
            return result
        else:
            web.ctx.output = result
    return g
    
def input(*a, **kw):
    if 'infobase_input' in web.ctx:
        return web.storify(web.ctx.infobase_input, *a, **kw)
    else:
        return web.input(*a, **kw)
    
ibase = None
def get_site(sitename):
    global ibase
    if not ibase:
        ibase = infobase.Infobase()
    return ibase.get_site(sitename)

class write:
    @jsonify
    def POST(self, sitename):
        site = get_site(sitename)
        i = input('query', comment=None, machine_comment=None)
        query = simplejson.loads(i.query)
        result = site.write(query, i.comment, i.machine_comment)
        return result

class withkey:
    @jsonify
    def GET(self, sitename):
        try:
            i = input("key", revision=None, expand=False)
            site = get_site(sitename)
            thing = site.withKey(i.key, revision=i.revision)
            return thing._get_data(expand=i.expand)
        except infobase.NotFound:
            return None
            
class things:
    @jsonify
    def GET(self, sitename):
        site = get_site(sitename)
        i = input('query')
        q = simplejson.loads(i.query)
        return site.things(q)

class versions:
    @jsonify
    def GET(self, sitename):
        site = get_site(sitename)
        i = input('query')
        q = simplejson.loads(i.query)
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
            web.notfound()
            raise StopIteration
        
    GET = POST = delegate

    def POST_login(self, site):
        i = input('username', 'password')
        a = site.get_account_manager()
        user = a.login(i.username, i.password)
        if user:
            return user._get_data()
        else:
            raise infobase.InfobaseException('Invalid username or password')

    def POST_register(self, site):
        i = input('username', 'password', 'displayname', 'email')
        a = site.get_account_manager()
        a.register(username=i.username, displayname=i.displayname, email=i.email, password=i.password)
        return ""

    def GET_get_user(self, site):
        a = site.get_account_manager()
        user = a.get_user()
        return user and user._get_data()

    def GET_get_reset_code(self, site):
        i = input('email')
        a = site.get_account_manager()
        username, code = a.get_user_code(i.email)
        return dict(username=username, code=code)

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
    for pattern, classname in web.group(urls, 2):
        m = web.re_compile('^' + pattern + '$').match(path)
        if m:
            args = m.groups()
            cls = globals()[classname]
            tocall = getattr(cls(), method)
            return tocall(*args)
    return web.notfound()

def run():
    web.run(urls, globals())
    
if __name__ == "__main__":
    web.config.db_parameters = dict(dbn='postgres', db='infobase', user='anand', pw='')
    web.config.db_printing = True
    web.run(urls, globals())
