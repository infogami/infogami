"""
backlinks: keep track of what links where

Creates a new set of database tables to keep track of link structure
and creates a new `m=backlinks` to display the results.
"""
from utils import delegate
import db
import web
from core import view

render = web.template.render('core/templates/')

class hooks:
    __metaclass__ = delegate.hook
    def on_new_version(site, path, data):
        db.new_links(site, path, view.do_links(data, links=True))

class backlinks (delegate.mode):
    def GET(self, site, path):
        links = db.get_links(site, path)
        print render.pagelist(links)
