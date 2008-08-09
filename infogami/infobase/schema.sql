$def with (prefixes, sequences, multisite=False)

BEGIN;

$if multisite:
    create table site (
        id serial primary key,
        name text UNIQUE,
        created timestamp default(current_timestamp at time zone 'utc')
    );

create table thing (
    id serial primary key,
    $if multisite:
        site_id int references site,
    key text,
    type int references thing,   
    latest_revision int default 1,
    last_modified timestamp default(current_timestamp at time zone 'utc'),
    created timestamp default(current_timestamp at time zone 'utc')
);
$for name in ['key', 'type', 'latest_revision', 'last_modified', 'created']:
    create index thing_${name}_idx ON thing($name);

$if multisite:
    create index thing_site_id_idx ON thing(site_id);

create table version (
    thing_id int references thing,
    revision int,
    comment text,
    machine_comment text,
    ip inet,
    author_id int references thing,
    created timestamp default (current_timestamp at time zone 'utc'),
    PRIMARY KEY (thing_id, revision)
);
$for name in ['author_id', 'ip', 'created']:
    create index version_${name}_idx ON version($name);

create table account (
    $if multisite:
        site_id int references site,
    thing_id int references thing,
    email text,
    password text,
    $if multisite:
        UNIQUE(site_id, email)
    $else:
        UNIQUE(email)
);
create index account_thing_id_idx ON account(thing_id);

create table data (
    thing_id int references thing,
    revision int,
    data text
);
create index data_thing_id_revision_idx ON data(thing_id, revision);

$ sqltypes = dict(int="int", float="float", boolean="boolean", str="varchar(2048)", ref="int references thing")

$for prefix in prefixes:
    -- $prefix tables --
    $ keys_table = prefix + '_keys'
    create table $keys_table (
        id serial primary key,
        key text
    );
    CREATE FUNCTION get_${prefix}_key(integer) RETURNS text AS 'select key FROM ${prefix}_keys where id=$$1;' LANGUAGE SQL;
    $for datatype in sqltypes:
        $ name = prefix + "_" + datatype
        create table $name (
            thing_id int references thing,
            key_id int references $keys_table,
            value $sqltypes[datatype],
            ordering int default NULL
        );
        create index ${name}_idx ON ${name}(key_id, value);
        create index ${name}_thing_id_idx ON ${name}(thing_id);
        
    CREATE VIEW ${prefix}_view AS 
    $for i, datatype in enumerate(sqltypes):
        $if i:
            UNION \
        $if datatype == 'boolean':
            SELECT thing_id, get_${prefix}_key(key_id) as key, '$datatype' as datatype, cast(cast(value as int) as text), ordering FROM ${prefix}_${datatype}
        $else:
            SELECT thing_id, get_${prefix}_key(key_id) as key, '$datatype' as datatype, cast(value as text), ordering FROM ${prefix}_${datatype}
    ;
        

-- sequences --
$for seq in sequences:
    CREATE SEQUENCE $seq;

COMMIT;

