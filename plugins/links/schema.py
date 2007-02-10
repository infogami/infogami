"""
db schema for links plugin.
"""
import web
from utils import dbsetup

schema = """
CREATE TABLE backlinks (
  site_id int references site,
  page_id int references page,
  link text,
  primary key (site_id, page_id, link)
);
"""

upgrade = dbsetup.module('links', schema).upgrade


