"""Feature flags support for Infogami.
"""
import web

from context import context

feature_flags = {}

def set_feature_flags(flags):
    global feature_flags

    # sanity check
    if isinstance(flags, dict):
        feature_flags = flags

filters = {}
def register_filter(name, method):
    filters[name] = method

def call_filter(spec):
    if isinstance(spec, list):
        return any(call_filter(x) for x in spec)
    elif isinstance(spec, dict):
        spec = spec.copy()
        filter_name = spec.pop('filter', None)
        kwargs = spec
    else:
        filter_name = spec
        kwargs = {}

    if filter_name in filters:
        return filters[filter_name](**kwargs)
    else:
        return False

def find_enabled_features():
    return set(f for f, spec in feature_flags.iteritems() if call_filter(spec))

def loadhook():
    features = find_enabled_features()
    web.ctx.features = features
    context.features = features

def is_enabled(flag):
    """Tests whether the given feature flag is enabled for this request.
    """
    return flag in web.ctx.features

def filter_disabled():
    return False

def filter_enabled():
    return True

def filter_loggedin():
    return context.user is not None

def filter_admin():
    return filter_usergroup("/usergroup/admin")

def filter_usergroup(usergroup):
    """Returns true if the current user is member of the given usergroup."""
    def get_members():
        return [m.key for m in web.ctx.site.get(usergroup).members]

    return context.user and context.user.key in get_members()

def filter_queryparam(name, value):
    """Returns true if the current request has a queryparam with given name and value."""
    i = web.input(_method="GET")
    return i.get(name) == value

register_filter("disabled", filter_disabled)
register_filter("enabled", filter_enabled)
register_filter("admin", filter_admin)
register_filter("loggedin", filter_loggedin)
register_filter("usergroup", filter_usergroup)
register_filter("queryparam", filter_queryparam)
