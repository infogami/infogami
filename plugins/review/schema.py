"""
db schema for review plugin.
"""
import web
from utils import dbsetup

upgrade = dbsetup.module('review').upgrade

schema = """
CREATE TABLE review (
  id serial primary key,
  site_id int references site,
  page_id int references page,
  user_id int references login,
  revision int default 0,
  unique (site_id, page_id, user_id)
)
"""

@upgrade
def setup():
    for t in schema.split('----'):
        web.query(t)
