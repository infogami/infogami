"""Infobase server to expose the API.
"""

from __future__ import print_function

__version__ = "0.5dev"

import json
import logging
import os
import sys
import time

import web

from infogami.infobase import cache, common, config, dbstore, infobase, logreader
from infogami.infobase.account import get_user_root

logger = logging.getLogger("infobase")

def setup_remoteip():
    web.ctx.ip = web.ctx.env.get('HTTP_X_REMOTE_IP', web.ctx.ip)

urls = (
    "/", "server",
    "/_echo", "echo",
    r"/([^_/][^/]*)", "db",
    r"/([^/]*)/get", "withkey",
    r"/([^/]*)/get_many", "get_many",
    r'/([^/]*)/save(/.*)', 'save',
    r'/([^/]*)/save_many', 'save_many',
    r"/([^/]*)/reindex", "reindex",
    r"/([^/]*)/new_key", "new_key",
    r"/([^/]*)/things", "things",
    r"/([^/]*)/versions", "versions",
    r"/([^/]*)/write", "write",
    r"/([^/]*)/account/(.*)", "account",
    r"/([^/]*)/permission", "permission",
    r"/([^/]*)/log/(\d\d\d\d-\d\d-\d\d:\d+)", "readlog",
    r"/([^/]*)/_store/(_.*)", "store_special",
    r"/([^/]*)/_store/(.*)", "store",
    r"/([^/]*)/_seq/(.*)", "seq",
    r"/([^/]*)/_recentchanges", "recentchanges",
    r"/([^/]*)/_recentchanges/(\d+)", "change",
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
    def __init__(self, json_data):
        self.json_data = json_data

def jsonify(f):
    def g(self, *a, **kw):
        t_start = time.time()
        web.ctx.setdefault("headers", [])

        if not web.ctx.get('infobase_localmode'):
            cookies = web.cookies(infobase_auth_token=None)
            web.ctx.infobase_auth_token = cookies.infobase_auth_token

        try:
            d = f(self, *a, **kw)
        except common.InfobaseException as e:
            if web.ctx.get('infobase_localmode'):
                raise

            process_exception(e)
        except Exception as e:
            logger.error("Error in processing request %s %s", web.ctx.get("method", "-"), web.ctx.get("path","-"), exc_info=True)

            common.record_exception()
            # call web.internalerror to send email when web.internalerror is set to web.emailerrors
            process_exception(common.InfobaseException(error="internal_error", message=str(e)))

            if web.ctx.get('infobase_localmode'):
                raise common.InfobaseException(message=str(e))
            else:
                process_exception(e)

        # use default=str to deal with TypeError: datetime is not JSON serializable
        result = d.json_data if isinstance(d, JSON) else json.dumps(d, default=str)
        t_end = time.time()
        totaltime = t_end - t_start
        querytime = web.ctx.pop('querytime', 0.0)
        queries = web.ctx.pop('queries', 0)

        if config.get("enabled_stats"):
            web.header("X-STATS", "tt: %0.3f, tq: %0.3f, nq: %d" % (totaltime, querytime, queries))

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
        return json.loads(s)
    except ValueError as e:
        raise common.BadData(message="Bad JSON: " + str(e))

_infobase = None
def get_site(sitename):
    global _infobase
    if not _infobase:
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
            return {"ok": "true"}

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
        print(web.data(), file=web.debug)
        return {'ok': True}

class write:
    @jsonify
    def POST(self, sitename):
        site = get_site(sitename)
        i = input('query', comment=None, action=None)
        query = from_json(i.query)
        result = site.write(query, comment=i.comment, action=i.action)
        return result

class withkey:
    @jsonify
    def GET(self, sitename):
        i = input("key", revision=None, expand=False)
        site = get_site(sitename)
        revision = i.revision and to_int(i.revision, "revision")
        json_data = site.get(i.key, revision=revision)
        if not json_data:
            raise common.NotFound(key=i.key)
        return JSON(json_data)

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
        data = from_json(get_data())

        comment = data.pop('_comment', None)
        action = data.pop('_action', None)
        _data = data.pop('_data', None)

        site = get_site(sitename)
        return site.save(key, data, comment=comment, action=action, data=_data)

class save_many:
    @jsonify
    def POST(self, sitename):
        i = input('query', comment=None, data=None, action=None)
        docs = from_json(i.query)
        data = i.data and from_json(i.data)
        site = get_site(sitename)
        return site.save_many(docs, comment=i.comment, data=data, action=i.action)

class reindex:
    @jsonify
    def POST(self, sitename):
        i = input("keys")
        keys = json.loads(i['keys'])
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

class recentchanges:
    @jsonify
    def GET(self, sitename):
        site = get_site(sitename)
        i = input('query')
        q = from_json(i.query)
        return site.recentchanges(q)

class change:
    @jsonify
    def GET(self, sitename, id):
        site = get_site(sitename)
        return site.get_change(int(id))

class permission:
    @jsonify
    def GET(self, sitename):
        site = get_site(sitename)
        i = input('key')
        return site.get_permissions(i.key)

class store_special:
    def GET(self, sitename, path):
        if path == '_query':
            return self.GET_query(sitename)
        else:
            raise web.notfound("")

    def POST(self, sitename, path):
        if path == '_save_many':
            return self.POST_save_many(sitename)
        else:
            raise web.notfound("")

    @jsonify
    def POST_save_many(self, sitename):
        store = get_site(sitename).get_store()
        docs = json.loads(get_data())
        store.put_many(docs)

    @jsonify
    def GET_query(self, sitename):
        i = input(type=None, name=None, value=None, limit=100, offset=0, include_docs="false")

        i.limit = common.safeint(i.limit, 100)
        i.offset = common.safeint(i.offset, 0)

        store = get_site(sitename).get_store()
        return store.query(
            type=i.type,
            name=i.name,
            value=i.value,
            limit=i.limit,
            offset=i.offset,
            include_docs=i.include_docs.lower()=="true")

class store:
    @jsonify
    def GET(self, sitename, path):
        store = get_site(sitename).get_store()
        json_data = store.get_json(path)
        if not json_data:
            raise common.NotFound(error="notfound", key=path)
        return JSON(json_data)

    @jsonify
    def PUT(self, sitename, path):
        store = get_site(sitename).get_store() 
        doc = json.loads(get_data())
        store.put(path, doc)
        return JSON('{"ok": true}')

    @jsonify
    def DELETE(self, sitename, path):
        store = get_site(sitename).get_store()
        store.delete(path)
        return JSON('{"ok": true}')

class seq:
    @jsonify
    def GET(self, sitename, name):
        seq = get_site(sitename).get_seq()
        return {"name": name, "value": seq.get_value(name)}

    @jsonify
    def POST(self, sitename, name):
        seq = get_site(sitename).get_seq()
        return {"name": name, "value": seq.next_value(name)}

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
        status = a.login(i.username, i.password)

        if status == "ok":
            a.set_auth_token(get_user_root() + i.username)
            return {"ok": True}
        else:
            raise common.BadData(code=status, message="Login failed")

    def POST_register(self, site):
        i = input('username', 'password', 'email')
        a = site.get_account_manager()
        username = i.pop('username')
        password = i.pop('password')
        email = i.pop('email')

        activation_code = a.register(username=username, email=email, password=password, data=i)
        return {"activation_code": activation_code, "email": email}

    def POST_activate(self, site):
        i = input('username')

        a = site.get_account_manager()
        status = a.activate(i.username)
        if status == "ok":
            return {"ok": "true"}
        else:
            raise common.BadData(error_code=status, message="Account activation failed.")

    def POST_update(self, site):
        i = input('username')
        username = i.pop("username")

        a = site.get_account_manager()
        status = a.update(username, **i)

        if status == "ok":
            return {"ok": "true"}
        else:
            raise common.BadData(error_code=status, message="Account activation failed.")

    def GET_find(self, site):
        i = input(email=None, username=None)
        a = site.get_account_manager()
        return a.find_account(email=i.email, username=i.username)

    def GET_get_user(self, site):
        a = site.get_account_manager()
        user = a.get_user()
        if user:
            d = user.format_data()
            username = d['key'].split("/")[-1]
            d['email'] = a.find_account(username=username)['email']
            return d

    def GET_get_reset_code(self, site):
        # TODO: remove this
        i = input('email')
        a = site.get_account_manager()
        username, code = a.get_user_code(i.email)
        return dict(username=username, code=code)

    def GET_check_reset_code(self, site):
        # TODO: remove this
        i = input('username', 'code')
        a = site.get_account_manager()
        a.check_reset_code(i.username, i.code)
        return {'ok': True}

    def GET_get_user_email(self, site):
        i = input('username')
        a = site.get_account_manager()
        return a.find_account(username=i.username)

    def GET_find_user_by_email(self, site):
        i = input("email")
        a = site.get_account_manager()
        account = a.find_account(email=i.email)
        return account and account['key'].split("/")[-1]

    def POST_reset_password(self, site):
        # TODO: remove this
        i = input('username', 'code', 'password')
        a = site.get_account_manager()
        return a.reset_password(i.username, i.code, i.password)

    def POST_update_user(self, site):
        i = input('old_password', new_password=None, email=None)
        a = site.get_account_manager()

        user = a.get_user()
        username = user.key.split("/")[-1]

        status = a.login(username, i.old_password)
        if status == "ok":
            kw = {}
            if i.new_password:
                kw['password'] = i.new_password
            if i.email:
                kw['email'] = i.email
            a.update(username, **kw)
        else:
            raise common.BadData(code=status, message="Invalid password")

    def POST_update_user_details(self, site):
        i = input('username')
        username = i.pop('username')

        a = site.get_account_manager()
        return a.update(username, **i)

class readlog:
    def get_log(self, offset, i):
        log = logreader.LogFile(config.writelog)
        log.seek(offset)

        # when the offset is not known, skip_till parameter can be used to query.
        if i.timestamp:
            try:
                timestamp = common.parse_datetime(i.timestamp)
                logreader.LogReader(log).skip_till(timestamp)
            except Exception as e:
                raise web.internalerror(str(e))

        return log

    def assert_valid_json(self, line):
        try:
            json.loads(line)
        except ValueError:
            raise web.BadRequest()

    def valid_json(self, line):
        try:
            json.loads(line)
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

                sep = ""
                for i in range(limit):
                    line = log.readline().strip()
                    if line:
                        if self.valid_json(line):
                            yield sep + line.strip()
                            sep = ",\n"
                        else:
                            print("ERROR: found invalid json before %s" % log.tell(), file=sys.stderr)
                    else:
                        break
                yield '], \n'
                yield '"offset": ' + json.dumps(log.tell()) + "\n}\n"
            except Exception as e:
                print('ERROR:', str(e))

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

        mapping = app.mapping

        # Before web.py<0.36, the mapping is a list and need to be grouped.
        # From web.py 0.36 onwards, the mapping is already grouped.
        # Checking the type to see if we need to group them here.
        if mapping and not isinstance(mapping[0], (list, tuple)):
            mapping = web.group(mapping, 2)

        for pattern, classname in mapping:
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
        dbn, db, user, pw = d.get('engine', 'postgres'), d['database'], d.get('username'), d.get('password') or ''
    else:
        dbn, db, user, pw = d.get('dbn', 'postgres'), d['db'], d.get('user'), d.get('pw') or ''

    if user is None:
        user = os.getenv("USER")

    result = dict(dbn=dbn, db=db, user=user, pw=pw)
    if 'host' in d:
        result['host'] = d['host']
    return result

def start(config_file, *args):
    load_config(config_file)
    # start running the server
    sys.argv = [sys.argv[0]] + list(args)
    run()

def load_config(config_file):
    # load config
    import yaml
    runtime_config = yaml.load(open(config_file)) or {}
    update_config(runtime_config)

def update_config(runtime_config):
    # update config
    for k, v in runtime_config.items():
        setattr(config, k, v)

    # import plugins
    plugins = []
    for p in config.get('plugins') or []:
        plugins.append(__import__(p, None, None, ["x"]))
        logger.info("loading plugin %s", p)

    web.config.db_parameters = parse_db_parameters(config.db_parameters)

    # initialize cache
    cache_params = config.get('cache', {'type': 'none'})
    cache.global_cache = cache.create_cache(**cache_params)

    # init plugins
    for p in plugins:
        m = getattr(p, 'init_plugin', None)
        m and m()
