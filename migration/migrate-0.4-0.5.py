"""Script to migrate data from 0.4 to 0.5
"""
from __future__ import print_function
from optparse import OptionParser
import os, sys
import web

DATATYPES = ["str", "int", "float", "boolean", "ref"]


def parse_args():
    parser = OptionParser("Usage: %s [options] db" % sys.argv[0])

    user = os.getenv('USER')
    parser.add_option(
        "-u",
        "--user",
        dest="user",
        default=user,
        help="database username (default: %default)",
    )
    parser.add_option(
        "-H",
        "--host",
        dest="host",
        default='localhost',
        help="database host (default: %default)",
    )
    parser.add_option(
        "-p",
        "--password",
        dest="pw",
        default='',
        help="database password (default: %default)",
    )

    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error("incorrect number of arguments")

    web.config.db_parameters = dict(
        dbn='postgres', db=args[0], user=options.user, pw=options.pw, host=options.host
    )


db = None

PROPERTY_TABLE = """
create table property (
    id serial primary key,
    type int references thing,
    name text,
    unique(type, name)
);
"""

TRANSACTION_TABLE = """
create table transaction (
    id serial primary key,
    action varchar(256),
    author_id int references thing,
    ip inet,
    comment text,
    created timestamp default (current_timestamp at time zone 'utc')    
);
"""

TRANSACTION_INDEXES = """
create index transaction_author_id_idx ON transaction(author_id);
create index transaction_ip_idx ON transaction(ip);
create index transaction_created_idx ON transaction(created);
"""

# @@ type to table prefix mappings.
# @@ If there are any special tables in your schema, this should be updated.
type2table = {}  # type: ignore

# exclusive properties. They are some property names, which can't occur with any other type.
exclusive_properties = {
    '/type/type': [
        'properties.name',
        'properties.expected_type',
        'properties.unique',
        'properties.description',
        'kind',
    ],
    '/type/user': ['displayname'],
    '/type/usergroup': ['members'],
    '/type/permission': ['readers', 'writers', 'admins'],
}


def get_table_prefix(type):
    """Returns table prefix for that type and a boolean flag to specify whether the table has more than one type.
    When the table as values only from a single type, then some of the queries can be optimized.
    """
    table = type2table.get(type, 'datum')
    multiple = (table == 'datum') or type2table.values().count(table) > 1
    return table, multiple


def fix_property_keys():
    """In 0.4, property keys are stored in $prefix_keys table where as in 0.5
    they are stored in a single `property` which also has type column.

    for t in types:
        prefix = table_prefix(t)
        copy_
    """

    def fix_type(type, type_id):
        print('fixing type', type, file=web.debug)
        prefix, multiple_types = get_table_prefix(type)
        keys_table = prefix + "_keys"
        keys = dict((r.key, r.id) for r in db.query('SELECT * FROM ' + keys_table))
        newkeys = {}

        # @@ There is a chance that we may overwrite one update with another when new id is in the same range of old ids.
        # @@ Example:
        # @@     UPDATE datum_str SET key_id=4 FROM thing WHERE thing.id = property.type AND key_id=1;
        # @@     UPDATE datum_str SET key_id=6 FROM thing WHERE thing.id = property.type AND key_id=4;
        # @@ In the above example, the second query overwrites the result of first query.
        # @@ Making id of property table more than max_id of datum_keys makes sure that this case never happen.
        id1 = db.query('SELECT max(id) as x FROM ' + keys_table)[0].x
        id2 = db.query('SELECT max(id) as x FROM property')[0].x
        print('max ids', id1, id2, file=web.debug)
        if id1 > id2:
            db.query("SELECT setval('property_id_seq', $id1)", vars=locals())

        for key in keys:
            newkeys[key] = db.insert('property', type=type_id, name=key)

        total_updated = {}

        for d in ['str', 'int', 'float', 'boolean', 'ref']:
            table = prefix + '_' + d
            print('fixing', type, table, file=web.debug)
            for key in keys:
                old_key_id = keys[key]
                new_key_id = newkeys[key]
                if multiple_types:
                    updated = db.query(
                        'UPDATE %s SET key_id=$new_key_id FROM thing WHERE thing.id = %s.thing_id AND thing.type=$type_id AND key_id=$old_key_id'
                        % (table, table),
                        vars=locals(),
                    )
                else:
                    updated = db.update(
                        table,
                        key_id=new_key_id,
                        where='key_id=$old_key_id',
                        vars=locals(),
                    )

                total_updated[key] = total_updated.get(key, 0) + updated
                print('updated', updated, file=web.debug)

        unused = [k for k in total_updated if total_updated[k] == 0]
        print('unused', unused, file=web.debug)
        db.delete('property', where=web.sqlors('id =', [newkeys[k] for k in unused]))

    primitive = [
        '/type/key',
        '/type/int',
        '/type/float',
        '/type/boolean',
        '/type/string',
        '/type/datetime',
    ]
    # add embeddable types too
    primitive += ['/type/property', '/type/backreference', '/type/link']
    types = dict(
        (r.key, r.id)
        for r in db.query("SELECT * FROM thing WHERE type=1")
        if r.key not in primitive
    )

    for type in types:
        fix_type(type, types[type])


def drop_key_id_foreign_key():
    table_prefixes = set(type2table.values() + ['datum'])
    for prefix in table_prefixes:
        for d in DATATYPES:
            table = prefix + '_' + d
            db.query('ALTER TABLE %s DROP CONSTRAINT %s_key_id_fkey' % (table, table))


def add_key_id_foreign_key():
    table_prefixes = ['datum']
    for prefix in table_prefixes:
        for d in DATATYPES:
            table = prefix + '_' + d
            db.query(
                'ALTER TABLE %s ADD CONSTRAINT %s_key_id_fkey FOREIGN KEY (key_id) REFERENCES property(id)'
                % (table, table)
            )


def get_datum_tables():
    prefixes = ["datum"]
    datatypes = ["str", "int", "float", "boolean", "ref"]
    return [p + "_" + d for p in prefixes for d in datatypes]


def process_keys(table):
    prefix = table.rsplit("_", 1)[0]
    keys_table = prefix + "_keys"

    result = db.query(
        "SELECT type, key_id"
        + " FROM thing, %s as datum" % table
        + " WHERE thing.id=datum.thing_id"
        + " GROUP BY type, key_id"
    )

    for r in result:
        print(r)


def fix_version_table():
    """Add transaction table and move columns from version table to transaction table."""
    filename = '/tmp/version.%d.txt' % os.getpid()
    new_filename = filename + ".new"
    db.query('copy version to $filename', vars=locals())
    cmd = (
        """awk -F'\t' 'BEGIN {OFS="\t"}{if ($3 == 1) action = "create"; else action="update"; print $1,action, $4,$5,$6,$8; }' < %s > %s"""
        % (filename, new_filename)
    )
    os.system(cmd)
    db.query(TRANSACTION_TABLE)
    db.query("copy transaction from $new_filename", vars=locals())
    db.query("SELECT setval('transaction_id_seq', (SELECT max(id) FROM transaction))")
    db.query('ALTER TABLE version add column transaction_id int references transaction')
    db.query('UPDATE version set transaction_id=id')
    db.query(TRANSACTION_INDEXES)
    os.system('rm %s %s' % (filename, new_filename))


def main():
    parse_args()
    global db
    db = web.database(**web.config.db_parameters)
    db.printing = True

    t = db.transaction()
    db.query(PROPERTY_TABLE)
    fix_version_table()

    drop_key_id_foreign_key()
    fix_property_keys()
    add_key_id_foreign_key()
    t.commit()


if __name__ == "__main__":
    main()
