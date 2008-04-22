"""
Infogami read/write API.
"""
import web
import infogami
from infogami.utils import delegate
from infogami.infobase import server

class api(delegate.page):
    path = "/api/(.*)"
        
    def delegate(self, path):
        host = infogami.config.infobase_host
        sitename = web.ctx.site.name
        path = "/%s/%s" % (sitename, path)
        method = web.ctx.method
        
        # Have an option of setting content-type to text/plain
        i = web.input(_method='GET', text="false")
        if i.text.lower() == "false":
            web.header('Content-type', 'application/json')
        else:
            web.header('Content-type', 'text/plain')
            
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
            print response.read()
        else:
            data = web.input()
            out = server.request(path, method, data)
            if web.ctx.status.split()[0] != '200':
                web.ctx.output = ''
            else:
                print out

    GET = POST = delegate
