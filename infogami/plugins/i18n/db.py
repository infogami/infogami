import web


def get_all_strings(site):
    t = site.get('/type/i18n')
    if t is None:
        return []
    else:
        q = {'type': '/type/i18n', 'limit': 1000}
        return site.get_many(site.things(q))


def get_all_sites():
    if web.ctx.site.exists():
        return [web.ctx.site]
    else:
        return []
