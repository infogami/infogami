import web
from infogami.infobase import client

def get_all_strings(site):
    t = site.get('/type/i18n')
    if t is None:
        return []
    else:
        q = {'type': '/type/i18n'}
        return site.get_many(site.things(q))

def get_all_sites():
    return [web.ctx.site]
