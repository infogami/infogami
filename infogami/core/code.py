import web
from infogami import utils, tdb
from infogami.utils import delegate
from infogami.utils.macro import macro
from infogami.utils.storage import storage
from infogami.utils.context import context

from diff import better_diff
import db
import auth
import forms


render = utils.view.render.core

def notfound():
    web.ctx.status = '404 Not Found'
    return render.notfound()

def deleted():
    web.ctx.status = '404 Not Found'
    return render.deleted()

def fill_missing_fields(site, page):
    schema = db.get_schema(page.type, keep_back_references=True)
    schema.pop('*', None)
    
    data = page.d
    for k, v in schema.items():
        if v.startswith('#'):
            t, key = v[1:].split('.', 1)
            q = {'type': db.get_type(site, t), key:page}
            data[k] = tdb.Things(limit=20, **q).list()
        elif k != '*' and data.get(k) is None:
            if v.endswith('*'):
                data[k] = ['']
            else:
                data[k] = ''
    
class view (delegate.mode):
    def GET(self, site, path):
        try:
            p = db.get_version(site, path, web.input(v=None).v)
        except db.NotFound:
            return notfound()
        else:
            if p.type == db.get_type(site, 'type/delete'):
                return deleted()
            else:
                fill_missing_fields(site, p)
                return render.view(p)
        
class edit (delegate.mode):
    def GET(self, site, path):
        i = web.input(v=None, t=None)
        
        try:
            p = db.get_version(site, path, i.v)
        except db.NotFound:
            p = db.new_version(site, path, db.get_type(site, 'type/page'), web.storage({}))

        if i.t:
            try:
                type = db.get_type(site, i.t)
            except tdb.NotFound:
                utils.view.set_error('Unknown type: ' + i.t)
            else:
                p.type = type
        
        fill_missing_fields(site, p)
        return render.edit(p)
    
    def dict_subset(self, d, keys):
        return dict([(k, v) for k, v in d.iteritems() if k in keys])
        
    def get_action(self, i):
        """Finds the action from input."""
        if '_save' in i: return 'save'
        elif '_preview' in i: return 'preview'
        elif '_delete' in i: return 'delete'
        else: return None
        
    def parse_data(self, site, type, i):
        schema = db.get_schema(type)
        allow_arbitrary = schema.pop('*', None) is not None
        
        _default = {True: [], False: ""}
        defaults = dict([(k, _default[v.endswith('*')]) for k, v in schema.items()])
        i = web.input(_method='post', **defaults)
        for k, v in schema.iteritems():
            if v.startswith('thing '):
                if isinstance(i[k], web.iters):
                    i[k] = [tdb.withName(x, site) for x in i[k] if x]
                else:
                    i[k] = tdb.withName(i[k], site)
            if v.endswith('*'):
                i[k] = [x for x in i[k] if x]
        if allow_arbitrary:
            d = [(k, v) for k, v in i.iteritems() if not k.startswith('_')]
            i = dict(d)
        else:
            d = [(k, i[k]) for k in schema]
            i = dict(d)

        return i
        
    def POST(self, site, path):
        i = web.input(_type="page", _method='post')
        action = self.get_action(i)
        comment = i.pop('_comment', None)
        try:
            type = db.get_type(site, i._type)
        except tdb.NotFound:
            utils.view.set_error('Unknown type: ' + i._type)
            #@@ using type/page here is not correct. 
            #@@ It should use the previous type
            type = db.get_type(site, 'type/page')
            data = self.parse_data(site, type, i)
            p = db.new_version(site, path, type, data)
            return render.edit(p)
        
        data = self.parse_data(site, type, i)
        p = db.new_version(site, path, type, data)
        
        if action == 'preview':
            return render.edit(p, preview=True)
        elif action == 'save':
            try:
                p.save(author=context.user, ip=web.ctx.ip, comment=comment)
                return web.seeother(web.changequery(m=None))
            except db.ValidationException, e:
                utils.view.set_error(str(e))
                return render.edit(p)
        elif action == 'delete':
            p.type = db.get_type(site, 'type/delete')
            p.save(author=context.user, ip=web.ctx.ip)
            return web.seeother(web.changequery(m=None))
            
class history (delegate.mode):
    def GET(self, site, path):
        try:
            p = db.get_version(site, path)
            return render.history(p)
        except db.NotFound:
            return web.seeother('/' + path)
                
class diff (delegate.mode):
    def GET(self, site, path):  
        i = web.input("b", a=None)
        i.a = i.a or int(i.b)-1

        try:
            if i.a == 0: a = web.storage(d={},v=web.storage(revision=0))
            else: a = db.get_version(site, path, revision=i.a)
            b = db.get_version(site, path, revision=i.b)
        except:
            return web.badrequest()
        
        if 'body' in a.d and 'body' in b.d:
            alines = a.body.splitlines()
            blines = b.body.splitlines()
            bodydiff = better_diff(alines, blines)
        else:
            bodydiff = None
        
        return render.diff(a, b, bodydiff)

class random(delegate.page):
    def GET(self, site):
        p = db.get_random_page(site)
        return web.seeother(p.path)

class login(delegate.page):
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
            user = db.new_user(site, i.username, i.email)
            user.displayname = i.displayname
            user.save()
            auth.set_password(user, i.password)
            auth.setcookie(user, i.remember)
            web.seeother(web.ctx.homepath + i.redirect)

class logout(delegate.page):
    def POST(self, site):
        web.setcookie("infogami_session", "", expires=-1)
        referer = web.ctx.env.get('HTTP_REFERER', '/')
        web.seeother(referer)

class login_reminder(delegate.page):
    def GET(self, site):
        print "Not yet implemented."

_preferences = storage.core_preferences
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
        i = web.input("oldpassword", "password", "password2")
        f = forms.login_preferences()
        if not f.validates(i):
            return render.login_preferences(f)
        else:
            user = auth.get_user(site)
            auth.set_password(user, i.password)
            return self.GET(site)

register_preferences("login_preferences", login_preferences())

class sitepreferences(delegate.page):
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

def string_renderer(name, value, **attrs):
    """Renderer for html text input."""
    return web.form.Textbox(name, value=value, **attrs).render()
    
def text_renderer(name, value, **attrs):
    """Renderer for html textarea input."""
    return web.form.Textarea(name, value=value, rows=25, cols=80, **attrs).render()
    
utils.view.register_input_renderer('string', string_renderer)
utils.view.register_input_renderer('text', text_renderer)
# Thing is also displayed as textbox
utils.view.register_input_renderer('thing', string_renderer)
