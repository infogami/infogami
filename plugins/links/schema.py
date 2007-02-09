"""
db schema for links plugin.
"""
import web
from utils import dbsetup

upgrade = dbsetup.module('links').upgrade

schema = """
CREATE TABLE backlinks (
  site_id int references site,
  page_id int references page,
  link text,
  primary key (site_id, page_id, link)
)
"""

@upgrade
def setup():
    for t in schema.split('----'):
        web.query(t)

