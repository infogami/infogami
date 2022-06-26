import web

from infogami.utils.view import public


def get_version(path, revision=None):
    return web.ctx.site.get(path, revision)


@public
def get_type(path):
    return get_version(path)


@public
def get_expected_type(page, property_name):
    """Returns the expected type of a property."""
    defaults = {
        "key": "/type/key",
        "type": "/type/type",
        "permission": "/type/permission",
        "child_permission": "/type/permission",
    }

    if property_name in defaults:
        return defaults[property_name]

    for p in page.type.properties:
        if p.name == property_name:
            return p.expected_type

    return "/type/string"


def new_version(path, type):
    if isinstance(type, str):
        type = get_type(type)

    assert type is not None
    return web.ctx.site.new(path, {'key': path, 'type': type})


@public
def get_i18n_page(page):
    key = page.key
    if key == '/':
        key = '/index'

    def get(lang):
        return lang and get_version(key + '.' + lang)

    return get(web.ctx.lang) or get('en') or None


class ValidationException(Exception):
    pass


def get_user_preferences(user):
    return get_version(user.key + '/preferences')


@public
def get_recent_changes(
    key=None, author=None, ip=None, type=None, bot=None, limit=None, offset=None
):
    q = {'sort': '-created'}
    if key is not None:
        q['key'] = key

    if author:
        q['author'] = author.key

    if type:
        q['type'] = type

    if ip:
        q['ip'] = ip

    if bot is not None:
        q['bot'] = bot

    q['limit'] = limit or 100
    q['offset'] = offset or 0
    result = web.ctx.site.versions(q)
    for r in result:
        r.thing = web.ctx.site.get(r.key, r.revision, lazy=True)
    return result


@public
def list_pages(path, limit=100, offset=0):
    """Lists all pages with name path/*"""
    return _list_pages(path, limit=limit, offset=offset)


def _list_pages(path, limit, offset):
    q = {}
    if path != '/':
        q['key~'] = path + '/*'

    # don't show /type/delete and /type/redirect
    q['a:type!='] = '/type/delete'
    q['b:type!='] = '/type/redirect'

    q['sort'] = 'key'
    q['limit'] = limit
    q['offset'] = offset
    # queries are very slow with != conditions
    # q['type'] != '/type/delete'
    return [web.ctx.site.get(key, lazy=True) for key in web.ctx.site.things(q)]


def get_things(typename, prefix, limit):
    """Lists all things whose names start with typename"""
    q = {'key~': prefix + '*', 'type': typename, 'sort': 'key', 'limit': limit}
    return [web.ctx.site.get(key, lazy=True) for key in web.ctx.site.things(q)]
