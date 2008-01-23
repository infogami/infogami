types = [
    {
        'create': True,
        'key': 'type/type',
        'name': 'Type',
        'type': {'key': 'type/type'},
        'properties': [
            {
                'create': True,
                'key': 'type/type/properties',
                'name': 'Properties',
                'type': {'key': 'type/property'},
                'expected_type': {'key': 'type/property'},
                'unique': "false"
            },
            {
                'create': True,
                'key': 'type/type/description',
                'name': 'Description',
                'type': {'key': 'type/property'},
                'expected_type': {'key': 'type/text'},
                'unique': "true"
            },
        ],
        'description': {
            'type': 'type/text',
            'value': 'Metatype.\nThis is the type of all types including it self.'
        }
    }, 
    {
        'create': True,
        'key': 'type/property',
        'name': 'Property',
        'type': {'key': 'type/type'},
        'properties': [
            {
                'create': True,
                'key': 'type/property/expected_type',
                'name': 'Expected Type',
                'type': {'key': 'type/property'},
                'expected_type': {'key': 'type/type'},
                'unique': 'true'
            },
            {
                'create': True,
                'key': 'type/property/unique',
                'name': 'Unique',
                'type': {'key': 'type/property'},
                'expected_type': {'key': 'type/boolean'},
                'unique': 'true'
            },
        ],
        'description': {
            'type': 'type/text',
            'value': ''
        }
    },
    {
        'create': True,
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
        'create': True,
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
        'create': True,
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
        'create': True,
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
        'create': True,
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
        'create': True,
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
        'create': True,
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
        'create': True,
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

