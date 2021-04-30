import web
import simplejson
from six import iteritems, string_types, text_type

from infogami.infobase import account, common


def get_thing(store, key, revision=None):
    if isinstance(key, common.Reference):
        key = text_type(key)
    json_data = store.get(key, revision)
    return json_data and common.Thing.from_json(store, key, json_data)


class PermissionEngine:
    """Engine to check if a user has permission to modify a document."""

    def __init__(self, store):
        self.store = store
        self.things = {}

    def get_thing(self, key):
        try:
            return self.things[key]
        except KeyError:
            t = get_thing(self.store, key)
            self.things[key] = t
            return t

    def has_permission(self, author, key):
        # admin user can modify everything
        if author and author.key == account.get_user_root() + 'admin':
            return True

        permission = self.get_permission(key)
        if permission is None:
            return True
        else:
            groups = permission.get('writers') or []
            # admin users can edit anything
            groups = groups + [self.get_thing('/usergroup/admin')]
            for group in groups:
                if group.key == '/usergroup/everyone':
                    return True
                elif author is not None:
                    members = [m.key for m in group.get('members', [])]
                    if group.key == '/usergroup/allusers' or author.key in members:
                        return True
                else:
                    return False

    def get_permission(self, key):
        """Returns permission for the specified key."""

        def parent(key):
            if key == "/":
                return None
            else:
                return key.rsplit('/', 1)[0] or "/"

        def _get_permission(key, child_permission=False):
            if key is None:
                return None
            thing = self.get_thing(key)
            if child_permission:
                permission = thing and (
                    thing.get("child_permission") or thing.get("permission")
                )
            else:
                permission = thing and thing.get("permission")
            return permission or _get_permission(parent(key), child_permission=True)

        return _get_permission(key)


class SaveProcessor:
    def __init__(self, store, author):
        self.store = store
        self.author = author
        self.permission_engine = PermissionEngine(self.store)

        self.things = {}

        self.types = {}

        self.key = None

    def process_many(self, docs):
        keys = [doc['key'] for doc in docs]
        self.things = dict(
            (doc['key'], common.Thing.from_dict(self.store, doc['key'], doc))
            for doc in docs
        )

        def parse_type(value):
            if isinstance(value, string_types):
                return value
            elif isinstance(value, dict) and 'key' in value:
                return value['key']
            else:
                return None

        # for verifying expected_type, type of the referenced objects is required.
        # Finding the the types in one shot instead of querying each one separately.
        for doc in docs:
            self.types[doc['key']] = parse_type(doc.get('type'))
        refs = list(k for k in self.find_references(docs) if k not in self.types)
        self.types.update(self.find_types(refs))

        prev_data = self.get_many(keys)
        docs = [
            self._process(doc['key'], doc, prev_data.get(doc['key'])) for doc in docs
        ]

        return [doc for doc in docs if doc]

    def find_types(self, keys):
        types = {}

        if keys:
            d = self.store.get_metadata_list(keys)
            type_ids = list(set(row.type for row in d.values()))
            typedict = self.store.get_metadata_list_from_ids(type_ids)

            for k, row in d.items():
                types[k] = typedict[row.type].key
        return types

    def find_references(self, d, result=None):
        if result is None:
            result = set()

        if isinstance(d, dict):
            if len(d) == 1 and d.keys() == ["key"]:
                result.add(d['key'])
            else:
                for k, v in iteritems(d):
                    if k != "type":
                        self.find_references(v, result)
        elif isinstance(d, list):
            for v in d:
                self.find_references(v, result)
        return result

    def get_thing(self, key):
        try:
            return self.things[key]
        except KeyError:
            t = get_thing(self.store, key)
            self.things[key] = t
            return t

    def get_type(self, key):
        try:
            return self.types[key]
        except KeyError:
            t = get_thing(self.store, key)
            return t and t.type.key

    def get_many(self, keys):
        d = self.store.get_many_as_dict(keys)
        return dict((k, simplejson.loads(json_data)) for k, json_data in d.items())

    def process(self, key, data):
        prev_data = self.get_many([key])
        return self._process(key, data, prev_data.get(key))

    def _process(self, key, data, prev_data=None):
        self.key = key  # hack to make key available when raising exceptions.

        if 'key' not in data:
            data['key'] = key

        if web.ctx.get('infobase_bootstrap', False):
            return data

        assert data['key'] == key

        data = common.parse_query(data)
        self.validate_properties(data)
        prev_data = prev_data and common.parse_query(prev_data)

        if not web.ctx.get(
            'disable_permission_check', False
        ) and not self.has_permission(self.author, key):
            raise common.PermissionDenied(
                message='Permission denied to modify %s' % repr(key)
            )

        type = data.get('type')
        if type is None:
            raise common.BadData(message="missing type", at=dict(key=key))
        type = self.process_value(type, self.get_property(None, 'type'))
        type = self.get_thing(type)

        # when type is changed, consider as all object is modified and don't compare with prev data.
        if prev_data and prev_data.get('type') != type.key:
            prev_data = None

        data = self.process_data(data, type, prev_data)

        for k in common.READ_ONLY_PROPERTIES:
            data.pop(k, None)
            prev_data and prev_data.pop(k, None)

        if data == prev_data:
            return None
        else:
            return data

    def has_permission(self, author, key):
        return self.permission_engine.has_permission(author, key)

    def get_property(self, type, name):
        if name == 'type':
            return web.storage(
                name='type',
                expected_type=web.storage(key='/type/type', kind="regular"),
                unique=True,
            )
        elif name in ['permission', 'child_permission']:
            return web.storage(
                name=name,
                expected_type=web.storage(key='/type/permission', kind="regular"),
                unique=True,
            )
        else:
            for p in type.get('properties', []):
                if p.get('name') == name:
                    return p

    def validate_properties(self, data):
        rx = web.re_compile('^[a-z][a-z0-9_]*$')
        for key in data:
            if not rx.match(key):
                raise common.BadData(
                    message="Bad Property: %s" % repr(key), at=dict(key=self.key)
                )

    def process_data(self, d, type, old_data=None, prefix=""):
        for k, v in list(d.items()):  # Avoid dictionary changed size during iteration
            if v in (None, []) or web.safeunicode(v).strip() == '':
                del d[k]
            else:
                if old_data and old_data.get(k) == v:
                    continue
                p = self.get_property(type, k)
                if p:
                    d[k] = self.process_value(v, p, prefix=prefix)
                else:
                    d[k] = v
        if type:
            d['type'] = common.Reference(type.key)

        return d

    def process_value(self, value, property, prefix=""):
        unique = property.get('unique', True)
        expected_type = property.expected_type.key

        at = {"key": self.key, "property": prefix + property.name}

        if isinstance(value, list):
            if unique is True:
                raise common.BadData(
                    message='expected atom, found list', at=at, value=value
                )

            p = web.storage(property.copy())
            p.unique = True
            return [self.process_value(v, p) for v in value]

        if unique is False:
            raise common.BadData(
                message='expected list, found atom', at=at, value=value
            )

        type_found = common.find_type(value)

        if expected_type in common.primitive_types:
            # string can be converted to any type and int can be converted to float
            try:
                if type_found == '/type/string' and expected_type != '/type/string':
                    value = common.primitive_types[expected_type](value)
                elif type_found == '/type/int' and expected_type == '/type/float':
                    value = float(value)
            except ValueError as e:
                raise common.BadData(message=str(e), at=at, value=value)
        elif property.expected_type.kind == 'embeddable':
            if isinstance(value, dict):
                return self.process_data(
                    value, property.expected_type, prefix=at['property'] + "."
                )
            else:
                raise common.TypeMismatch(expected_type, type_found, at=at, value=value)
        else:
            if type_found == '/type/string':
                value = common.Reference(value)

        type_found = common.find_type(value)

        if type_found == '/type/object':
            type_found = self.get_type(value)

            # type is not found only when the thing id not found.
            if type_found is None:
                raise common.NotFound(key=text_type(value), at=at)

        if expected_type != type_found:
            raise common.BadData(
                message='expected %s, found %s'
                % (property.expected_type.key, type_found),
                at=at,
                value=value,
            )
        return value


class WriteQueryProcessor:
    def __init__(self, store, author):
        self.store = store
        self.author = author

    def process(self, query):
        p = SaveProcessor(self.store, self.author)

        for q in serialize(query):
            q = common.parse_query(q)

            if not isinstance(q, dict) or q.get('key') is None:
                continue

            key = q['key']
            thing = get_thing(self.store, key)
            create = q.pop('create', None)

            if thing is None:
                if create:
                    q = self.remove_connects(q)
                else:
                    raise common.NotFound(key=key)
            else:
                q = self.connect_all(thing._data, q)

            yield p.process(key, q)

    def remove_connects(self, query):
        for k, v in query.items():
            if isinstance(v, dict) and 'connect' in v:
                if 'key' in v:
                    value = v['key'] and common.Reference(v['key'])
                else:
                    value = v['value']
                query[k] = value
        return query

    def connect_all(self, data, query):
        """Applies all connects specified in the query to data.

        >>> p = WriteQueryProcessor(None, None)
        >>> data = {'a': 'foo', 'b': ['foo', 'bar']}

        >>> query = {'a': {'connect': 'update', 'value': 'bar'}, 'b': {'connect': 'insert', 'value': 'foobar'}}
        >>> p.connect_all(data, query)
        {'a': 'bar', 'b': ['foo', 'bar', 'foobar']}

        >>> query = {'a': {'connect': 'update', 'value': 'bar'}, 'b': {'connect': 'delete', 'value': 'foo'}}
        >>> p.connect_all(data, query)
        {'a': 'bar', 'b': ['bar']}

        >>> query = {'a': {'connect': 'update', 'value': 'bar'}, 'b': {'connect': 'update_list', 'value': ['foo', 'foobar']}}
        >>> p.connect_all(data, query)
        {'a': 'bar', 'b': ['foo', 'foobar']}
        """
        import copy

        data = copy.deepcopy(data)

        for k, v in query.items():
            if isinstance(v, dict):
                if 'connect' in v:
                    if 'key' in v:
                        value = v['key'] and common.Reference(v['key'])
                    else:
                        value = v['value']
                    self.connect(data, k, v['connect'], value)
        return data

    def connect(self, data, name, connect, value):
        """Modifies the data dict by performing the specified connect.

        >>> getdata = lambda: {'a': 'foo', 'b': ['foo', 'bar']}
        >>> p = WriteQueryProcessor(None, None)

        >>> p.connect(getdata(), 'a', 'update', 'bar')
        {'a': 'bar', 'b': ['foo', 'bar']}
        >>> p.connect(getdata(), 'b', 'update_list', ['foobar'])
        {'a': 'foo', 'b': ['foobar']}
        >>> p.connect(getdata(), 'b', 'insert', 'foobar')
        {'a': 'foo', 'b': ['foo', 'bar', 'foobar']}
        >>> p.connect(getdata(), 'b', 'insert', 'foo')
        {'a': 'foo', 'b': ['foo', 'bar']}
        >>> p.connect(getdata(), 'b', 'delete', 'foobar')
        {'a': 'foo', 'b': ['foo', 'bar']}
        """
        if connect == 'update' or connect == 'update_list':
            data[name] = value
        elif connect == 'insert':
            if value not in data[name]:
                data[name].append(value)
        elif connect == 'delete':
            if value in data[name]:
                data[name].remove(value)
        return data


def serialize(query):
    """TODO: Remove this line and fix doctests below."""
    # fmt: off
    r"""Serializes a nested query such that each subquery acts on a single object.

        >>> q = {
        ...     'create': 'unless_exists',
        ...     'key': '/foo',
        ...     'type': '/type/book',
        ...     'author': {
        ...        'create': 'unless_exists',
        ...        'key': '/bar',
        ...     },
        ...     'descption': {'value': 'foo', 'type': '/type/text'}
        ... }
        >>> serialize(q)
        [{
            'create': 'unless_exists',
            'key': '/bar'
        }, {
            'author': {
                'key': '/bar'
            },
            'create': 'unless_exists',
            'descption': {
                'type': '/type/text',
                'value': 'foo'
            },
            'key': '/foo',
            'type': '/type/book'
        }]
        >>> q = {
        ...     'create': 'unless_exists',
        ...     'key': '/foo',
        ...     'authors': {
        ...         'connect': 'update_list',
        ...         'value': [{
        ...             'create': 'unless_exists',
        ...             'key': '/a/1'
        ...         }, {
        ...             'create': 'unless_exists',
        ...             'key': 'a/2'
        ...         }]
        ...     }
        ... }
        >>> serialize(q)
        [{
            'create': 'unless_exists',
            'key': '/a/1'
        }, {
            'create': 'unless_exists',
            'key': 'a/2'
        }, {
            'authors': {
                'connect': 'update_list',
                'value': [{
                    'key': '/a/1'
                }, {
                    'key': 'a/2'
                }]
            },
            'create': 'unless_exists',
            'key': '/foo'
        }]
    """
    # fmt: on

    def flatten(query, result, path=[], from_list=False):
        """This does two things.
            1. It flattens the query and appends it to result.
        2. It returns its minimal value to use in parent query.
        """
        if isinstance(query, list):
            data = [
                flatten(q, result, path + [str(i)], from_list=True)
                for i, q in enumerate(query)
            ]
            return data
        elif isinstance(query, dict):
            # @@ FIX ME
            q = query.copy()
            for k, v in q.items():
                q[k] = flatten(v, result, path + [k])

            if 'key' in q:
                result.append(q)

            if from_list:
                # @@ quick fix
                if 'key' in q:
                    data = {'key': q['key']}
                else:
                    # take keys (connect, key, type, value) from q
                    data = dict(
                        (k, v)
                        for k, v in q.items()
                        if k in ("connect", "key", "type", "value")
                    )
            else:
                # take keys (connect, key, type, value) from q
                data = dict(
                    (k, v)
                    for k, v in q.items()
                    if k in ("connect", "key", "type", "value")
                )
            return data
        else:
            return query

    result = []
    flatten(query, result)
    return result


if __name__ == "__main__":
    import doctest

    doctest.testmod()
