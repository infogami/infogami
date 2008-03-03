"""Write query to create initial system objects including type system.
"""

# The bootstrap query will contain the following subqueries.
# 
# * create type/type without any properties
# * create all primitive types
# * create type/property and type/backreference
# * update type/type with its properties.
# * create type/user, type/usergroup and type/permission
# * create required usergroup and permission objects.

def metatype():
    """Subquery to create type/type."""
    return {
        'create': 'unless_exists',
        'key': '/type/type',
        'type': '/type/type',
        'name': 'Type',
        'description': {
            'type': '/type/text',
            'value': 'Metatype.\nThis is the type of all types including it self.'
        }
    }
    
def primitive_types():
    """Subqueries to create all primitive types."""
    def q(key, name, description):
        return {
            'create': 'unless_exists',
            'key': key,
            'type': '/type/type',
            'name': name,
            'description': {
                'type': '/type/text',
                'value': description
            }
        }
    return [
        q('/type/key', 'Key', 'Type to store keys. A key is a string constrained to the regular expression [a-z][a-z/_]*.'),
        q('/type/string', 'String', 'Type to store unicode strings up to a maximum length of 2048.'),
        q('/type/text', 'Text', 'Type to store arbitrary long unicode text. Values of this type are not indexed.'),
        q('/type/int', 'Integer', 'Type to store 32-bit integers. This can store integers in the range [-2**32, 2**31-1].'),
        q('/type/boolean', 'Boolean', 'Type to store boolean values true and false.'),
        q('/type/float', 'Floating Point Number', 'Type to store 32-bit floating point numbers'),
        q('/type/uri', 'URI', 'Type to store URIs.'),
        q('/type/datetime', 'Datetime', 'Type to store datetimes from 4713 BC to 5874897 AD with 1 millisecond resolution.'),
    ]

def _property(key, property_name, expected_type, unique):
    return {
        'create': 'unless_exists',
        'key': key + '/' + property_name,
        'type': '/type/property',
        'name': property_name,
        'expected_type': {'key': expected_type},
        'unique': unique
    }

def type_property_and_backreference():
    return [{
        'create': 'unless_exists',
        'key': '/type/property',
        'name': 'Property',
        'type': '/type/type',
        'properties': [
            _property('/type/property', 'name', '/type/string', True),
            _property('/type/property', 'expected_type', '/type/type', True),
            _property('/type/property', 'unique', '/type/boolean', True),
        ],
    }, {
        'create': 'unless_exists',
        'key': '/type/backreference',
        'name': 'Back Reference',
        'type': '/type/type',
        'properties': [
            _property('/type/backreference', 'name', '/type/string', True),
            _property('/type/backreference', 'expected_type', '/type/type', True),
            _property('/type/backreference', 'property_name', '/type/string', True),
        ],
    }]

def update_metatype():
    def p(property_name, expected_type, unique, index):
        q = _property('/type/type', property_name, expected_type, unique)
        q['index'] = index
        return q

    return {
        'key': '/type/type',
        'type': '/type/type',
        'properties': {
            'connect': 'update_list',
            'value': [
                p('name', '/type/string', True, 0),
                p('description', '/type/text', True, 1),
                p('properties', '/type/property', False, 2),
                p('backreferences', '/type/backreference', False, 3),
            ]
        }
    }

def type_user_etal():
    """Query to create type/user, type/usergroup and type/permission."""
    return [{
        'create': 'unless_exists',
        'key': '/type/user',
        'type': '/type/type',
        'properties': [
            _property('/type/user', 'displayname', '/type/string', True),
            _property('/type/user', 'website', '/type/uri', True),
            _property('/type/user', 'description', '/type/text', True),
        ]
    }, {
        'create': 'unless_exists',
        'key': '/type/usergroup',
        'type': '/type/type',
        'properties': [
            _property('/type/usergroup', 'description', '/type/text', True),
            _property('/type/usergroup', 'members', '/type/user', False),
        ]
    }, {
        'create': 'unless_exists',
        'key': '/type/permission',
        'type': '/type/type',
        'properties': [
            _property('/type/permission', 'description', '/type/text', True),
            _property('/type/permission', 'readers', '/type/usergroup', False),
            _property('/type/permission', 'writers', '/type/usergroup', False),
            _property('/type/permission', 'admins', '/type/usergroup', False),
        ]
    }]

def groups_and_permissions():
    def group(key, description):
        return {
            'create': 'unless_exists',
            'key': key,
            'type': '/type/usergroup',
            'description': description
        }
    
    def permission(key, readers, writers, admins):
        return {
            'create': 'unless_exists',
            'key': key,
            'type': '/type/permission',
            'readers': readers,
            'writers': writers,
            'admins': admins
        }
    
    return [
        group('/usergroup/everyone', 'Group of all users including anonymous users.'),
        group('/usergroup/allusers', 'Group of all registred users.'),
        group('/usergroup/admin', 'Group of admin users.'),
        permission('/permission/open', ['/usergroup/everyone'], ['/usergroup/everyone'], ['/usergroup/admin']),
        permission('/permission/restricted', ['/usergroup/everyone'], ['/usergroup/admin'], ['/usergroup/admin']),
        permission('/permission/secret', ['/usergroup/admin'], ['/usergroup/admin'], ['/usergroup/admin']),
    ]

def make_query():
    return [
        metatype(),
        primitive_types(),
        type_property_and_backreference(),
        update_metatype(),
        type_user_etal(),
        groups_and_permissions()
    ]

def bootstrap(site, admin_password):
    """Creates system types and objects for a newly created site.
    """
    import web
    web.ctx.infobase_bootstrap = True
    query = make_query()
    site.write(query)
    a = site.get_account_manager()
    a.register(username="admin", displayname="Administrator", email="admin@example.com", password=admin_password)
    a.register(username="useradmin", displayname="User Administrator", email="useradmin@example.com", password=admin_password)
    