import web

def get_all_templates(site):
    t = site.get('type/template')
    if t is None:
        return []
    q = {'type': 'type/template'}
    return [site.get(key) for key in site.things(q)]

def get_all_macros(site):
    t = site.get('type/macro')
    if t is None:
        return []
    q = {'type': 'type/macro'}
    return [site.get(key) for key in site.things(q)]
    
def get_all_sites():
    return [web.ctx.site]
