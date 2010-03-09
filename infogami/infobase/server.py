"""Infobase server to expose the API.
"""
__version__ = "0.5dev"

import sys
import web
import infobase
import _json as simplejson
import time
from infobase import config

import common
import cache
import logreader

def setup_remoteip():
    web.ctx.ip = web.ctx.env.get('HTTP_X_REMOTE_IP', web.ctx.ip)

urls = (
    "/", "server",
    "/_echo", "echo",
    "/([^/]*)", "db",
    "/([^/]*)/get", "withkey",
    "/([^/]*)/get_many", "get_many",
    '/([^/]*)/save(/.*)', 'save',
    '/([^/]*)/save_many', 'save_many',
    "/([^/]*)/reindex", "reindex",    
    "/([^/]*)/new_key", "new_key",
    "/([^/]*)/things", "things",
    "/([^/]*)/versions", "versions",
    "/([^/]*)/write", "write",
    "/([^/]*)/account/(.*)", "account",
    "/([^/]*)/permission", "permission",
    "/([^/]*)/log/(\d\d\d\d-\d\d-\d\d:\d+)", 'readlog',
    "/_invalidate", "invalidate"
)

app = web.application(urls, globals(), autoreload=False)

app.add_processor(web.loadhook(setup_remoteip))
app.add_processor(web.loadhook(cache.loadhook))
app.add_processor(web.unloadhook(cache.unloadhook))

def process_exception(e):
    if isinstance(e, common.InfobaseException):
        status = e.status
    else:
        status = "500 Internal Server Error"

    msg = str(e)
    raise web.HTTPError(status, {}, msg)
    
class JSON:
    """JSON marker. instances of this class not escaped by jsonify.
    """
    def __init__(self, json):
        self.json = json

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
            process_exception(common.InfobaseException(error="internal_error", message=str(e)))
            
            if web.ctx.get('infobase_localmode'):
                raise common.InfobaseException(message=str(e))
            else:
                process_exception(e)
        
        if isinstance(d, JSON):
            result = d.json
        else:
            result = simplejson.dumps(d)

        if web.ctx.get('infobase_localmode'):
            return result
        else:
            # set auth-token as cookie for remote connection.
            if web.ctx.get('infobase_auth_token'):
                web.setcookie('infobase_auth_token', web.ctx.infobase_auth_token)
            return result
    return g
    
def get_data():
    if 'infobase_input' in web.ctx:
        return web.ctx.infobase_input
    else:
        return web.data()
    
def input(*required, **defaults):
    if 'infobase_input' in web.ctx:
        d = web.ctx.infobase_input
    else:
        d = web.input()
        
    for k in required:
        if k not in d:
            raise common.BadData(message="Missing argument: " + repr(k))
            
    result = web.storage(defaults)
    result.update(d)
    return result
    
def to_int(value, key):
    try:
        return int(value)
    except:
        raise common.BadData(message="Bad integer value for %s: %s" % (repr(key), repr(value)))
        
def from_json(s):
    try:
        return simplejson.loads(s)
    except ValueError, e:
        raise common.BadData(message="Bad JSON: " + str(e))
        
_infobase = None
def get_site(sitename):
    import config
    global _infobase
    if not _infobase:
        import dbstore
        schema = dbstore.default_schema or dbstore.Schema()
        store = dbstore.DBStore(schema)
        _infobase = infobase.Infobase(store, config.secret_key)
    return _infobase.get(sitename)
    
class server:
    @jsonify
    def GET(self):
        return {"infobase": "welcome", "version": __version__}
        
class db:
    @jsonify
    def GET(self, name):
        site = get_site(name)
        if site is None:
            raise common.NotFound(error="db_notfound", name=name)
        else:
            return {"name": site.sitename}
        
    @jsonify
    def PUT(self, name):
        site = get_site(name)
        if site is not None:
            raise web.HTTPError("412 Precondition Failed", {}, "")
        else:
            site = _infobase.create(name)
            return {"ok": True}
            
    @jsonify
    def DELETE(self, name):
        site = get_site(name)
        if site is None:
            raise common.NotFound(error="db_notfound", name=name)
        else:
            site.delete()
            return {"ok": True}

class echo:
    @jsonify
    def POST(self):
        print >> web.debug, web.data()
        return {'ok': True}

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
        json = site.get(i.key, revision=revision)
        if not json:
            raise common.NotFound(key=i.key)
        return JSON(json)

class get_many:
    @jsonify
    def GET(self, sitename):
        i = input("keys")
        keys = from_json(i['keys'])
        site = get_site(sitename)
        return JSON(site.get_many(keys))

class save:
    @jsonify
    def POST(self, sitename, key):
        #@@ This takes payload of json instead of form encoded data.
        data = get_data()
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

class reindex:
    @jsonify
    def POST(self, sitename):
        i = input("keys")
        keys = simplejson.loads(i['keys'])
        site = get_site(sitename)
        site.store.reindex(keys)
        return {"status": "ok"}
        
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
        
        if i.details.lower() == "false":
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
        
        if not user:
            raise common.BadData(message='Invalid username or password')
        elif config.verify_user_email and user.get('verified') is False:
            raise common.BadData(message="User is not verified")
        else:
            return user.format_data()

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
        
    def GET_check_reset_code(self, site):
        i = input('username', 'code')
        a = site.get_account_manager()
        a.check_reset_code(i.username, i.code)
        return {'ok': True}
        
    def GET_get_user_email(self, site):
        i = input('username')
        a = site.get_account_manager()
        email = a.get_user_email(i.username)
        return dict(email=email)
        
    def GET_find_user_by_email(self, site):
        i = input("email")
        a = site.get_account_manager()
        username = a.find_user_by_email(i.email)
        return username

    def POST_reset_password(self, site):
        i = input('username', 'code', 'password')
        a = site.get_account_manager()
        return a.reset_password(i.username, i.code, i.password)
    
    def POST_update_user(self, site):
        i = input('old_password', new_password=None, email=None)
        a = site.get_account_manager()
        return a.update_user(i.old_password, i.new_password, i.email)
        
    def POST_update_user_details(self, site):
        i = input('username')
        username = i.pop('username')
        
        a = site.get_account_manager()
        return a.update_user_details(username, **i)

class readlog:
    def get_log(self, offset, i):
        log = logreader.LogFile(config.writelog)
        log.seek(offset)
        
        # when the offset is not known, skip_till parameter can be used to query.
        if i.timestamp:
            try:
                timestamp = common.parse_datetime(i.timestamp)
                logreader.LogReader(log).skip_till(timestamp)
            except Exception, e:
                raise web.internalerror(str(e))
        
        return log
        
    def assert_valid_json(self, line):
        try:
            simplejson.loads(line)
        except ValueError:
            raise web.BadRequest()
            
    def valid_json(self, line):
        try:
            simplejson.loads(line)
            return True
        except ValueError:
            return False
        
    def GET(self, sitename, offset):
        i = web.input(timestamp=None, limit=1000)
        
        if not config.writelog:
            raise web.notfound("")
        else:
            log = self.get_log(offset, i)
            limit = min(1000, common.safeint(i.limit, 1000))
            
            try:                
                web.header('Content-Type', 'application/json')
                yield '{"data": [\n'
                
                for i in range(limit):
                    line = log.readline().strip()
                    if line:
                        if self.valid_json(line):
                            yield ",\n" + line.strip()
                        else:
                            print >> sys.stderr, "ERROR: found invalid json before %s" % log.tell()
                    else:
                        break
                yield '], \n'
                yield '"offset": ' + simplejson.dumps(log.tell()) + "\n}\n"
            except Exception, e:
                print 'ERROR:', str(e)
                
def request(path, method, data):
    """Fakes the web request.
    Useful when infobase is not run as a separate process.
    """
    web.ctx.infobase_localmode = True
    web.ctx.infobase_input = data or {}
    web.ctx.infobase_method = method
    
    def get_class(classname):
        if '.' in classname:
            modname, classname = classname.rsplit('.', 1)
            mod = __import__(modname, None, None, ['x'])
            fvars = mod.__dict__
        else:
            fvars = globals()
        return fvars[classname]

    try:
        # hack to make cache work for local infobase connections
        cache.loadhook()

        for pattern, classname in web.group(app.mapping, 2):
            m = web.re_compile('^' + pattern + '$').match(path)
            if m:
                args = m.groups()
                cls = get_class(classname)
                tocall = getattr(cls(), method)
                return tocall(*args)
        raise web.notfound()
    finally:
        # hack to make cache work for local infobase connections
        cache.unloadhook()
            
def run():
    app.run()
    
def parse_db_parameters(d):
    if d is None:
        return None

    # support both <engine, database, username, password> and <dbn, db, user, pw>.
    if 'database' in d:
        dbn, db, user, pw = d.get('engine', 'postgres'), d['database'], d['username'], d.get('password') or ''
    else:
        dbn, db, user, pw = d.get('dbn', 'postgres'), d['db'], d['user'], d.get('pw') or ''
     
    result = dict(dbn=dbn, db=db, user=user, pw=pw)
    if 'host' in d:
        result['host'] = d['host']
    return result
    
def start(config_file, *args):
    # load config
    import yaml
    runtime_config = yaml.load(open(config_file)) or {}

    # update config
    for k, v in runtime_config.items():
        setattr(config, k, v)
        
    # import plugins
    plugins = []
    for p in config.get('plugins') or []:
        plugins.append(__import__(p, None, None, ["x"]))
        print >> web.debug, "loaded plugin", p
        
    web.config.db_parameters = parse_db_parameters(config.db_parameters)    

    # initialize cache
    cache_params = config.get('cache', {'type': 'none'})
    cache.global_cache = cache.create_cache(**cache_params)
    
    # init plugins
    for p in plugins:
        m = getattr(p, 'init_plugin', None)
        m and m()
        
    # start running the server
    sys.argv = [sys.argv[0]] + list(args)
    run()
