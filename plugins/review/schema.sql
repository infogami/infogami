CREATE TABLE review (
  id serial primary key,
  site_id int references site,
  page_id int references page,
  user_id int references login,
  revision int,
  primary key (site_id, page_id, user_id)
  unique (site_id, page_id, user_id)
);
