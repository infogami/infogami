"""
links: allow interwiki links

Adds a markdown preprocessor to catch `[[foo]]` style links.
Creates a new set of database tables to keep track of them.
Creates a new `m=backlinks` to display the results.
"""

from infogami import utils
from infogami.utils import delegate

import view
from infogami import tdb
from infogami.core import db
import web

render = utils.view.render.links

class hook(tdb.hook):
    def before_new_version(self, page):
        if page.type.name == "type/page":
            page.links = list(view.get_links(page.get('body', '')))

class backlinks (delegate.mode):
    def GET(self, site, path):
        links = tdb.Things(type=db.get_type(site, 'type/page'), parent=site, links=path)
        return render.backlinks(links)

