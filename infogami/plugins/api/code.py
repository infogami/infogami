"""
Infogami read/write API.
"""
import json
from functools import wraps

import web

import infogami
from infogami.infobase import client
from infogami.utils import delegate, features
from infogami.utils.view import safeint

hooks = {}


def add_hook(name, cls):
    hooks[name] = cls


class api(delegate.page):
    path = "/api/(.*)"

    def delegate(self, suffix):
        # Have an option of setting content-type to text/plain
        i = web.input(_method='GET', text="false")
        if i.text.lower() == "false":
            web.header('Content-type', 'application/json')
        else:
            web.header('Content-type', 'text/plain')

        if suffix in hooks:
            method = web.ctx.method
            cls = hooks[suffix]
            m = getattr(cls(), method, None)
            if m:
                raise web.HTTPError('200 OK', {}, m())
            else:
                web.ctx.status = '405 Method Not Allowed'
        else:
            web.ctx.status = '404 Not Found'

    GET = POST = delegate


def get_custom_headers():
    opt = web.ctx.env.get('HTTP_OPT')
    if opt is None:
        return {}

    rx = web.re_compile(r'"(.*)"; ns=(\d\d)')
    m = rx.match(opt.strip())

    if m:
        decl_uri, ns = m.groups()
        expected_decl_uri = infogami.config.get(
            'http_ext_header_uri', 'http://infogami.org/api'
        )
        if expected_decl_uri == decl_uri:
            prefix = 'HTTP_%s_' % ns
            return {
                web.lstrips(k, prefix).lower(): v
                for k, v in web.ctx.env.items()
                if k.startswith(prefix)
            }
    else:
        return {}


class infobase_request:
    def delegate(self):
        sitename = web.ctx.site.name
        path = web.lstrips(web.ctx.path, "/api")
        method = web.ctx.method
        data = web.input()

        conn = self.create_connection()

        try:
            out = conn.request(sitename, path, method, data)
            return '{"status": "ok", "result": %s}' % out
        except client.ClientException as e:
            return '{"status": "fail", "message": "%s"}' % str(e)

    GET = delegate

    def create_connection(self):
        conn = client.connect(**infogami.config.infobase_parameters)
        auth_token = web.cookies().get(infogami.config.login_cookie_name)
        conn.set_auth_token(auth_token)
        return conn

    def POST(self):
        """RESTful write API."""
        if not can_write():
            raise Forbidden("Permission Denied")

        sitename = web.ctx.site.name
        path = web.lstrips(web.ctx.path, "/api")
        method = "POST"

        query = web.data()
        h = get_custom_headers()
        comment = h.get('comment')
        action = h.get('action')
        data = dict(query=query, comment=comment, action=action)

        conn = self.create_connection()

        try:
            out = conn.request(sitename, path, method, data)
        except client.ClientException as e:
            raise BadRequest(e.json or str(e))

        # @@ this should be done in the connection.
        try:
            if path == "/save_many":
                for q in json.loads(query):
                    web.ctx.site._run_hooks("on_new_version", q)
            elif path == "/write":
                result = json.loads(out)
                for k in result.get('created', []) + result.get('updated', []):
                    web.ctx.site._run_hooks(
                        "on_new_version", request("/get", data=dict(key=k))
                    )
        except Exception as e:
            import traceback

            traceback.print_exc()
        return out


# Earlier read API, for backward-compatability
add_hook("get", infobase_request)
add_hook("things", infobase_request)
add_hook("versions", infobase_request)
add_hook("get_many", infobase_request)

# RESTful write API.
add_hook("write", infobase_request)
add_hook("save_many", infobase_request)


def jsonapi(f):
    @wraps(f)
    def g(*a, **kw):
        try:
            out = f(*a, **kw)
        except client.ClientException as e:
            raise web.HTTPError(e.status, {}, e.json or str(e))

        i = web.input(_method='GET', callback=None)

        if i.callback:
            out = f'{i.callback}({out});'

        if web.input(_method="GET", text="false").text.lower() == "true":
            content_type = "text/plain"
        else:
            content_type = "application/json"

        return delegate.RawText(out, content_type=content_type)

    return g


def request(path, method='GET', data=None):
    return web.ctx.site._conn.request(web.ctx.site.name, path, method=method, data=data)


class Forbidden(web.HTTPError):
    def __init__(self, msg=""):
        web.HTTPError.__init__(self, "403 Forbidden", {}, msg)


class BadRequest(web.HTTPError):
    def __init__(self, msg=""):
        web.HTTPError.__init__(self, "400 Bad Request", {}, msg)


def can_write():
    user = delegate.context.user and delegate.context.user.key
    usergroup = web.ctx.site.get('/usergroup/api') or {}
    usergroup_admin = web.ctx.site.get('/usergroup/admin') or {}
    api_users = usergroup.get('members', []) + usergroup_admin.get('members', [])
    return user in [u.key for u in api_users]


class view(delegate.mode):
    encoding = "json"

    @jsonapi
    def GET(self, path):
        i = web.input(v=None)
        v = safeint(i.v, None)
        data = dict(key=path, revision=v)
        return request('/get', data=data)

    @jsonapi
    def PUT(self, path):
        if not can_write():
            raise Forbidden("Permission Denied.")

        data = web.data()
        h = get_custom_headers()
        comment = h.get('comment')
        if comment:
            data = json.loads(data)
            data['_comment'] = comment
            data = json.dumps(data)

        result = request('/save' + path, 'POST', data)

        # @@ this should be done in the connection.
        web.ctx.site._run_hooks("on_new_version", data)
        return result


def make_query(i, required_keys=None):
    """Removes keys starting with _ and limits the keys to required_keys, if it is specified.

    >>> make_query(dict(a=1, _b=2))
    {'a': 1}
    >>> make_query(dict(a=1, _b=2, c=3), required_keys=['a'])
    {'a': 1}
    """
    query = {}
    for k, v in i.items():
        if k.startswith('_'):
            continue
        if required_keys and k not in required_keys:
            continue
        if v == '':
            v = None
        query[k] = v
    return query


class history(delegate.mode):
    encoding = "json"

    @jsonapi
    def GET(self, path):
        query = make_query(
            web.input(), required_keys=['author', 'ip', 'offset', 'limit']
        )
        query['key'] = path
        query['sort'] = '-created'
        return request('/versions', data=dict(query=json.dumps(query)))


class recentchanges(delegate.page):
    encoding = "json"

    @jsonapi
    def GET(self):
        i = web.input(query=None)
        query = i.pop('query')
        if not query:
            query = json.dumps(
                make_query(
                    i,
                    required_keys=[
                        "key",
                        "type",
                        "author",
                        "ip",
                        "offset",
                        "limit",
                        "bot",
                    ],
                )
            )

        if features.is_enabled("recentchanges_v2"):
            return request('/_recentchanges', data=dict(query=query))
        else:
            return request('/versions', data=dict(query=query))


class query(delegate.page):
    encoding = "json"

    @jsonapi
    def GET(self):
        i = web.input(query=None)
        i.pop("callback", None)
        query = i.pop('query')
        if not query:
            query = json.dumps(make_query(i))
        return request('/things', data=dict(query=query, details="true"))


class login(delegate.page):
    encoding = "json"
    path = "/account/login"

    def POST(self):
        try:
            d = json.loads(web.data())
            web.ctx.site.login(d['username'], d['password'])
            web.setcookie(
                infogami.config.login_cookie_name, web.ctx.conn.get_auth_token()
            )
        except Exception as e:
            raise BadRequest(str(e))
