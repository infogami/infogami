$def with (tables, sequences, multisite=False)

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
    created timestamp default(current_timestamp at time zone 'utc'),
    last_modified timestamp default(current_timestamp at time zone 'utc')
);
$for name in ['key', 'type', 'latest_revision', 'last_modified', 'created']:
    create index thing_${name}_idx ON thing($name);

$if multisite:
    create index thing_site_id_idx ON thing(site_id);

create table transaction (
    id serial primary key,
    action varchar(256),
    author_id int references thing,
    ip inet,
    comment text,
    machine_comment text,
    created timestamp default (current_timestamp at time zone 'utc')    
);

$for name in ['author_id', 'ip', 'created']:
    create index transaction_${name}_idx ON transaction($name);

create table version (
    id serial primary key,
    thing_id int references thing,
    revision int,
    txn_id int references transaction,
    UNIQUE (thing_id, revision)
);

create table property (
    id serial primary key,
    type int references thing,
    name text,
    UNIQUE (type, name)
);

CREATE FUNCTION get_property_name(integer, integer) 
RETURNS text AS 
'select property.name FROM property, thing WHERE thing.type = property.type AND thing.id=$$1 AND property.id=$$2;'
LANGUAGE SQL;

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

$ sqltypes = dict(int="int", float="float", boolean="boolean", str="varchar(2048)", datetime='datetime', ref="int references thing")

$for table, datatype in tables:
    create table $table (
        thing_id int references thing,
        key_id int references property,
        value $sqltypes[datatype],
        ordering int default NULL
    );
    create index ${table}_idx ON ${table}(key_id, value);
    create index ${table}_thing_id_idx ON ${table}(thing_id);
    
-- sequences --
$for seq in sequences:
    CREATE SEQUENCE $seq;

COMMIT;

