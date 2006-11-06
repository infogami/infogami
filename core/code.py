import web
from utils import delegate
from utils.diff import better_diff
import db
from view import render 

def notfound():
    web.ctx.status = '404 Not Found'
    print render.special.do404()

class view (delegate.mode):
    def GET(self, site, path):
        try:
            d = db.get_version(site, path, web.input(v=None).v)
        except IndexError:
            return notfound()
        
        print render.view(d)

class edit (delegate.mode):
    def GET(self, site, path):
        i = web.input(v=None)
        try:
            data = db.get_version(site, path, i.v).data
        except IndexError:
            data = web.storage({'title': '', 'body': ''})
        
        print render.edit(data)
    
    def POST(self, site, path):
        i = web.input()
        if i.clicked == 'Preview':
            print render.edit(i, preview=True)
        else:
            d = db.new_version(site, path, dict(title=i.title, body=i.body))
            return web.seeother(web.changequery(m=None))

class history (delegate.mode):
    def GET(self, site, path):
        d = db.get_all_versions(site, path)
        print render.history(d)

class diff (delegate.mode):
    def GET(self, site, path):
        i = web.input(a=None, b=None)

        try:
            a = db.get_version(site, path, date=i.a)
            if i.b is None:
                b = db.get_version(site, path, before=i.a)
            else:
                b = db.get_version(site, path, date=i.b)
        except:
            return notfound()

        alines = a.data.body.splitlines()
        blines = b.data.body.splitlines()
        
        map = better_diff(alines, blines)
        print render.diff(map, a.created, b.created)

class random(delegate.page):
    def GET(self, site):
        p = db.get_random_page(site)
        return web.seeother(p.path)

class pagelist(delegate.page):
    def GET(self, site):
        d = db.get_all_pages(site)
        print render.pagelist(d)

class recentchanges(delegate.page):
    def GET(self, site):
        d = db.get_recent_changes(site)
        print render.recentchanges(d)
        
