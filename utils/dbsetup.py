"""
utility to create and upgrade infogami database.
"""

import web
import glob

modules = []

class module:
    def __init__(self, name):
        self.name = name
        self.upgrades = []
        modules.append(self)

    def get_version(self):
        try:
            name = self.name
            d = web.query("SELECT * from metadata where name=$name", vars=locals())[0].version
        except:
            return 0

    def upgrade(self, f):
        self.upgrades.append(f)
        return f

    def apply_upgrades(self):
        version = self.get_version()
        for f in self.upgrades[version:]:
            print 'applying upgrade: %s.%s (%s)' % (self.name, f.__name__, f.__doc__)
            f()

        name = self.name
        if version == 0:
            web.insert("metadata", name=name, version=len(self.upgrades))
        else:
            web.update("metadata", where="name=$name", version=len(self.upgrades), vars=locals())

upgrade = module("system").upgrade

@upgrade
def setup():
    """setup db upgrade system."""

    web.query("""
        CREATE TABLE metadata (
            id serial primary key, 
            name text unique,
            version int
        )
    """);

def _load():
    import config
    web.load()
    from core import schema
    for f in glob.glob('plugins/*/schema.py'):
        module = f.replace('/', '.')[:-3]
        __import__(module, globals(), locals(), ['plugins'])

def apply_upgrades():
    _load()
    try:
        web.transact()
        for m in modules:
            print 'applying upgrades for', m.name
            m.apply_upgrades()
    except:
        web.rollback()
        print 'upgrade failed.'
        raise
    else:
        web.commit()
        print 'upgrade successful.'
