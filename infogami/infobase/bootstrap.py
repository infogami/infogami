"""Write query to create initial type system.
"""

# primitive types
type_key = {
    'key': 'type/key',
    'name': 'Key',
    'type': 'type/type',
    'properties': [],
    'description': {
        'type': 'type/text',
        'value': 'Type to store keys. A key is a string constrained to the regular expression [a-z][a-z/_]*.'
    }
}

type_string = {
    'key': 'type/string',
    'name': 'String',
    'type': 'type/type',
    'properties': [],
    'description': {
        'type': 'type/text',
        'value': 'Type to store unicode strings up to a maximum length of 2048.'
    }
}

type_text = {
    'key': 'type/text',
    'name': 'Text',
    'type': 'type/type',
    'properties': [],
    'description': {
        'type': 'type/text',
        'value': 'Type to store arbitrary long unicode text. Values of this type are not indexed.'
    }
}

type_uri = {
    'key': 'type/uri',
    'name': 'URI',
    'type': 'type/type',
    'properties': [],
    'description': {
        'type': 'type/text',
        'value': 'Type to store URIs.'
    }
}

type_boolean = {
    'key': 'type/boolean',
    'name': 'Boolean',
    'type': 'type/type',
    'properties': [],
    'description': {
        'type': 'type/text',
        'value': 'Type to store boolean values true and false.'
    }
}

type_int = {
    'key': 'type/int',
    'name': 'Integer',
    'type': 'type/type',
    'properties': [],
    'description': {
        'type': 'type/text',
        'value': '32-bit integer type. This can store integers in the range [-2**32, 2**31-1].'
    }
}

type_float = {
    'key': 'type/float',
    'name': 'Floating Point Number',
    'type': 'type/type',
    'properties': [],
    'description': {
        'type': 'type/text',
        'value': 'Type to store 32-bit floating point values.'
    }
}

type_datatime = {
    'key': 'type/datetime',
    'name': 'Datetime',
    'type': 'type/type',
    'properties': [],
    'description': {
        'type': 'type/text',
        'value': 'Type to store datetimes from 4713 BC to 5874897 AD with 1 millisecond resolution.'
    }
}

# type/property and type/type are special system types.
# Since they are inter-linked, first type/type is created with no properties and then updated.
type_property = {
    'key': 'type/property',
    'name': 'Property',
    'type': 'type/type',
    'properties': [
        {
            'key': 'type/property/name',
            'name': 'Name',
            'type': 'type/property',
            'expected_type': {'key': 'type/string'},
            'unique': {'type': 'type/boolean', 'value': True}
        },
        {
            'key': 'type/property/expected_type',
            'name': 'Expected Type',
            'type': 'type/property',
            'expected_type': {'key': 'type/type'},
            'unique': {'type': 'type/boolean', 'value': True}
        },
        {
            'key': 'type/property/unique',
            'name': 'Unique',
            'type': 'type/property',
            'expected_type': {'key': 'type/boolean'},
            'unique': {'type': 'type/boolean', 'value': True}
        },
    ],
    'description': {
        'type': 'type/text',
        'value': ''
    }
}

type_type = {
    'key': 'type/type',
    'name': 'Type',
    'type': 'type/type',
}

type_type = {
    'key': 'type/type',
    'type': 'type/type',
    'properties': [
        {
            'key': 'type/type/name',
            'name': 'Name',
            'type': 'type/property',
            'expected_type': 'type/string',
            'unique': {'type': 'type/boolean', 'value': True}
        },
        {
            'key': 'type/type/properties',
            'name': 'Properties',
            'type': "type/property",
            'expected_type': 'type/property',
            'unique': {'type': 'type/boolean', 'value': False}
        },
        {
            'key': 'type/type/description',
            'name': 'Description',
            'type': 'type/property',
            'expected_type': "type/text",
            'unique': {'type': 'type/boolean', 'value': True}
        },
    ],
    'description': {
        'connect': 'update',
        'type': 'type/text',
        'value': 'Metatype.\nThis is the type of all types including it self.'
    }
} 

def make_type(key):
    return 

a = [
    {'key': 'type/type', 'type': 'type/type'},
    {'key': 'type/property', 'type': 'type/type'},
    {'key': 'type/key', 'type': 'type/type'},
    {'key': 'type/string', 'type': 'type/type'},
    {'key': 'type/text', 'type': 'type/type'},
    {'key': 'type/int', 'type': 'type/type'},
    {'key': 'type/boolean', 'type': 'type/type'},
    {'key': 'type/float', 'type': 'type/type'},
    {'key': 'type/uri', 'type': 'type/type'},
    {'key': 'type/datetime', 'type': 'type/type'},
]

types = a + [type_property, type_type, type_key, type_string, type_text, type_int, type_boolean, type_float, type_uri, type_datatime]

if __name__ == "__main__":
    import web
    import infobase
    web.config.db_parameters = dict(dbn='postgres', db='infobase', user='anand', pw='')
    web.config.db_printing = True
    web.load()
    
    web.transact()
    site = infobase.Infobase().create_site('foobar')
    import pprint
    pprint.pprint(site.write(types))

    web.commit()
