--- infobase schema ---

--- tables ---

CREATE TABLE site (
    id serial primary key,
    name text,
    UNIQUE (name)
);

CREATE TABLE thing (
    id serial primary key,
    site_id int references site,
    key varchar(4096),
    latest_revision int,
    deleted boolean DEFAULT false,
    UNIQUE (site_id, key)
);

CREATE TABLE version (
    id serial primary key,
    thing_id int references thing,
    revision int,
    author_id int references thing,
    ip inet,
    comment text,
    created timestamp default (current_timestamp at time zone 'utc'),
    unique (thing_id, revision)
);

CREATE TABLE datum (
    thing_id int references thing,
    begin_revision int,
    end_revision int default 2147483647, -- MAX_INT: 2**31 -1 
    key text,
    value text,
    datatype int default 1, -- 0: reference, 1: key, 2: string, 3: text, 4: uri, 5: boolean, 6: int, 7: float, 8: datatime
    ordering int default null,
    CHECK(key ~ '^[a-z][a-z/_]*$')
);

--- index ---

CREATE INDEX version_created_idx ON version (created);

CREATE FUNCTION text2timestap(text) RETURNS timestamp AS $$
    SELECT CAST($1 AS TIMESTAMP);
$$ LANGUAGE SQL IMMUTABLE;

--- index for keys, strings and uris 
CREATE INDEX datum_key_val_str_idx ON datum (key, value, datatype) WHERE datatype=1 OR datatype=2 OR datatype = 4;

--- index for integers, booleans and references
CREATE INDEX datum_key_val_int_idx ON datum (key, cast(value as integer), datatype) WHERE datatype=0 OR datatype = 5 OR datatype = 6;

--- index for floats
CREATE INDEX datum_key_val_float_idx ON datum (key, CAST(value AS float), datatype) WHERE datatype=7;

--- index for timestamps
CREATE INDEX datum_key_val_timestamp_idx ON datum (key, text2timestap(value), datatype) WHERE datatype=8;

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
    UPDATE thing SET latest_revision = NEW.revision WHERE thing.id = NEW.thing_id;
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
    IF NEW.datatype = 1 AND NEW.value !~  '^[^/\s](?:/[^/\s\])*$' THEN
    END IF;
        
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER thing_key
AFTER INSERT ON datum 
FOR EACH ROW EXECUTE PROCEDURE on_datum_insert();

