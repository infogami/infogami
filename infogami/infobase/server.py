"""Infobase server to expose the API.
"""
import web
import infobase
import simplejson

urls = (
    "/([^/]*)/get/(.*)", "withkey",
    "/([^/]*)/things", "things",
    "/([^/]*)/versions", "versions",
    "/([^/]*)/write", "write",
)

def jsonify(f):
    def g(self, *a, **kw):
        d = {'status': 'ok'}
        try:
            d['result'] = f(self, *a, **kw)
        except infobase.InfobaseException, e:
            d['status'] = 'fail'
            d['message'] = '%s: %s' % (e.__class__.__name__, str(e))
        except Exception, e:
            import traceback
            traceback.print_exc()
            d['status'] = 'fail'
            d['message'] = 'InternalError: %s' % str(e)
        result = simplejson.dumps(d)
        if web.ctx.get('infobase_localmode'):
            return result
        else:
            print result
    return g
    
def readdata():
    if web.ctx.get('infobase_localmode'):
        return web.ctx.infobase_data
    else:
        return web.data()
    
ibase = None
def get_site(sitename):
    global ibase
    if not ibase:
        ibase = infobase.Infobase()
    return ibase.get_site(sitename)

class write:
    @jsonify
    def POST(self, sitename):
        site = get_site(sitename)
        query = simplejson.loads(readdata())
        result = site.write(query)
        return result

class withkey:
    @jsonify
    def GET(self, sitename, key):
        try:
            i = input(revision=None)
            site = get_site(sitename)
            thing = site.withKey(key, revision=i.revision)
            return thing._get_data()
        except infobase.NotFound:
            return None
            
def input(*a, **kw):
    if 'infobase_input' in web.ctx:
        return web.storify(web.ctx.infobase_input, *a, **kw)
    else:
        return web.input(*a, **kw)
        
class things:
    @jsonify
    def GET(self, sitename):
        site = get_site(sitename)
        i = input('query')
        q = simplejson.loads(i.query)
        return site.things(q)

class versions:
    @jsonify
    def GET(self, sitename):
        site = get_site(sitename)
        i = input('query')
        q = simplejson.loads(i.query)
        return site.versions(q)
        
def request(path, method, data):
    """Fakes the web request.
    Useful when infobase is not run as a separate process.
    """
    web.ctx.infobase_localmode = True
    web.ctx.infobase_data = data 
    web.ctx.infobase_input = data or {}
    for pattern, classname in web.group(urls, 2):
        m = web.re_compile(pattern).match(path)
        if m:
            args = m.groups()
            cls = globals()[classname]
            tocall = getattr(cls(), method)
            return tocall(*args)

if __name__ == "__main__":
    web.config.db_parameters = dict(dbn='postgres', db='infobase', user='anand', pw='')
    web.config.db_printing = True
    web.run(urls, globals())
