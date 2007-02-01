"""
review: allow user reviews

Creates a new set of database tables to keep track of user reviews.
Creates '/review' page for displaying modifications since last review.
"""

from utils import delegate, view

import db
import web
import core

render = web.template.render("plugins/review/templates/", cache=False)

def require_login(f):
    def g(*a, **kw):
        if not core.auth.get_user():
            return web.seeother(web.ctx.homepath + "/login")
        return f(*a, **kw)
    return g

class hooks:
    __metaclass__ = delegate.hook

    def on_new_version(site, path, data):
        user = core.auth.get_user()

        if user:
            # editing a page also means reviewing it.
            #@@ query should be avoided
            v = core.db.get_version(site, path)
            db.review(site, path, user.id, v.revision)

class changes (delegate.page):
    @require_login
    def GET(self, site):
        user = core.auth.get_user()
        d = db.get_modified_pages(site, user.id)
        return render.changes(web.ctx.homepath, d)

class review (delegate.mode):
    @require_login
    def GET(self, site, path):
        user = core.auth.get_user()
        i = web.input()

        print >> web.debug, i

        a = (i.a and int(i.a) or 0)
        b = int(i.b)

        if a == 0:
            alines = []
            xa = web.storage(created="", revision=0)
        else:
            xa = core.db.get_version(site, path, revision=a)
            alines = xa.data.body.splitlines()

        xb = core.db.get_version(site, path, revision=b)
        blines = xb.data.body.splitlines()
        map = core.diff.better_diff(alines, blines)

        view.add_stylesheet('core', 'diff.css')
        diff = core.code.render.diff(map, xa, xb)
        
        return render.review(path, diff, a, b)
        
class approve(delegate.mode):
    @require_login
    def GET(self, site, path):
        user = core.auth.get_user()
        i = web.input("v")
        db.approve(site, user.id, path, int(i.v))
        web.seeother(web.ctx.homepath + '/changes')
