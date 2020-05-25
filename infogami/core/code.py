import web

from infogami import config
from infogami.core import db, forms, helpers
from infogami.infobase.client import ClientException
from infogami.utils import delegate, types
from infogami.utils.flash import add_flash_message
from infogami.utils.template import render
from infogami.utils.view import require_login, safeint


def notfound(path):
    web.ctx.status = '404 Not Found'
    return render.notfound(path)

class view (delegate.mode):
    def GET(self, path):
        i = web.input(v=None)

        if i.v is not None and safeint(i.v, None) is None:
            raise web.seeother(web.changequery(v=None))

        p = db.get_version(path, i.v)
        if p is None:
            return notfound(path)
        elif p.type.key == '/type/delete':
            web.ctx.status = '404 Not Found'
            return render.viewpage(p)
        elif p.type.key == "/type/redirect" and p.location \
                and not p.location.startswith('http://') \
                and not p.location.startswith('://'):
            web.redirect(p.location)
        else:
            return render.viewpage(p)

class edit (delegate.mode):
    def GET(self, path):
        i = web.input(v=None, t=None)

        if not web.ctx.site.can_write(path):
            return render.permission_denied(web.ctx.fullpath, "Permission denied to edit " + path + ".")

        if i.v is not None and safeint(i.v, None) is None:
            raise web.seeother(web.changequery(v=None))

        p = db.get_version(path, i.v) or db.new_version(path, types.guess_type(path))

        if i.t:
            type = db.get_type(i.t)
            if type is None:
                add_flash_message('error', 'Unknown type: ' + i.t)
            else:
                p.type = type

        return render.editpage(p)


    def trim(self, d):
        """Trims empty value from d.

        >>> trim = edit().trim

        >>> trim("hello ")
        'hello'
        >>> trim(['hello ', '', ' foo'])
        ['hello', 'foo']
        >>> trim({'x': '', 'y': 'foo'})
        {'y': 'foo'}
        >>> trim({'x': '', 'unique': 'foo'})
        >>> trim([{'x': '', 'y': 'foo'}, {'x': ''}])
        [{'y': 'foo'}]
        """
        if d is None:
            return d
        elif isinstance(d, list):
            d = [self.trim(x) for x in d]
            d = [x for x in d if x]
            return d
        elif isinstance(d, dict):
            for k, v in list(d.items()):
                d[k] = self.trim(v)
                if d[k] is None or d[k] == '' or d[k] == []:
                    del d[k]

            # hack to stop saving empty properties
            if list(d.keys()) == [] or list(d.keys()) == ['unique']:
                return None
            else:
                return d
        else:
            return d.strip()

    def POST(self, path):
        i = web.input(_method='post')
        i = web.storage(helpers.unflatten(i))
        i.key = path

        _ = web.storage((k, i.pop(k)) for k in list(i.keys()) if k.startswith('_'))
        action = self.get_action(_)
        comment = _.get('_comment', None)

        for k, v in list(i.items()):
            i[k] = self.trim(v)

        p = web.ctx.site.get(path) or web.ctx.site.new(path, {})
        p.update(i)

        if action == 'preview':
            p['comment_'] = comment
            return render.editpage(p, preview=True)
        elif action == 'save':
            try:
                p._save(comment)
                path = web.input(_method='GET', redirect=None).redirect or web.changequery(query={})
                raise web.seeother(path)
            except (ClientException, db.ValidationException) as e:
                add_flash_message('error', str(e))
                p['comment_'] = comment
                return render.editpage(p)
        elif action == 'delete':
            q = dict(key=i['key'], type=dict(key='/type/delete'))

            try:
                web.ctx.site.save(q, comment)
            except (ClientException, db.ValidationException) as e:
                add_flash_message('error', str(e))
                p['comment_'] = comment
                return render.editpage(p)

            raise web.seeother(web.changequery(query={}))

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
            raise web.seeother(path)
        return render.permission(p)

    def POST(self, path):
        p = db.get_version(path)
        if not p:
            raise web.seeother(path)

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
        except Exception as e:
            import traceback
            traceback.print_exc(e)
            add_flash_message('error', str(e))
            return render.permission(p)

        raise web.seeother(web.changequery({}, m='permission'))

class history (delegate.mode):
    def GET(self, path):
        page = web.ctx.site.get(path)
        if not page:
            raise web.seeother(path)
        i = web.input(page=0)
        offset = 20 * safeint(i.page)
        limit = 20
        history = db.get_recent_changes(key=path, limit=limit, offset=offset)
        return render.history(page, history)

class recentchanges(delegate.page):
    def GET(self):
        return render.recentchanges()

class diff (delegate.mode):
    def GET(self, path):
        i = web.input(b=None, a=None)
        # default value of b is latest revision and default value of a is b-1

        def get(path, revision):
            if revision == 0:
                page = web.ctx.site.new(path, {'revision': 0, 'type': {'key': '/type/object'}, 'key': path})
            else:
                page = web.ctx.site.get(path, revision)
            return page

        def is_int(n):
            return n is None or safeint(n, None) is not None

        # if either or i.a or i.b is bad, then redirect to latest diff
        if not is_int(i.b) or not is_int(i.a):
            return web.redirect(web.changequery(b=None, a=None))

        b = get(path, safeint(i.b, None))

        # if the page is not there go to view page
        if b is None:
            raise web.seeother(web.changequery(query={}))

        a = get(path, max(1, safeint(i.a, b.revision-1)))
        return render.diff(a, b)

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
        except Exception as e:
            f = forms.login()
            f.fill(i)
            f.note = str(e)
            return render.login(f)

        if i.redirect == "/account/login" or i.redirect == "":
            i.redirect = "/"

        expires = (i.remember and 3600*24*7) or ""
        web.setcookie(config.login_cookie_name, web.ctx.conn.get_auth_token(), expires=expires)
        raise web.seeother(i.redirect)

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
            except ClientException as e:
                f.note = str(e)
                return render.register(f)
            web.setcookie(config.login_cookie_name, web.ctx.conn.get_auth_token())
            raise web.seeother(i.redirect)

class logout(delegate.page):
    path = "/account/logout"

    def POST(self):
        web.setcookie(config.login_cookie_name, "", expires=-1)
        referer = web.ctx.env.get('HTTP_REFERER', '/')
        raise web.seeother(referer)

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
            except ClientException as e:
                f.note = str(e)
                web.ctx.headers = []
                return render.forgot_password(f)
            else:
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
                raise web.seeother('/')
            except Exception as e:
                return "Failed to reset password.<br/><br/> Reason: "  + str(e)

_preferences = []
def register_preferences(cls):
    _preferences.append((cls.title, cls.path))

class preferences(delegate.page):
    path = "/account/preferences"

    @require_login
    def GET(self):
        return render.preferences(_preferences)

class change_password(delegate.page):
    path = "/account/preferences/change_password"
    title = "Change Password"

    @require_login
    def GET(self):
        f = forms.login_preferences()
        return render.login_preferences(f)

    @require_login
    def POST(self):
        i = web.input("oldpassword", "password", "password2")
        f = forms.login_preferences()
        if not f.validates(i):
            return render.login_preferences(f)
        else:
            try:
                user = web.ctx.site.update_user(i.oldpassword, i.password, None)
            except ClientException as e:
                f.note = str(e)
                return render.login_preferences(f)
            add_flash_message('info', 'Password updated successfully.')
            raise web.seeother("/account/preferences")

register_preferences(change_password)

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
        data = "\n".join("%s|%s" % (t[i.property], t.key) for t in things)
        raise web.HTTPError('200 OK', {}, data)

class favicon(delegate.page):
    path = "/favicon.ico"
    def GET(self):
        return web.redirect('/static/favicon.ico')

class feed(delegate.page):
    def _format_date(self, dt):
        """convert a datetime into an RFC 822 formatted date
        Input date must be in GMT.

        Source: PyRSS2Gen.py
        """
        # Looks like:
        #   Sat, 07 Sep 2002 00:00:01 GMT
        # Can't use strftime because that's locale dependent
        #
        # Isn't there a standard way to do this for Python?  The
        # rfc822 and email.Utils modules assume a timestamp.  The
        # following is based on the rfc822 module.
        return "%s, %02d %s %04d %02d:%02d:%02d GMT" % (
                ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dt.weekday()],
                dt.day,
                ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][dt.month-1],
                dt.year, dt.hour, dt.minute, dt.second)

    def GET(self):
        i = web.input(key=None)
        changes = db.get_recent_changes(key=i.key, limit=50)
        site =  web.ctx.home

        def diff(key, revision):
            b = db.get_version(key, revision)

            rev_a = revision -1
            if rev_a == 0:
                a = web.ctx.site.new(key, {})
                a.revision = 0
            else:
                a = db.get_version(key, revision=rev_a)

            diff = render.diff(a, b)

            #@@ dirty hack to extract diff table from diff
            import re
            rx = re.compile(r"^.*(<table.*<\/table>).*$", re.S)
            return rx.sub(r'\1', str(diff))

        web.header('Content-Type', 'application/rss+xml')

        for c in changes:
            c.diff = diff(c.key, c.revision)
            c.created = self._format_date(c.created)
        return delegate.RawText(render.feed(site, changes))
