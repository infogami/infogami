import web
from config import db
from view import render

def notfound():
    web.ctx.status = '404 Not Found'
    print render.special.do404()

class view:
    def GET(self, site, path):
        try:
            d = db.get_version(site, path, web.input(v=None).v)
        except IndexError:
            return notfound()
        
        print render.view(d)

class edit:
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

class history:
    def GET(self, site, path):
        d = db.get_all_versions(site, path)
        print render.history(d)
