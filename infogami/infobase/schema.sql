--- infobase schema ---

--- tables ---

CREATE TABLE site (
    id serial primary key,
    name text,
    secret_key text,
    UNIQUE (name)
);

CREATE TABLE thing (
    id serial primary key,
    site_id int references site,
    key varchar(4096),
    latest_revision int,
    deleted boolean DEFAULT false,
    created timestamp default (current_timestamp at time zone 'utc'),
    last_modified timestamp default (current_timestamp at time zone 'utc'),
    UNIQUE (site_id, key)
);

CREATE TABLE version (
    id serial primary key,
    thing_id int references thing,
    revision int,
    author_id int references thing,
    ip inet,
    comment varchar(1024),
    machine_comment varchar(1024),
    created timestamp default (current_timestamp at time zone 'utc'),
    unique (thing_id, revision)
);

CREATE TABLE datum (
    thing_id int references thing,
    begin_revision int,
    end_revision int default 2147483647, -- MAX_INT: 2**31 -1 
    key text,
    value text,
    datatype int, --- 0: reference, 1: key, 2: string, 3: text, 4: uri, 5: boolean, 6: int, 7: float, 8: datatime
    ordering int default null,
    CHECK(key ~ '^[a-z][a-z0-9/_]*$')
);

CREATE TABLE account (
    thing_id int references thing,
    email text,
    password text
);

--- index ---

CREATE INDEX version_created_idx ON version (created);
CREATE INDEX version_comment_idx ON version (comment) where comment is not NULL;
CREATE INDEX version_machine_comment_idx ON version (machine_comment);
CREATE INDEX version_author_id_idx ON version (author_id) where author_id is not NULL;

CREATE FUNCTION text2timestap(text) RETURNS timestamp AS $$
    SELECT CAST($1 AS TIMESTAMP);
$$ LANGUAGE SQL IMMUTABLE;

CREATE FUNCTION dirname(text) RETURNS text AS $$
    SELECT ltrim(regexp_replace('/' || $1, '[^/]*$', ''), '/');
$$ LANGUAGE SQL IMMUTABLE;

CREATE INDEX datum_thing_id_revision_idx ON datum (thing_id, end_revision, begin_revision);


-- index dirname(key) for datatype key
CREATE INDEX datum_key_val_dirname_idx ON datum (key, dirname(value), datatype, begin_revision, end_revision) WHERE datatype=1;

CREATE INDEX datum_key_val_key_idx ON datum (key, value, thing_id) WHERE datatype=1 AND end_revision=2147483647;
CREATE INDEX datum_key_val_str_idx ON datum (key, value, thing_id) WHERE datatype=2 AND end_revision=2147483647;
CREATE INDEX datum_key_val_uri_idx ON datum (key, value, thing_id) WHERE datatype=4 AND end_revision = 2147483647;
CREATE INDEX datum_key_val_ref_idx ON datum (key, cast(value as integer), thing_id) WHERE datatype=0 AND end_revision=2147483647;
CREATE INDEX datum_key_val_bool_idx ON datum (key, cast(value as integer), thing_id) WHERE datatype=5 AND end_revision=2147483647;
CREATE INDEX datum_key_val_int_idx ON datum (key, cast(value as integer), thing_id) WHERE datatype=6 AND end_revision=2147483647;
CREATE INDEX datum_key_val_float_idx ON datum (key, cast(value as float), thing_id) WHERE datatype=7 AND end_revision=2147483647;
CREATE INDEX datum_key_val_timestamp_idx ON datum (key, text2timestap(value), thing_id) WHERE datatype=8 AND end_revision=2147483647;

CREATE INDEX account_email_idx ON account (email);

----------------
--- triggers ---
----------------

CREATE FUNCTION before_version_insert() RETURNS TRIGGER AS $$
DECLARE
    next_revision int;
BEGIN
    SELECT INTO next_revision revision FROM version WHERE thing_id=NEW.thing_id ORDER BY revision DESC LIMIT 1;
    IF next_revision IS NULL THEN
        NEW.revision = 1;
    ELSE
        NEW.revision := next_revision + 1;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER version_revision
BEFORE INSERT ON version
FOR EACH ROW EXECUTE PROCEDURE before_version_insert();

CREATE FUNCTION on_version_insert() RETURNS TRIGGER AS $$
BEGIN
    UPDATE thing SET latest_revision = NEW.revision, last_modified=NEW.created WHERE thing.id = NEW.thing_id;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER thing_latest_revision
AFTER INSERT ON version
FOR EACH ROW EXECUTE PROCEDURE on_version_insert(); 

CREATE FUNCTION on_datum_insert() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.key = 'key' THEN
        UPDATE thing SET key=NEW.VALUE WHERE thing.id = NEW.thing_id;
    END IF;

    -- make sure length of string is limited for datatypes key, string and uri
    IF NEW.datatype = 1 OR NEW.datatype = 2 OR NEW.datatype = 4 THEN
        IF char_length(NEW.value) > 2048 THEN
            RAISE EXCEPTION 'string length can not be more than 2048';
        END IF;
    END IF;

    -- key should not have leading or trailing /'s and should not have spaces
    IF NEW.datatype = 1 AND NEW.key !~ E'^[^/\\s]+(?:/[^/\\s]+)*$' THEN
            RAISE EXCEPTION 'Invalid key %', NEW.value;
    END IF;
        
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER thing_key
AFTER INSERT ON datum 
FOR EACH ROW EXECUTE PROCEDURE on_datum_insert();

