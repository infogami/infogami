CREATE TABLE backlinks_link (
  tail int references pages,
  head_path text,
  head_site int references sites,
  primary key (tail, head_path, head_site)
);