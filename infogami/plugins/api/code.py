"""
Infogami read/write API.
"""
import web
import infogami
from infogami.utils import delegate
from infogami.infobase import server

hooks = {}        
def add_hook(name, cls):
    hooks[name] = cls

class api(delegate.page):
    path = "/api/(.*)"
    
    def delegate(self, suffix):
        # Have an option of setting content-type to text/plain
        i = web.input(_method='GET', text="false")
        if i.text.lower() == "false":
            web.header('Content-type', 'application/json')
        else:
            web.header('Content-type', 'text/plain')

        if suffix in hooks:
            method = web.ctx.method
            cls = hooks[suffix]
            m = getattr(cls(), method, None)
            if m:
                print m()
            else:
                web.ctx.status = '405 Method Not Allowed'
        else:
            web.ctx.status = '404 Not Found'
            
    GET = POST = delegate

class infobase_request:
    def delegate(self):
        method = web.ctx.method
        path = web.lstrips(web.ctx.path, "/api/")
    
        host = infogami.config.infobase_host
        sitename = web.ctx.site.name
        path = "/%s/%s" % (sitename, path)
        method = web.ctx.method

        if host:
            if method == 'GET':
                path += '?' + web.ctx.env['QUERY_STRING']
                data = None
            else:
                data = web.data()
        
            conn = httplib.HTTPConnection(self.host)
            env = web.ctx.get('env') or {}
        
            cookie = self.cookie or env.get('HTTP_COOKIE')
            if cookie:
                headers = {'Cookie': cookie}
            else:
                headers = {}
        
            conn.request(method, path, data, headers=headers)
            response = conn.getresponse()
        
            cookie = response.getheader('Set-Cookie')
            self.cookie = cookie
            web.header('Set-Cookie', cookie)
        
            web.ctx.status = "%s %s" % (response.status, response.reason)
            return response.read()
        else:
            data = web.input()
            out = server.request(path, method, data)
            if web.ctx.status.split()[0] != '200':
                web.ctx.output = ''
            else:
                return out
                
    GET = delegate

add_hook("get", infobase_request)
add_hook("things", infobase_request)
add_hook("versions", infobase_request)
            
