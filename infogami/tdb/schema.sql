CREATE TABLE thing (
  id serial primary key,
  name varchar(4000) unique,
  latest_version_id int references version
);

CREATE TABLE version (
  id serial primary key,
  revision int,
  thing_id int references thing,
  author int references thing,
  comment text,
  created timestamp default (current_timestamp at time zone 'utc')
);

CREATE TABLE datum (
  version_id int references version,
  key text,
  value text,
  data_type int default 0, -- {0: 'string', 1: 'reference', 2: 'int', 3: 'float', 4: 'date'}
  ordering int default null,
);