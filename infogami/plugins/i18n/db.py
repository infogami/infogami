import web
from infogami.infobase import client

def get_all_strings(site):
    t = site.get('/type/i18n')
    if t is None:
        return []
    else:
        q = {'type': '/type/i18n'}
        return [site.get(key) for key in site.things(q)]
    
    return tdb.Things(type=db.get_type(site, 'type/i18n'), parent=site)

def get_all_sites():
    return [web.ctx.site]
