import web
import os

import infogami
from infogami import utils, tdb, config
from infogami.utils import delegate, types
from infogami.utils.context import context
from infogami.utils.template import render

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
    def GET(self, path):
        i = web.input(v=None)
        p = db.get_version(path, i.v)
        
        if p is None:
            return notfound()
        elif p.deleted:
            return deleted()
        else:
            return render.viewpage(p)

class edit (delegate.mode):
    def GET(self, path):
        i = web.input(v=None, t=None)
        
        p = db.get_version(path, i.v) or db.new_version(path, types.guess_type(path))
        
        if i.t:
            try:
                type = db.get_type(i.t)
            except tdb.NotFound:
                utils.view.set_error('Unknown type: ' + i.t)
            else:
                p.type = type 

        return render.editpage(p)
    
    def POST(self, path):
        i = web.input(_method='post')
        i = web.storage(helpers.unflatten(i))
        i.key = path
        
        _ = web.storage((k, i.pop(k)) for k in i.keys() if k.startswith('_'))
        action = self.get_action(_)
        comment = _.get('_comment', None)
        
        #@@ hack to make editing types work.
        def hack(d):
            if isinstance(d, list):
                for x in d:
                    hack(x)
            elif isinstance(d, dict):
                if 'key' not in d and 'name' in d:
                    d['key'] = path + '/' + d['name']
                for k, v in d.items():
                    hack(v)
        
        def non_empty(items):
            return [i for i in items if i]

        def trim(d):
            if isinstance(d, list):
                return non_empty([trim(x) for x in d])
            elif isinstance(d, dict):
                for k, v in d.items():
                    d[k] = trim(v)
                if non_empty(d.values()) and (path == '' or d.get('key') or d.get('name')):
                    return d
                else: 
                    return None
            else:
                return d.strip()
                   
        i = trim(i)
        hack(i)  
        
        if action == 'preview':
            p = self.process(i)
            return render.editpage(p, preview=True)
        elif action == 'save':
            try:
                web.ctx.site.write(i, comment)
                return web.seeother(web.changequery(query={}))
            except db.ValidationException, e:
                utils.view.set_error(str(e))
                return render.editpage(p)
        elif action == 'delete':
            # delete is not yet implemented
            return web.seeother(web.changequery(query={}))

    def process(self, data):
        """Updates thing with given data recursively."""
        def new_version(data):
            thing = db.get_version(data['key'])
            if not thing:
                thing = web.ctx.site.new(data['key'], {'type': self.process(data['type'])})
            return thing
                
        if isinstance(data, dict):
            thing = new_version(data)
            for k, v in data.items():
                thing[k] = self.process(v)
            return thing
        elif isinstance(data, list):
            return [self.process(d) for d in data]
        else:
            return data
    
    def get_action(self, i):
        """Finds the action from input."""
        if '_save' in i: return 'save'
        elif '_preview' in i: return 'preview'
        elif '_delete' in i: return 'delete'
        else: return None
            
class history (delegate.mode):
    def GET(self, path):
        try:
            history = db.get_recent_changes(key=path, limit=20)
            if not history:
                return web.seeother('/' + path)
            return render.history(history)
        except tdb.NotFound:
            return web.seeother('/' + path)
                
class diff (delegate.mode):
    def GET(self, path):  
        i = web.input("b", a=None)

        try:
            rev_b = int(i.b)
            if i.a:
                rev_a = int(i.a)
            else:
                rev_a = rev_b - 1
        except ValueError:
            raise
            return web.badrequest()
            
        try:
            b = db.get_version(path, revision=rev_b)
            if not b:
                return web.seeother('/' + path)
            
            if i.a == 0: 
                a = web.ctx.site.new(path, {})
                a.revision = i.a
            else: 
                a = db.get_version(path, revision=rev_a)
        except:
            raise
            return web.badrequest()
        
        return render.diff(a, b)

class random(delegate.page):
    def GET(self, site):
        p = db.get_random_page(site)
        return web.seeother(p.path)

class login(delegate.page):
    path = "/account/login"
    
    def GET(self):
        referer = web.ctx.env.get('HTTP_REFERER', '/')
        i = web.input(redirect=referer)
        f = forms.login()
        f['redirect'].value = i.redirect 
        return render.login(f)

    def POST(self):
        i = web.input(remember=False, redirect='/')
        user = web.ctx.site.login(i.username, i.password, i.remember)
        if user is None:
            f = forms.login()
            f.fill(i)
            f.note = 'Invalid username or password.'
            return render.login(f)
        web.seeother(i.redirect)
        
class register(delegate.page):
    path = "/account/register"
    
    def GET(self):
        return render.register(forms.register())
        
    def POST(self):
        i = web.input(remember=False, redirect='/')
        f = forms.register()
        if not f.validates(i):
            return render.register(f)
        else:
            from infogami.infobase.client import ClientException
            try:
                web.ctx.site.register(i.username, i.displayname, i.email, i.password)
            except ClientException, e:
                f.note = str(e)
                return render.register(f)
            web.seeother(i.redirect)

class logout(delegate.page):
    path = "/account/logout"
    
    def POST(self):
        web.setcookie("infobase_session", "", expires=-1)
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
    def GET(self):
        print ''
    
class sitepreferences(delegate.page):
    path = "/admin/sitepreferences"
    
    def GET(self, site):
        if not auth.has_permission(context.site, context.user, "admin/sitepreferences", "view"):
            return auth.login_redirect()
            
        perms = db.get_site_permissions(site)
        return render.sitepreferences(perms)
        
    def POST(self, site):
        if not auth.has_permission(context.site, context.user, "admin/sitepreferences", "view"):
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

