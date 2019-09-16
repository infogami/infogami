"""
links: allow interwiki links

Adds a markdown preprocessor to catch `[[foo]]` style links.
Creates a new set of database tables to keep track of them.
Creates a new `m=backlinks` to display the results.
"""

import web

from infogami.core import db
from infogami.utils import delegate
from infogami.utils.template import render

import view

class backlinks (delegate.mode):
    def GET(self, site, path):
        #@@ fix later
        return []
        # unreachable code...
        links = db.Things(type=db.get_type(site, 'type/page'), parent=site, links=path)
        return render.backlinks(links)
