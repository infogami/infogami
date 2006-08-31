import web, config
from core import code

urls = (
  '/(.*)', 'page'
)

def delegate(f):
    def idelegate(self, path):
        what = web.input().get('m', 'view')
        return getattr(code.__dict__[what](), f)(config.site, path)
    return idelegate

class page:
    GET = delegate('GET')
    POST = delegate('POST')