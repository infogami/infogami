import web
import os

import infogami
from infogami import utils, tdb, config
from infogami.utils import delegate, types
from infogami.utils.context import context
from infogami.utils.template import render
from infogami.utils.view import login_redirect, require_login, safeint

import db
import forms
import thingutil
import helpers

from infogami.infobase.client import ClientException

def notfound(path):
    web.ctx.status = '404 Not Found'
    return render.notfound(path)

class view (delegate.mode):
    def GET(self, path):
        i = web.input(v=None)

        if i.v is not None and safeint(i.v, None) is None:
            return web.seeother(web.changequery(v=None))
		
        p = db.get_version(path, i.v)

        if p is None:
            return notfound(path)
        elif p.type.key == '/type/delete':
            web.ctx.status = '404 Not Found'
            return render.viewpage(p)
        else:
            return render.viewpage(p)

class edit (delegate.mode):
    def GET(self, path):
        i = web.input(v=None, t=None)

        if i.v is not None and safeint(i.v, None) is None:
            return web.seeother(web.changequery(v=None))
		        
        p = db.get_version(path, i.v) or db.new_version(path, types.guess_type(path))
        
        if i.t:
            try:
                type = db.get_type(i.t)
            except tdb.NotFound:
                utils.view.set_error('Unknown type: ' + i.t)
            else:
                p.type = type 

        return render.editpage(p)
        
    def make_query(self, value, connect=False):
        """Make infobase write query from post data."""
        if isinstance(value, dict):
            d = dict()
            for k, v in value.items():
                if k in ['key', 'connect', 'create']: # key is never changed
                    d[k] = v
                    continue
                d['create'] = 'unless_exists'
                d[k] = self.make_query(v, connect=True)
                
            if connect and 'create' not in d:
                d['connect'] = 'update'
            return d
        elif isinstance(value, list):
            return dict(connect='update_list', value=[self.make_query(v, False) for v in value])
        else:
            return dict(connect='update', value=value or None)
            
        for key, value in i.items():
            if key in ['key', 'connect', 'create']: # key is never changed
                continue
                
            i['create'] = 'unless_exists'
            if isinstance(value, dict):
                value = self.make_query(value)
                if 'create' not in value:
                    value['connect'] = 'update'
            elif isinstance(value, list):
                value = dict(
                    connect='update_list', 
                    value=[self.make_query(v) for v in value])
            else:
                value = dict(connect='update', value=value)
            i[key] = value
            
        return i
        
    def POST(self, path):
        i = web.input(_method='post')
        i = web.storage(helpers.unflatten(i))
        i.key = path
        i.create = 'unless_exists'
        
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
                return non_empty([trim(x) for x in d if x])
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
        from copy import deepcopy
        q = self.make_query(deepcopy(i))
        if action == 'preview':
            p = self.process(i)
            return render.editpage(p, preview=True)
        elif action == 'save':
            try:
                web.ctx.site.write(q, comment)
                return web.seeother(web.changequery(query={}))
            except ClientException, e:
                utils.view.set_error(str(e))
                p = self.process(i)
                return render.editpage(p)
        elif action == 'delete':
            q = dict(key=q['key'], type=dict(connect='update', key='/type/delete'))
            web.ctx.site.write(q, comment)
            return web.seeother(web.changequery(query={}))

    def process(self, data):
        """Updates thing with given data recursively."""
        def new_version(data):
            thing = db.get_version(data['key'])
            if not thing:
                thing = web.ctx.site.new(data['key'], data)
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

class permission(delegate.mode):
    def GET(self, path):
        p = db.get_version(path)
        if not p:
            return web.seeother('/' + path)
        return render.permission(p)
        
    def POST(self, path):
        p = db.get_version(path)
        if not p:
            return web.seeother('/' + path)
            
        i = web.input('permission.key', 'child_permission.key')
        q = {
            'key': path,
            'permission': {
                'connect': 'update',
                'key': i['permission.key'] or None,
            },
            'child_permission': {
                'connect': 'update',
                'key': i['child_permission.key'] or None,
            }
        }
        
        try:
            web.ctx.site.write(q)
            web.seeother(web.changequery({}, m='permission'))
        except Exception, e:
            import traceback
            traceback.print_exc(e)
            delegate.view.set_error(str(e))
            return render.permission(p)
            
class history (delegate.mode):
    def GET(self, path):
        page = web.ctx.site.get(path)
        if not page:
            return web.seeother(path)
        i = web.input(page=0)
        offset = 20 * safeint(i.page)
        limit = 20
        history = db.get_recent_changes(key=path, limit=limit, offset=offset)
        return render.history(page, history)
                
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
        try:
            web.ctx.site.login(i.username, i.password, i.remember)
        except Exception, e:
            f = forms.login()
            f.fill(i)
            f.note = str(e)
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

    def GET(self):
        f = forms.forgot_password()
        return render.forgot_password(f)
        
    def POST(self):
        i = web.input()
        f = forms.forgot_password()
        if not f.validates(i):
            return render.forgot_password(f)
        else:
            from infogami.infobase.client import ClientException
            try:
                delegate.admin_login()
                d = web.ctx.site.get_reset_code(i.email)
            except ClientException, e:
                f.note = str(e)
                return render.forgot_password(f)
            finally:
                # clear the cookie set by delegate.admin_login
                # Otherwise user will be able to work as admin user.
                web.ctx.headers = []
                
            msg = render.password_mailer(web.ctx.home, d.username, d.code)            
            web.sendmail(config.from_address, i.email, msg.subject.strip(), str(msg))
            return render.passwordsent(i.email)

class reset_password(delegate.page):
    path = "/account/reset_password"
    def GET(self):
        f = forms.reset_password()
        return render.reset_password(f)
        
    def POST(self):
        i = web.input("code", "username")
        f = forms.reset_password()
        if not f.validates(i):
            return render.reset_password(f)
        else:
            try:
                web.ctx.site.reset_password(i.username, i.code, i.password)
                web.ctx.site.login(i.username, i.password, False)
                web.seeother('/')
            except Exception, e:
                return "Failed to reset password.<br/><br/> Reason: "  + str(e)
        
_preferences = web.storage()
def register_preferences(name, handler):
    _preferences[name] = handler

class preferences(delegate.page):
    path = "/account/preferences"
    
    @require_login    
    def GET(self):
        d = dict((name, p.GET()) for name, p in _preferences.iteritems())
        return render.preferences(d.values())

    @require_login
    def POST(self):
        i = web.input("_action")
        result = _preferences[i._action].POST()
        d = dict((name, p.GET()) for name, p in _preferences.iteritems())
        if result:
            d[i._action] = result
        return render.preferences(d.values())

class login_preferences:
    def GET(self):
        f = forms.login_preferences()
        return render.login_preferences(f)
        
    def POST(self):
        i = web.input("oldpassword", "password", "password2")
        f = forms.login_preferences()
        if not f.validates(i):
            return render.login_preferences(f)
        else:
            user = web.ctx.site.update_user(i.oldpassword, i.password, None)
            return self.GET()

register_preferences("login_preferences", login_preferences())

class getthings(delegate.page):
    """Lists all pages with name path/*"""
    def GET(self):
        i = web.input("type", property="key")
        q = {
            i.property + '~': i.q + '*',
            'type': i.type,
            'limit': int(i.limit)
        }
        things = [web.ctx.site.get(t, lazy=True) for t in web.ctx.site.things(q)]
        print "\n".join("%s|%s" % (t[i.property], t.key) for t in things)
    
class favicon(delegate.page):
    path = "/favicon.ico"
    def GET(self):
        return web.redirect('/static/favicon.ico')
