"""Core datastructures for Infogami.
"""
import copy

import simplejson
import web

from six import iteritems, text_type


class InfobaseException(Exception):
    status = "500 Internal Server Error"

    def __init__(self, **kw):
        self.status = kw.pop('status', self.status)
        kw.setdefault('error', 'unknown')
        self.d = kw
        Exception.__init__(self)

    def __str__(self):
        return simplejson.dumps(self.d)

    def dict(self):
        return dict(self.d)


class NotFound(InfobaseException):
    status = "404 Not Found"

    def __init__(self, **kw):
        error = kw.pop('error', 'notfound')
        InfobaseException.__init__(self, error=error, **kw)


class UserNotFound(InfobaseException):
    status = "404 Not Found"

    def __init__(self, **kw):
        InfobaseException.__init__(self, error='user_notfound', **kw)


class PermissionDenied(InfobaseException):
    status = "403 Forbidden"

    def __init__(self, **kw):
        InfobaseException.__init__(self, error='permission_denied', **kw)


class BadData(InfobaseException):
    status = "400 Bad Request"

    def __init__(self, **kw):
        InfobaseException.__init__(self, error='bad_data', **kw)


class Conflict(InfobaseException):
    status = "409 Conflict"

    def __init__(self, **kw):
        InfobaseException.__init__(self, error="conflict", **kw)


class TypeMismatch(BadData):
    def __init__(self, type_expected, type_found, **kw):
        BadData.__init__(
            self, message="expected %s, found %s" % (type_expected, type_found), **kw
        )


class Text(text_type):
    """Python type for /type/text."""

    def __repr__(self):
        return "<text: %s>" % text_type.__repr__(self)


class Reference(text_type):
    """Python type for reference type."""

    def __repr__(self):
        return "<ref: %s>" % text_type.__repr__(self)


class Thing:
    def __init__(self, store, key, data):
        self._store = store
        self.key = key
        self._data = data

    def _process(self, value):
        if isinstance(value, list):
            return [self._process(v) for v in value]
        elif isinstance(value, dict):
            return web.storage((k, self._process(v)) for k, v in iteritems(value))
        elif isinstance(value, Reference):
            json_data = self._store.get(value)
            return Thing.from_json(self._store, text_type(value), json_data)
        else:
            return value

    def __contains__(self, key):
        return key in self._data

    def __getitem__(self, key):
        return self._process(self._data[key])

    def __setitem__(self, key, value):
        self._data[key] = value

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __eq__(self, other):
        return (
            getattr(other, 'key', None) == self.key
            and getattr(other, '_data', None) == self._data
        )

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __repr__(self):
        return "<thing: %s>" % repr(self.key)

    def copy(self):
        return Thing(self._store, self.key, self._data.copy())

    def _get_data(self):
        return copy.deepcopy(self._data)

    def format_data(self):
        from infogami.infobase import common

        return common.format_data(self._get_data())

    def get_property(self, name):
        for p in self.get('properties', []):
            if p.get('name') == name:
                return p

    @staticmethod
    def from_json(store, key, data):
        return Thing.from_dict(store, key, simplejson.loads(data))

    @staticmethod
    def from_dict(store, key, data):
        from infogami.infobase import common

        data = common.parse_query(data)
        return Thing(store, key, data)


class Store:
    """Storage for Infobase.

    Store manages one or many SiteStores.
    """

    def create(self, sitename):
        """Creates a new site with the given name and returns store for it."""
        raise NotImplementedError

    def get(self, sitename):
        """Returns store object for the given sitename."""
        raise NotImplementedError

    def delete(self, sitename):
        """Deletes the store for the specified sitename."""
        raise NotImplementedError


class SiteStore:
    """Interface for Infobase data storage"""

    def get(self, key, revision=None):
        raise NotImplementedError

    def new_key(self, type, kw):
        """Generates a new key to create a object of specified type.
        The store guarantees that it never returns the same key again.
        Optional keyword arguments can be specified to give more hints
        to the store in generating the new key.
        """
        import uuid

        return '/' + str(uuid.uuid1())

    def get_many(self, keys):
        return [self.get(key) for key in keys]

    def write(
        self,
        query,
        timestamp=None,
        comment=None,
        machine_comment=None,
        ip=None,
        author=None,
    ):
        raise NotImplementedError

    def things(self, query):
        raise NotImplementedError

    def versions(self, query):
        raise NotImplementedError

    def get_user_details(self, key):
        """Returns a storage object with user email and encrypted password."""
        raise NotImplementedError

    def update_user_details(self, key, email, enc_password):
        """Update user's email and/or encrypted password."""
        raise NotImplementedError

    def find_user(self, email):
        """Returns the key of the user with the specified email."""
        raise NotImplementedError

    def register(self, key, email, encrypted):
        """Registers a new user."""
        raise NotImplementedError

    def transact(self, f):
        """Executes function f in a transaction."""
        raise NotImplementedError

    def initialize(self):
        """Initializes the store for the first time.
        This is called before doing the bootstrap.
        """
        pass

    def set_cache(self, cache):
        pass


class Event:
    """Infobase Event.

    Events are fired when something important happens (write, new account etc.).
    Some code can listen to the events and do some action (like logging, updating external cache etc.).
    """

    def __init__(self, sitename, name, timestamp, ip, username, data):
        """Creates a new event.

        sitename - name of the site where the event is triggered.
        name - name of the event
        timestamp - timestamp of the event
        ip - client's ip address
        username - current user
        data - additional data of the event
        """
        self.sitename = sitename
        self.name = name
        self.timestamp = timestamp
        self.ip = ip
        self.username = username
        self.data = data
