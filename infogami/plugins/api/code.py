"""
Infogami read/write API.
"""
import web
import infogami
from infogami.utils import delegate
from infogami.infobase import client

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
                raise web.HTTPError('200 OK', {}, m())
            else:
                web.ctx.status = '405 Method Not Allowed'
        else:
            web.ctx.status = '404 Not Found'
            
    GET = POST = delegate

class infobase_request:
    def delegate(self):
        sitename = web.ctx.site.name
        path = web.lstrips(web.ctx.path, "/api")
        method = web.ctx.method
        data = web.input()
        
        conn = client.connect(**infogami.config.infobase_parameters)            
        out = conn.request(sitename, path, method, data)
        return out
        
    GET = delegate

add_hook("get", infobase_request)
add_hook("things", infobase_request)
add_hook("versions", infobase_request)

