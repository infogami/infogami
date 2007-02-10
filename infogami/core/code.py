import web
from infogami import utils
from infogami.utils import delegate
from diff import better_diff
import db
import auth
import forms

render = utils.view.render.core

def notfound():
    web.ctx.status = '404 Not Found'
    return render.special.do404()

class view (delegate.mode):
    def GET(self, site, path):
        try:
            d = db.get_version(site, path, web.input(v=None).v)
        except IndexError:
            return notfound()
        
        return render.view(d)

class edit (delegate.mode):
    def GET(self, site, path):
        i = web.input(v=None)
        try:
            data = db.get_version(site, path, i.v).data
        except IndexError:
            data = web.storage({'title': '', 'body': ''})
        
        return render.edit(data)
    
    def POST(self, site, path):
        i = web.input()
        if i.clicked == 'Preview':
            return render.edit(i, preview=True)
        else:
            user = auth.get_user()
            author_id = user and user.id
            d = db.new_version(site, path, author_id, dict(title=i.title, body=i.body))
            return web.seeother(web.changequery(m=None))

class history (delegate.mode):
    def GET(self, site, path):
        d = db.get_all_versions(site, path)
        return render.history(d)

class diff (delegate.mode):
    def GET(self, site, path):
        i = web.input("b", a=None)
        i.a = i.a or int(i.b)-1

        try:
            a = db.get_version(site, path, revision=i.a)
            b = db.get_version(site, path, revision=i.b)
        except:
            return web.badrequest()

        alines = a.data.body.splitlines()
        blines = b.data.body.splitlines()
        
        map = better_diff(alines, blines)
        utils.view.add_stylesheet('core', 'diff.css')
        return render.diff(map, a, b)

class random(delegate.page):
    def GET(self, site):
        p = db.get_random_page(site)
        return web.seeother(p.path)

class pagelist(delegate.page):
    def GET(self, site):
        d = db.get_all_pages(site)
        return render.pagelist(d)

class recentchanges(delegate.page):
    def GET(self, site):
        d = db.get_recent_changes(site)
        return render.recentchanges(web.ctx.homepath, d)
    
    
class login(delegate.page):
    def GET(self, site):
        return render.login(forms.login(), forms.register())

    def POST(self, site):
        i = web.input(remember=False)
        if i.action == 'register':
            f = forms.register()
            if not f.validates(i):
                    return render.login(forms.login(), f)
            else:
                user = db.get_user(db.new_user(i.username, i.email, i.password))
        else:
            user = db.login(i.username, i.password)

        if user is None:
            f = forms.login()
            f.validates(i)
            return render.login(f, forms.register(), error='Invalid username or password.')

        auth.setcookie(user, i.remember)
        web.seeother(web.ctx.homepath + "/")

class logout(delegate.page):
    def POST(self, site):
        web.setcookie("infogami_session", "", expires=-1)
        web.seeother(web.ctx.homepath + '/')

class login_reminder(delegate.page):
    def GET(self, site):
        print "Not yet implemented."
