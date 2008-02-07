types = [
    {
        'create': 'unless_exists',
        'key': 'type/type',
        'name': 'Type',
        'type': 'type/type',
        'properties': [{
            'create': 'unless_exists',
            'key': 'type/type/properties',
            'name': 'Properties',
            'type': {
                'create': 'unless_exists',
                'key': 'type/property',
            }
            'expected_type': 'type/property',
            'unique': False
        },
        {
            'create': 'unless_exists',
            'key': 'type/type/description',
            'name': 'Description',
            'type': 'type/property',
            'expected_type': 'type/text',
            'unique': True
        }],
        'description': {
            'type': 'type/text',
            'value': 'Metatype.\nThis is the type of all types including it self.'
        }
    }, 
    {
        'create': 'unless_exists',
        'key': 'type/property',
        'name': 'Property',
        'type': 'type/type',
        'properties': [
            {
                'create': 'unless_exists',
                'key': 'type/property/expected_type',
                'name': 'Expected Type',
                'type': 'type/property',
                'expected_type': {'key': 'type/type'},
                'unique': True
            },
            {
                'create': 'unless_exists',
                'key': 'type/property/unique',
                'name': 'Unique',
                'type': {'key': 'type/property'},
                'expected_type': {'key': 'type/boolean'},
                'unique': True
            },
        ],
        'description': {
            'type': 'type/text',
            'value': ''
        }
    },
    {
        'create': 'unless_exists',
        'key': 'type/key',
        'name': 'Key',
        'type': {'key': 'type/type'},
        'properties': [],
        'description': {
            'type': 'type/text',
            'value': 'Type to store keys. A key is a string constrained to the regular expression [a-z][a-z/_]*.'
        }
    },
    {
        'create': 'unless_exists',
        'key': 'type/string',
        'name': 'String',
        'type': {'key': 'type/type'},
        'properties': [],
        'description': {
            'type': 'type/text',
            'value': 'Type to store unicode strings up to a maximum length of 2048.'
        }
    },
    {
        'create': 'unless_exists',
        'key': 'type/text',
        'name': 'Text',
        'type': {'key': 'type/type'},
        'properties': [],
        'description': {
            'type': 'type/text',
            'value': 'Type to store arbitrary long unicode text. Values of this type are not indexed.'
        }
    },
    {
        'create': 'unless_exists',
        'key': 'type/uri',
        'name': 'URI',
        'type': {'key': 'type/type'},
        'properties': [],
        'description': {
            'type': 'type/text',
            'value': 'Type to store URIs.'
        }
    },
    {
        'create': 'unless_exists',
        'key': 'type/boolean',
        'name': 'Boolean',
        'type': {'key': 'type/type'},
        'properties': [],
        'description': {
            'type': 'type/text',
            'value': 'Type to store boolean values true and false.'
        }
    },
    {
        'create': 'unless_exists',
        'key': 'type/int',
        'name': 'Integer',
        'type': {'key': 'type/type'},
        'properties': [],
        'description': {
            'type': 'type/text',
            'value': '32-bit integer type. This can store integers in the range [-2**32, 2**31-1].'
        }
    },
    {
        'create': 'unless_exists',
        'key': 'type/float',
        'name': 'Floating Point Number',
        'type': {'key': 'type/type'},
        'properties': [],
        'description': {
            'type': 'type/text',
            'value': 'Type to store 32-bit floating point values.'
        }
    },
    {
        'create': 'unless_exists',
        'key': 'type/datetime',
        'name': 'Datetime',
        'type': {'key': 'type/type'},
        'properties': [],
        'description': {
            'type': 'type/text',
            'value': 'Type to store datetimes from 4713 BC to 5874897 AD with 1 millisecond resolution.'
        }
    },
]

