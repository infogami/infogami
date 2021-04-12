"""Infobase client."""
from __future__ import print_function

import datetime
import logging
import time

import json
import requests
from six import iteritems, string_types, text_type, with_metaclass
from six.moves.http_cookies import SimpleCookie
from six.moves.urllib_parse import urlencode, quote, unquote

import web

from infogami import config
from infogami.infobase import common, server
from infogami.utils import stats


logger = logging.getLogger("infobase.client")

DEBUG = False


def storify(d):
    if isinstance(d, dict):
        for k, v in d.items():
            d[k] = storify(v)
        return web.storage(d)
    elif isinstance(d, list):
        return [storify(x) for x in d]
    else:
        return d


def unstorify(d):
    if isinstance(d, dict):
        return {k: unstorify(v) for k, v in iteritems(d)}
    elif isinstance(d, list):
        return [unstorify(x) for x in d]
    else:
        return d


class ClientException(Exception):
    def __init__(self, status, msg, json_data=None):
        self.status = status
        self.json = json_data
        Exception.__init__(self, msg)

    def get_data(self):
        return json.loads(self.json) if self.json else {}


class NotFound(ClientException):
    def __init__(self, msg):
        ClientException.__init__(self, "404 Not Found", msg)


def connect(type, **params):
    """Connect to infobase server using the given params."""
    for t in _connection_types:
        if type == t:
            return _connection_types[t](**params)
    raise Exception('Invalid connection type: ' + type)


class Connection:
    response_type = "json"

    def __init__(self):
        self.auth_token = None

    def set_auth_token(self, token):
        self.auth_token = token

    def get_auth_token(self):
        return self.auth_token

    def request(self, sitename, path, method='GET', data=None):
        raise NotImplementedError

    def handle_error(self, status, error):
        try:
            data = json.loads(error)
            message = data.get('message', data.get('error', ''))
            json_data = error
        except Exception as e:
            message = error or str(e)
            json_data = None
        raise ClientException(status, message, json_data)


class LocalConnection(Connection):
    """LocalConnection assumes that db_parameters are set in web.config."""

    def __init__(self, **params):
        Connection.__init__(self)
        pass

    def request(self, sitename, path, method='GET', data=None):
        path = "/" + sitename + path
        web.ctx.infobase_auth_token = self.get_auth_token()
        try:
            stats.begin("infobase", path=path, method=method, data=data)
            out = server.request(path, method, data)
            stats.end()
            if 'infobase_auth_token' in web.ctx:
                self.set_auth_token(web.ctx.infobase_auth_token)
        except common.InfobaseException as e:
            stats.end(error=True)
            self.handle_error(e.status, str(e))
        return out


class RemoteConnection(Connection):
    """Connection to remote Infobase server."""

    def __init__(self, base_url):
        Connection.__init__(self)
        self.base_url = base_url

    def request(self, sitename, path, method='GET', data=None):
        url = self.base_url + '/' + sitename + path
        path = '/' + sitename + path
        if isinstance(data, dict):
            for k in list(data):
                if data[k] is None:
                    del data[k]

        if web.config.debug:
            web.ctx.infobase_req_count = 1 + web.ctx.get('infobase_req_count', 0)
            a = time.time()
            _path = path
            _data = data

        headers = {}

        if data:
            if isinstance(data, dict):
                data = dict((web.safestr(k), web.safestr(v)) for k, v in data.items())
                data = urlencode(data)
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            if method == 'GET':
                path += '?' + data
                data = None

        stats.begin("infobase", path=path, method=method, data=data)
        env = web.ctx.get('env') or {}

        if self.auth_token:
            c = SimpleCookie()
            c['infobase_auth_token'] = quote(self.auth_token)
            cookie = c.output(header='').strip()
            headers['Cookie'] = cookie

        # pass the remote ip to the infobase server
        headers['X-REMOTE-IP'] = web.ctx.get('ip') or ''

        try:
            response = requests.request(method, path, data=data, headers=headers)
            if not response.ok:
                response.raise_for_status()
            stats.end()
        except requests.exceptions.HTTPError:
            stats.end(error=True)
            logger.error("Unable to connect to infobase server", exc_info=True)
            raise ClientException(
                "503 Service Unavailable", "Unable to connect to infobase server"
            )

        cookie = response.headers.get('Set-Cookie')
        if cookie:
            c = SimpleCookie()
            c.load(cookie)
            if 'infobase_auth_token' in c:
                auth_token = c['infobase_auth_token'].value
                # The auth token will be in urlquoted form, unquote it before use.
                # Otherwise, it will be quoted twice this value is set as cookie.
                auth_token = auth_token and unquote(auth_token)
                self.set_auth_token(auth_token)

        if web.config.debug:
            b = time.time()
            print(
                "%.02f (%s):" % (round(b - a, 2), web.ctx.infobase_req_count),
                response.status_code,
                method,
                _path,
                _data,
                file=web.debug,
            )

        if response.status_code == 200:
            return response.content
        else:
            self.handle_error(
                "%d %s" % (response.status_code, response.reason), response.content
            )


_connection_types = {'local': LocalConnection, 'remote': RemoteConnection}


class LazyObject:
    """LazyObject which creates the required object on demand.
    >>> o = LazyObject(lambda: [1, 2, 3])
    >>> list(o)
    [1, 2, 3]
    """

    def __init__(self, creator):
        self.__dict__['_creator'] = creator
        self.__dict__['_o'] = None

    def _get(self):
        if self._o is None:
            self._o = self._creator()
        return self._o

    def __getattr__(self, key):
        return getattr(self._get(), key)

    def __iter__(self):
        return self._get().__iter__()


class Site:
    def __init__(self, conn, sitename):
        self._conn = conn
        self.name = sitename
        # cache for storing pages requested in this HTTP request
        self._cache = {}

        self.store = Store(conn, sitename)
        self.seq = Sequence(conn, sitename)

    def _request(self, path, method='GET', data=None):
        out = self._conn.request(self.name, path, method, data)

        # Allow connection to return dict
        if self._conn.response_type != "dict":
            out = json.loads(out)
        return storify(out)

    def _get(self, key, revision=None):
        """Returns properties of the thing with the specified key."""
        revision = revision and int(revision)

        if (key, revision) not in self._cache:
            data = dict(key=key, revision=revision)
            try:
                result = self._request('/get', data=data)
            except ClientException as e:
                if e.status.startswith('404'):
                    raise NotFound(key)
                else:
                    raise
            self._cache[key, revision] = web.storage(common.parse_query(result))

        return self._cache[key, revision]

    def _process(self, value):
        if isinstance(value, list):
            return [self._process(v) for v in value]
        elif isinstance(value, dict):
            d = {}
            for k, v in value.items():
                d[k] = self._process(v)
            return create_thing(self, None, d)
        elif isinstance(value, common.Reference):
            return create_thing(self, text_type(value), None)
        else:
            return value

    def _process_dict(self, data):
        d = {}
        for k, v in data.items():
            d[k] = self._process(v)
        return d

    def _load(self, key, revision=None):
        data = self._get(key, revision)
        data = self._process_dict(data)
        return data

    def _get_backreferences(self, thing):
        def safeint(x):
            try:
                return int(x)
            except ValueError:
                return 0

        if 'env' in web.ctx:
            i = web.input(_method='GET')
        else:
            i = web.storage()
        page_size = 20
        backreferences = {}

        for p in thing.type._getdata().get('backreferences', []):
            offset = page_size * safeint(i.get(p.name + '_page') or '0')
            q = {p.property_name: thing.key, 'offset': offset, 'limit': page_size}
            if p.expected_type:
                q['type'] = p.expected_type.key
            backreferences[p.name] = LazyObject(
                lambda q=q: self.get_many(self.things(q))
            )
        return backreferences

    def exists(self):
        """Returns true if this site exists."""
        try:
            self._request(path="", method="GET")
            return True
        except ClientException as e:
            if e.status.startswith("404"):
                return False
            else:
                raise

    def create(self):
        """Creates this site if not exists."""
        if not self.exists():
            self._request(path="", method="PUT")

    def get(self, key, revision=None, lazy=False):
        assert key.startswith('/'), "key {} does not start with '/'".format(key)

        if lazy:
            data = None
        else:
            try:
                data = self._load(key, revision)
            except NotFound:
                return None
        return create_thing(self, key, data, revision=revision)

    def get_many(self, keys, raw=False):
        """When raw=True, the raw data is returned instead of objects."""
        if not keys:
            return []

        # simple hack to avoid crossing URL length limit.
        if len(keys) > 100:
            things = []
            while keys:
                things += self.get_many(keys[:100], raw=raw)
                keys = keys[100:]
            return things

        data = dict(keys=json.dumps(keys))
        result = self._request('/get_many', data=data)
        things = []

        for key in keys:
            # @@ what if key is not there?
            if key in result:
                data = result[key]
                if raw:
                    things.append(data)
                else:
                    data = web.storage(common.parse_query(data))
                    self._cache[key, None] = data
                    things.append(create_thing(self, key, self._process_dict(data)))
        return things

    def new_key(self, type):
        data = {'type': type}
        result = self._request('/new_key', data=data)
        return result

    def things(self, query, details=False):
        query = json.dumps(query)
        return self._request(
            '/things', 'GET', {'query': query, "details": str(details)}
        )

    def versions(self, query):
        def process(v):
            v = web.storage(v)
            v.created = parse_datetime(v.created)
            v.author = v.author and self.get(v.author, lazy=True)
            return v

        query = json.dumps(query)
        versions = self._request('/versions', 'GET', {'query': query})
        return [process(v) for v in versions]

    def recentchanges(self, query):
        query = json.dumps(query)
        changes = self._request('/_recentchanges', 'GET', {'query': query})
        return [Changeset.create(self, c) for c in changes]

    def get_change(self, id):
        data = self._request('/_recentchanges/%s' % id, 'GET')
        return data and Changeset.create(self, data)

    def write(self, query, comment=None, action=None):
        self._run_hooks('before_new_version', query)
        _query = json.dumps(query)
        result = self._request(
            '/write', 'POST', dict(query=_query, comment=comment, action=action)
        )
        self._run_hooks('on_new_version', query)
        self._invalidate_cache(result.created + result.updated)
        return result

    def save(self, query, comment=None, action=None, data=None):
        query = dict(query)
        self._run_hooks('before_new_version', query)

        query['_comment'] = comment
        query['_action'] = action
        query['_data'] = data
        key = query['key']

        # @@ save sends payload of application/json instead of form data
        data = json.dumps(query)
        result = self._request('/save' + key, 'POST', data)
        if result:
            self._invalidate_cache([result['key']])
            self._run_hooks('on_new_version', query)
        return result

    def save_many(self, query, comment=None, data=None, action=None):
        _query = json.dumps(query)
        # for q in query:
        #    self._run_hooks('before_new_version', q)
        data = data or {}
        result = self._request(
            '/save_many',
            'POST',
            dict(
                query=_query,
                comment=comment,
                action=action,
                data=json.dumps(data),
            ),
        )
        self._invalidate_cache([r['key'] for r in result])
        for q in query:
            self._run_hooks('on_new_version', q)
        return result

    def _invalidate_cache(self, keys):
        for k in keys:
            try:
                del self._cache[k, None]
            except KeyError:
                pass

    def can_write(self, key):
        perms = self._request('/permission', 'GET', dict(key=key))
        return perms['write']

    def _run_hooks(self, name, query):
        if isinstance(query, dict) and 'key' in query:
            key = query['key']
            type = query.get('type')
            # type is none when saving permission
            if type is not None:
                if isinstance(type, dict):
                    type = type['key']
                type = self.get(type)
                data = query.copy()
                data['type'] = type
                t = self.new(key, data)
                # call the global _run_hooks function
                _run_hooks(name, t)

    def login(self, username, password, remember=False):
        return self._request(
            '/account/login', 'POST', dict(username=username, password=password)
        )

    def register(self, username, displayname, email, password):
        data = dict(
            username=username, displayname=displayname, email=email, password=password
        )
        _run_hooks("before_register", data)
        return self._request('/account/register', 'POST', data)

    def activate_account(self, username):
        data = dict(username=username)
        return self._request('/account/activate', 'POST', data)

    def update_account(self, username, **kw):
        """Updates an account."""
        data = dict(kw, username=username)
        return self._request('/account/update', 'POST', data)

    def find_account(self, username=None, email=None):
        """Finds account by username or email."""
        if username is None and email is None:
            return None
        data = dict(username=username, email=email)
        return self._request("/account/find", "GET", data)

    def update_user(self, old_password, new_password, email):
        return self._request(
            '/account/update_user',
            'POST',
            dict(old_password=old_password, new_password=new_password, email=email),
        )

    def update_user_details(self, username, **kw):
        params = dict(kw, username=username)
        return self._request('/account/update_user_details', 'POST', params)

    def find_user_by_email(self, email):
        return self._request('/account/find_user_by_email', 'GET', {'email': email})

    def get_reset_code(self, email):
        """Returns the reset code for user specified by the email.
        This called to send forgot password email.
        This should be called after logging in as admin.
        """
        return self._request('/account/get_reset_code', 'GET', dict(email=email))

    def check_reset_code(self, username, code):
        return self._request(
            '/account/check_reset_code', 'GET', dict(username=username, code=code)
        )

    def get_user_email(self, username):
        return self._request('/account/get_user_email', 'GET', dict(username=username))

    def reset_password(self, username, code, password):
        return self._request(
            '/account/reset_password',
            'POST',
            dict(username=username, code=code, password=password),
        )

    def get_user(self):
        # avoid hitting infobase when there is no cookie.
        if web.cookies().get(config.login_cookie_name) is None:
            return None
        try:
            data = self._request('/account/get_user')
        except ClientException:
            return None

        user = data and create_thing(
            self, data['key'], self._process_dict(common.parse_query(data))
        )
        return user

    def new(self, key, data=None):
        """Creates a new thing in memory."""
        data = common.parse_query(data)
        data = self._process_dict(data or {})
        return create_thing(self, key, data)


class Store:
    """Store to store any arbitrary data.

    This provides a dictionary like interface for storing documents.
    Each document can have an optional type (default is "") and all the (type, name, value) triples are indexed.
    """

    def __init__(self, conn, sitename):
        self.conn = conn
        self.name = sitename

    def _request(self, path, method='GET', data=None):
        out = self.conn.request(self.name, "/_store/" + path, method, data)
        return json.loads(out)

    def delete(self, key):
        return self._request(key, method='DELETE')

    def update(self, d={}, **kw):
        d2 = dict(d, **kw)
        docs = [dict(doc, _key=key) for key, doc in d2.items()]
        self._request("_save_many", method="POST", data=json.dumps(docs))

    def clear(self):
        """Removes all keys from the store. Use this with caution!"""
        for k in self.keys(limit=-1):
            del self[k]

    def query(
        self, type=None, name=None, value=None, limit=100, offset=0, include_docs=False
    ):
        """Returns the  a list of keys matching the given query.
        Sample result:
            [{"key": "a"}, {"key": "b"}, {"key": "c"}]
        """
        if limit == -1:
            return self.unlimited_query(
                type, name, value, offset=offset, include_docs=include_docs
            )

        params = dict(
            type=type,
            name=name,
            value=value,
            limit=limit,
            offset=offset,
            include_docs=str(include_docs),
        )
        params = dict((k, v) for k, v in params.items() if v is not None)
        return self._request("_query", method="GET", data=params)

    def unlimited_query(self, type, name, value, offset=0, include_docs=False):
        while True:
            result = self.query(
                type, name, value, limit=1000, offset=offset, include_docs=include_docs
            )
            if not result:
                break

            offset += len(result)
            for k in result:
                yield k

    def __getitem__(self, key):
        try:
            return self._request(key)
        except ClientException as e:
            if e.status.startswith("404"):
                raise KeyError(key)
            else:
                raise

    def __setitem__(self, key, data):
        return self._request(key, method='PUT', data=json.dumps(data))

    def __delitem__(self, key):
        self.delete(key)

    def __contains__(self, key):
        return bool(self.get(key))

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def iterkeys(self, **kw):
        result = self.query(**kw)
        return (d['key'] for d in result)

    def keys(self, **kw):
        return list(self.iterkeys(**kw))

    def itervalues(self, **kw):
        rows = self.query(include_docs=True, **kw)
        return (row['doc'] for row in rows)

    def values(self, **kw):
        return list(self.itervalues(**kw))
        rows = self.query(**kw)

    def iteritems(self, **kw):
        rows = self.query(include_docs=True, **kw)
        return ((row['key'], row['doc']) for row in rows)

    def items(self, **kw):
        return list(self.iteritems(**kw))


class Sequence:
    """Dynamic sequences.
    Quite similar to sequences in postgres, but there is no need of define anything upfront..

        seq = web.ctx.site.seq
        for i in range(10):
            print(seq.next_value("foo"))
    """

    def __init__(self, conn, sitename):
        self.conn = conn
        self.name = sitename

    def _request(self, path, method='GET', data=None):
        out = self.conn.request(self.name, "/_seq/" + path, method, data)
        return json.loads(out)

    def get_value(self, name):
        return self._request(name, method="GET")['value']

    def next_value(self, name):
        return self._request(name, method="POST", data=" ")['value']


def parse_datetime(datestring):
    """Parses from isoformat.
    Is there any way to do this in stdlib?
    """
    import re, datetime

    tokens = re.split(r'-|T|:|\.| ', datestring)
    return datetime.datetime(*map(int, tokens))


class Nothing:
    """For representing missing values.

    >>> n = Nothing()
    >>> repr(n)
    '<Nothing>'
    >>> str(n)
    ''
    >>> web.safestr(n)
    ''
    >>> str([n])  # See #148 and #151
    '[<Nothing>]'
    """

    def __getattr__(self, name):
        if name.startswith('__') or name == 'next':
            raise AttributeError(name)
        else:
            return self

    def __getitem__(self, name):
        return self

    def __call__(self, *a, **kw):
        return self

    def __add__(self, a):
        return a

    __radd__ = __add__
    __mul__ = __rmul__ = __add__

    def __iter__(self):
        return iter([])

    def __hash__(self):
        return id(self)

    def __len__(self):
        return 0

    def __bool__(self):
        return False

    def __eq__(self, other):
        return isinstance(other, Nothing)

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return "<Nothing>"

    def __str__(self):
        return ""


nothing = Nothing()

_thing_class_registry = {}


def register_thing_class(type, klass):
    _thing_class_registry[type] = klass


def create_thing(site, key, data, revision=None):
    type = None
    try:
        if data is not None and data.get('type'):
            type = data.get('type')

            # @@@ Fix this!
            if isinstance(type, Thing):
                type = type.key
            elif isinstance(type, dict):
                type = type['key']

            # just to be safe
            if not isinstance(type, string_types):
                type = None
    except Exception as e:
        # just for extra safety
        print('ERROR:', str(e), file=web.debug)
        type = None

    klass = _thing_class_registry.get(type) or _thing_class_registry.get(None)
    return klass(site, key, data, revision)


class Thing(object):
    def __init__(self, site, key, data=None, revision=None):
        self._site = site
        self.key = key
        self._revision = revision

        assert data is None or isinstance(data, dict)

        self._data = data
        self._backreferences = None

        # no back-references for embeddable objects
        if self.key is None:
            self._backreferences = {}

    def __hash__(self):
        if self.key:
            return hash(self.key)
        else:
            d = self.dict()
            # dict is not hashable and converting it to tuple of items isn't #
            # enough as values might again be dictionaries. The simplest
            # solution seems to be converting it to JSON.
            return hash(json.dumps(d, sort_keys=True))

    def _getdata(self):
        if self._data is None:
            self._data = self._site._load(self.key, self._revision)

            # @@ Hack: change class based on type
            self.__class__ = _thing_class_registry.get(
                self._data.get('type').key, Thing
            )

        return self._data

    def _get_backreferences(self):
        if self._backreferences is None:
            self._backreferences = self._site._get_backreferences(self)
        return self._backreferences

    def _get_defaults(self):
        return {}

    def keys(self):
        special = ['id', 'revision', 'latest_revision', 'last_modified', 'created']
        return [k for k in self._getdata() if k not in special]

    def get(self, key, default=None):
        try:
            return self._getdata()[key]
        except KeyError:
            # try default-value
            d = self._get_defaults()
            try:
                return d[key]
            except KeyError:
                if 'type' not in self._data:
                    return default
                return self._get_backreferences().get(key, default)

    def __getitem__(self, key):
        return self.get(key, nothing)

    def __setitem__(self, key, value):
        self._getdata()[key] = value

    def __setattr__(self, key, value):
        if key == '__class__':
            object.__setattr__(self, '__class__', value)
        elif key.startswith('_') or key in (
            'key',
            'revision',
            'latest_revision',
            'last_modified',
            'created',
        ):
            self.__dict__[key] = value
        else:
            self._getdata()[key] = value

    def __iter__(self):
        return iter(self._data)

    def _save(self, comment=None, action=None, data=None):
        d = self.dict()
        return self._site.save(d, comment, action=action, data=data)

    def _format(self, d):
        if isinstance(d, dict):
            return {k: self._format(v) for k, v in iteritems(d)}
        elif isinstance(d, list):
            return [self._format(v) for v in d]
        elif isinstance(d, common.Text):
            return {'type': '/type/text', 'value': web.safeunicode(d)}
        elif isinstance(d, Thing):
            return d._dictrepr()
        elif isinstance(d, datetime.datetime):
            return {'type': '/type/datetime', 'value': d.isoformat()}
        else:
            return d

    def dict(self):
        return self._format(self._getdata())

    def _dictrepr(self):
        if self.key is None:
            return self.dict()
        else:
            return {'key': self.key}

    def update(self, data):
        data = common.parse_query(data)
        data = self._site._process_dict(data)
        self._getdata().update(data)

    def __getattr__(self, key):
        if key.startswith('__'):
            raise AttributeError(key)

        # Hack: __class__ of this object can change in _getdata method.
        #
        # Lets say __class__ is changed to A in _getdata and A has method foo.
        # When obj.foo() is called before initializing, foo won't be found because
        # __class__ is not yet set to A. Initialize and call getattr again to get
        # the expected behaviour.
        #
        # @@ Can this ever lead to infinite-recursion?
        if self._data is None:
            self._getdata()  # initialize self._data
            return getattr(self, key)

        return self[key]

    def __eq__(self, other):
        return isinstance(other, Thing) and other.key == self.key

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return web.safestr(self.key)

    def __repr__(self):
        return "{}(site={}, key={}, data={}, revision={})".format(
            self.__class__.__name__, self._site, self.key, self._data, self._revision
        )


class Type(Thing):
    def _get_defaults(self):
        return {"kind": "regular"}

    def get_property(self, name):
        for p in self.properties:
            if p.name == name:
                return p

    def get_backreference(self, name):
        for p in self.backreferences:
            if p.name == name:
                return p


class Changeset:
    def __init__(self, site, data):
        self._site = site
        self._data = data

        self.id = data['id']
        self.kind = data['kind']
        self.timestamp = parse_datetime(data['timestamp'])
        self.comment = data['comment']

        if data['author']:
            self.author = self._site.get(data['author']['key'], lazy=True)
        else:
            self.author = None
        self.ip = data['ip']
        self.changes = data.get('changes') or []
        self.data = web.storage(data['data'])
        self.init()

    def get_comment(self):
        return self.comment

    def get_changes(self):
        return [
            self._site.get(c['key'], c['revision'], lazy=True) for c in self.changes
        ]

    def dict(self):
        return unstorify(self._data)

    def init(self):
        pass

    def url(self):
        kwargs = {
            "year": self.timestamp.year,
            "month": self.timestamp.month,
            "day": self.timestamp.day,
            "kind": self.kind,
            "id": self.id,
        }
        default_format = "/recentchanges/%(year)s/%(month)02d/%(day)02d/%(kind)s/%(id)s"
        format = config.get("recentchanges_view_link_format", default_format)
        return format % kwargs

    def __repr__(self):
        return "<Changeset@%s of kind %s>" % (self.id, self.kind)

    @staticmethod
    def create(site, data):
        kind = data['kind']
        klass = _changeset_class_register.get(kind) or _changeset_class_register.get(
            None
        )
        return klass(site, data)


_changeset_class_register = {}


def register_changeset_class(kind, klass):
    _changeset_class_register[kind] = klass


register_changeset_class(None, Changeset)
register_thing_class(None, Thing)
register_thing_class('/type/type', Type)

# hooks can be registered by extending the hook class
hooks = []


class metahook(type):
    def __init__(self, name, bases, attrs):
        hooks.append(self())
        type.__init__(self, name, bases, attrs)


class hook(with_metaclass(metahook)):
    pass


# remove hook from hooks
hooks.pop()


def _run_hooks(name, thing):
    for h in hooks:
        m = getattr(h, name, None)
        if m:
            m(thing)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
