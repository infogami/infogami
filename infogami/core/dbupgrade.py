"""
module for doing database upgrades when code changes.
"""
from __future__ import print_function
import infogami
from infogami import tdb

from infogami.core import db
from infogami.utils.context import context as ctx

import web


def get_db_version():
    return tdb.root.d.get('__version__', 0)


upgrades = []


def upgrade(f):
    upgrades.append(f)
    return f


def apply_upgrades():
    from infogami import tdb

    tdb.transact()
    try:
        v = get_db_version()
        for u in upgrades[v:]:
            print('applying upgrade:', u.__name__, file=web.debug)
            u()

        mark_upgrades()
        tdb.commit()
        print('upgrade successful.', file=web.debug)
    except:
        print('upgrade failed', file=web.debug)
        import traceback

        traceback.print_exc()
        tdb.rollback()


@infogami.action
def dbupgrade():
    apply_upgrades()


def mark_upgrades():
    tdb.root.__version__ = len(upgrades)
    tdb.root.save()


@upgrade
def hash_passwords():
    from infogami.core import auth

    tuser = db.get_type(ctx.site, 'type/user')
    users = tdb.Things(parent=ctx.site, type=tuser).list()

    for u in users:
        try:
            preferences = u._c('preferences')
        except:
            # setup preferences for broken accounts, so that they can use forgot password.
            preferences = db.new_version(
                u, 'preferences', db.get_type(ctx.site, 'type/thing'), dict(password='')
            )
            preferences.save()

        if preferences.password:
            auth.set_password(u, preferences.password)


@upgrade
def upgrade_types():
    from infogami.core.db import _create_type, tdbsetup

    tdbsetup()
    type = db.get_type(ctx.site, "type/type")
    types = tdb.Things(parent=ctx.site, type=type)
    types = [t for t in types if 'properties' not in t.d and 'is_primitive' not in t.d]
    primitives = dict(
        int='type/int', integer='type/int', string='type/string', text='type/text'
    )

    newtypes = {}
    for t in types:
        properties = []
        backreferences = []
        print(t, t.d, file=web.debug)
        if t.name == 'type/site':
            continue
        for name, value in t.d.items():
            p = web.storage(name=name)
            typename = web.lstrips(value, "thing ")

            if typename.startswith('#'):
                typename, property_name = typename.lstrip('#').split('.')
                p.type = db.get_type(ctx.site, typename)
                p.property_name = property_name
                backreferences.append(p)
                continue

            if typename.endswith('*'):
                typename = typename[:-1]
                p.unique = False
            else:
                p.unique = True
            if typename in primitives:
                typename = primitives[typename]
            p.type = db.get_type(ctx.site, typename)
            properties.append(p)
        _create_type(ctx.site, t.name, properties, backreferences)
