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

def deleted():
    web.ctx.status = '404 Not Found'
    return render.special.deleted()

class view (delegate.mode):
    def GET(self, site, path):
        try:
            p = db.get_version(site, path, web.input(v=None).v)
        except db.NotFound:
            return notfound()
        else:
            if p.type.name == 'delete':
                return deleted()
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
            p = db.get_version(site, path, i.v)
            if i.t:
                p.type = type
        except db.NotFound:
            data = web.storage(title='', body='')
            p = db.new_version(site, path, type, data)

        return render.edit(p)
    
    def POST(self, site, path):
        i = web.input(_type="page", _method='post')
        data = web.storage((k, v) for k, v in i.items() if not k.startswith('_'))
        p = db.new_version(site, path, db.get_type(i._type), data)
        
        if '_preview' in i:
            return render.edit(p, preview=True)
        elif '_save' in i:
            author = auth.get_user()
            try:
                p.save(author=author, ip=web.ctx.ip)
                delegate.run_hooks('on_new_version', site, path, p)
                return web.seeother(web.changequery(m=None))
            except db.ValidationException, e:
                utils.view.set_error(str(e))
                return render.edit(p)
        elif '_delete' in i:
            p.type = db.get_type('delete', create=True)
            p.save()
            return web.seeother(web.changequery(m=None))
            

class history (delegate.mode):
    def GET(self, site, path):
        p = db.get_version(site, path)
        return render.history(p)

class diff (delegate.mode):
    def GET(self, site, path):
        i = web.input("b", a=None)
        i.a = i.a or int(i.b)-1

        try:
            a = db.get_version(site, path, revision=i.a)
            b = db.get_version(site, path, revision=i.b)
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
        return render.login(forms.login())

    def POST(self, site):
        i = web.input(remember=False, redirect='/')
        user = db.login(i.username, i.password)
        if user is None:
            f = forms.login()
            f.fill(i)
            f.note = 'Invalid username or password.'
            return render.login(f)

        auth.setcookie(user, i.remember)
        web.seeother(web.ctx.homepath + i.redirect)
        
class register(delegate.page):
    def GET(self, site):
        return render.register(forms.register())
        
    def POST(self, site):
        i = web.input(remember=False, redirect='/')
        f = forms.register()
        if not f.validates(i):
            return render.register(f)
        else:
            user = db.new_user(i.username, i.email, i.password)
            user.save()
            auth.setcookie(user, i.remember)
            web.seeother(web.ctx.homepath + i.redirect)

class logout(delegate.page):
    def POST(self, site):
        web.setcookie("infogami_session", "", expires=-1)
        web.seeother(web.ctx.homepath + '/')

class login_reminder(delegate.page):
    def GET(self, site):
        print "Not yet implemented."

_preferences = {}
def register_preferences(name, handler):
    _preferences[name] = handler

class preferences(delegate.page):
    @auth.require_login    
    def GET(self, site):
        d = dict((name, p.GET(site)) for name, p in _preferences.iteritems())
        return render.preferences(d.values())

    @auth.require_login    
    def POST(self, site):
        i = web.input("_action")
        result = _preferences[i._action].POST(site)
        d = dict((name, p.GET(site)) for name, p in _preferences.iteritems())
        if result:
            d[i._action] = result
        return render.preferences(d.values())

class login_preferences:
    def GET(self, site):
        f = forms.login_preferences()
        return render.login_preferences(f)
        
    def POST(self, site):
        i = web.input("email", "password", "password2")
        f = forms.login_preferences()
        if not f.validates(i):
            return render.login_preferences(f)
        else:
            user = auth.get_user()
            user.password = i.password
            user.save()
            return self.GET(site)

register_preferences("login_preferences", login_preferences())