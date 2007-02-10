"""
links: allow interwiki links

Adds a markdown preprocessor to catch `[[foo]]` style links.
Creates a new set of database tables to keep track of them.
Creates a new `m=backlinks` to display the results.
"""

from infogami.utils import delegate
from infogami import utils

import view
import db

import web
import re

render = utils.view.render.links

class hooks:
    __metaclass__ = delegate.hook
    def on_new_version(site, path, data):
        db.new_links(site, path, view.get_links(data))

class backlinks (delegate.mode):
    def GET(self, site, path):
        links = db.get_links(site, path)
        return render.backlinks(links)

