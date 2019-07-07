import web

def get_all_templates(site):
    t = site.get('/type/template')
    if t is None:
        return []
    q = {'type': '/type/template', 'limit': 1000}
    #return [site.get(key) for key in site.things(q)]
    return site.get_many([key for key in site.things(q)])

def get_all_macros(site):
    t = site.get('/type/macro')
    if t is None:
        return []
    q = {'type': '/type/macro', 'limit': 1000}
    #return [site.get(key) for key in site.things(q)]
    return site.get_many([key for key in site.things(q)])

def get_all_sites():
    if web.ctx.site.exists():
        return [web.ctx.site]
    else:
        return []
