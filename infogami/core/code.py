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
            p = db.get_version(site.id, path, web.input(v=None).v)
        except db.NotFound:
            return notfound()
        else:
            return render.view(p)
        
class edit (delegate.mode):
    def GET(self, site, path):
        i = web.input(v=None, t=None)
        
        if i.t:
            type = db.get_type(i.t) or db.new_type(i.t)
        else:
            type = db.get_type('page')
            
        try:
            p = db.get_version(site.id, path, i.v)
            if i.t:
                p.type = type
        except db.NotFound:
            data = web.storage(title='', body='')
            p = db.new_version(site.id, path, type.id, data)

        return render.edit(p)
    
    def POST(self, site, path):
        i = web.input(type="page")
        data = web.storage((k, v) for k, v in i.items() if k not in ['clicked', 'type', 'm'])
        p = db.new_version(site.id, path, db.get_type(i.type).id, data)

        if i.clicked == 'Preview':
            return render.edit(p, preview=True)
        else:
            user = auth.get_user()
            author_id = user and user.id
            try:
                p.save(author_id=author_id, ip=web.ctx.ip)
                delegate.run_hooks('on_new_version', site, path, p)
            except db.ValidationException, e:
                utils.view.set_error(str(e))
                return render.edit(p)

            return web.seeother(web.changequery(m=None))

class history (delegate.mode):
    def GET(self, site, path):
        p = db.get_version(site.id, path)
        return render.history(p.h)

class diff (delegate.mode):
    def GET(self, site, path):
        i = web.input("b", a=None)
        i.a = i.a or int(i.b)-1

        try:
            a = db.get_version(site.id, path, revision=i.a)
            b = db.get_version(site.id, path, revision=i.b)
        except:
            return web.badrequest()

        alines = a.body.splitlines()
        blines = b.body.splitlines()
        
        map = better_diff(alines, blines)
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
                user = db.new_user(i.username, i.email, i.password)
                user.save()
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
