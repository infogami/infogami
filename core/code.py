import web
from utils import delegate
from utils.diff import better_diff
from config import db
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
        try:
            d = db.get_version(site, path)
        except IndexError:
            d = web.storage({'data': web.storage({'title': '', 'body': ''})})
        
        print render.edit(d)
    
    def POST(self, site, path):
        i = web.input()
        d = db.new_version(site, path, dict(title=i.title, body=i.body))
        return web.seeother(web.changequery(m=None))

class history (delegate.mode):
    def GET(self, site, path):
        d = db.get_all_versions(site, path)
        print render.history(d)

class diff(delegate.mode):
    def GET(self, site, path):
        i = web.input(a=None, b=None)

        a = db.get_version(site, path, i.a)
        b = db.get_version(site, path, i.b)
        alines = a.data.body.splitlines()
        blines = b.data.body.splitlines()
        
        map = better_diff(alines, blines)
        print render.diff(map, a.created, b.created)
