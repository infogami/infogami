import web
from infogami import utils, tdb, config
from infogami.utils import delegate
from infogami.utils.context import context
from infogami.utils.template import render

from diff import better_diff
import db
import auth
import forms
import thingutil
import helpers

def notfound():
    web.ctx.status = '404 Not Found'
    return render.notfound()

def deleted():
    web.ctx.status = '404 Not Found'
    return render.deleted()

class view (delegate.mode):
    def GET(self, site, path):
        try:
            p = db.get_version(site, path, web.input(v=None).v)
        except tdb.NotFound:
            return notfound()
        else:
            if p.type == db.get_type(site, 'type/delete'):
                return deleted()
            else:
                thingutil.thingtidy(p)
                return render.view(p)
        
class edit (delegate.mode):
    def GET(self, site, path):
        i = web.input(v=None, t=None)
        
        try:
            p = db.get_version(site, path, i.v)
        except tdb.NotFound:
            p = db.new_version(site, path, db.get_type(site, 'type/page'), web.storage({}))

        if i.t:
            try:
                type = db.get_type(site, i.t)
            except tdb.NotFound:
                utils.view.set_error('Unknown type: ' + i.t)
            else:
                p.type = type
        
        thingutil.thingtidy(p)
        return render.edit(p)
    
    def get_action(self, i):
        """Finds the action from input."""
        if '_save' in i: return 'save'
        elif '_preview' in i: return 'preview'
        elif '_delete' in i: return 'delete'
        else: return None
        
    def POST(self, site, path):
        i = web.input(_type="page", _method='post')
        i = web.storage(helpers.trim(helpers.unflatten(i)))
        
        action = self.get_action(i)
        comment = i.pop('_comment', None)
        try:
            type = db.get_type(site, i._type)
        except tdb.NotFound:
            utils.view.set_error('Unknown type: ' + i._type)
            #@@ using type/page here is not correct. 
            #@@ It should use the previous type
            type = db.get_type(site, 'type/page')
            p = db.new_version(site, path, type, data)
            thingutil.thingtidy(p)
            return render.edit(p)
            
        p = db.new_version(site, path, type, i)
        
        if action == 'preview':
            thingutil.thingtidy(p, fill_missing=True)
            return render.edit(p, preview=True)
        elif action == 'save':
            try:
                thingutil.thingtidy(p, fill_missing=False)
                p.save(author=context.user, ip=web.ctx.ip, comment=comment)
                return web.seeother(web.changequery(query={}))
            except db.ValidationException, e:
                utils.view.set_error(str(e))
                return render.edit(p)
        elif action == 'delete':
            p.type = db.get_type(site, 'type/delete')
            p.save(author=context.user, ip=web.ctx.ip)
            return web.seeother(web.changequery(query={}))

class history (delegate.mode):
    def GET(self, site, path):
        try:
            p = db.get_version(site, path)
            return render.history(p)
        except tdb.NotFound:
            return web.seeother('/' + path)
                
class diff (delegate.mode):
    def GET(self, site, path):  
        i = web.input("b", a=None)
        i.a = i.a or int(i.b)-1

        try:
            b = db.get_version(site, path, revision=i.b)
            #@@ what to do diff is called when there is only one version
            # Probably diff should be displayed with empty thing and current thing.  
            # Displaying diff with itself, since it is easy to implement.
            if i.a == 0: a = b
            else: a = db.get_version(site, path, revision=i.a)
        except:
            return web.badrequest()
            
        return render.diff(a, b)

class random(delegate.page):
    def GET(self, site):
        p = db.get_random_page(site)
        return web.seeother(p.path)

class login(delegate.page):
    path = "/account/login"
    
    def GET(self, site):
        referer = web.ctx.env.get('HTTP_REFERER', '/')
        i = web.input(redirect=referer)
        f = forms.login()
        f['redirect'].value = i.redirect 
        return render.login(f)

    def POST(self, site):
        i = web.input(remember=False, redirect='/')
        user = auth.login(site, i.username, i.password, i.remember)
        if user is None:
            f = forms.login()
            f.fill(i)
            f.note = 'Invalid username or password.'
            return render.login(f)

        web.seeother(i.redirect)
        
class register(delegate.page):
    path = "/account/register"
    
    def GET(self, site):
        return render.register(forms.register())
        
    def POST(self, site):
        i = web.input(remember=False, redirect='/')
        f = forms.register()
        if not f.validates(i):
            return render.register(f)
        else:
            user = db.new_user(site, i.username, i.displayname, i.email, i.password)
            auth.setcookie(user, i.remember)
            web.seeother(i.redirect)

class logout(delegate.page):
    path = "/account/logout"
    
    def POST(self, site):
        web.setcookie("infogami_session", "", expires=-1)
        referer = web.ctx.env.get('HTTP_REFERER', '/')
        web.seeother(referer)

class forgot_password(delegate.page):
    path = "/account/forgot_password"

    def GET(self, site):
        f = forms.forgot_password()
        return render.forgot_password(f)
        
    def POST(self, site):
        i = web.input()
        f = forms.forgot_password()
        if not f.validates(i):
            return render.forgot_password(f)
        else:    
            user = db.get_user_by_email(site, i.email)
            username = web.lstrips(user.name, 'user/')
            web.config.smtp_server = config.smtp_server
            password = auth.random_password()
            auth.set_password(user, password)
            msg = render.password_mailer(username, password)
            web.sendmail(config.from_address, i.email, msg.subject.strip(), str(msg))
            return render.passwordsent(i.email)

_preferences = web.storage()
def register_preferences(name, handler):
    _preferences[name] = handler

class preferences(delegate.page):
    path = "/account/preferences"
    
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
        i = web.input("oldpassword", "password", "password2")
        f = forms.login_preferences()
        if not f.validates(i):
            return render.login_preferences(f)
        else:
            user = auth.get_user(site)
            auth.set_password(user, i.password)
            return self.GET(site)

register_preferences("login_preferences", login_preferences())

class getthings(delegate.page):
    """Lists all pages with name path/*"""
    def GET(self, site):
        i = web.input("q", "type", "limit")
        things = db.get_things(site, i.type, i.q, i.limit)
        print "\n".join([thing.name for thing in things])
    
class sitepreferences(delegate.page):
    path = "/admin/sitepreferences"
    
    def GET(self, site):
        if not auth.has_permission(context.site, context.user, "sitepreferences", "view"):
            return auth.login_redirect()
            
        perms = db.get_site_permissions(site)
        return render.sitepreferences(perms)
        
    def POST(self, site):
        if not auth.has_permission(context.site, context.user, "sitepreferences", "view"):
            return auth.login_redirect()
            
        perms = self.input()
        db.set_site_permissions(site, perms)
        return render.sitepreferences(perms)
    
    def input(self):
        i = web.input(order=[])
        re_who = web.re_compile("who(\d+)_path\d+")
        re_what = web.re_compile("what(\d+)_path\d+")
        
        values = []
        for o in i.order:
            key = 'path' + o
            path = i[key].strip()
            if path == "":
                continue
                
            who_keys = [re_who.sub(r'\1', k) for k in i
                            if k.endswith(key) and k.startswith('who')]            
            what_keys = [re_what.sub(r'\1', k) for k in i
                            if k.endswith(key) and k.startswith('what')]
            x = sorted(who_keys)
            y = sorted(what_keys)
            assert x == y
            whos = [i["who%s_%s" % (k, key)].strip() for k in x]
            whats = [i["what%s_%s" % (k, key)].strip() for k in x]
            
            perms = [(a, b) for a, b in zip(whos, whats) if a != ""]
            values.append((path, perms))
            
        return values
