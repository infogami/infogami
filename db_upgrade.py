"""
Script for handling infogami database version upgrades.

Applies all upgrades since the last successful upgrade to the database 
and increments the db version accordingly.
"""
import config
import web

def get_db_version():
    try:
        d = web.query("select version from metadata")
        return (d and d[0].version) or 0
    except:
        return 0

upgrades = []
def upgrade(f):
    upgrades.append(f)
    return f

def apply_upgrades():
    version = get_db_version()
    try:
        web.transact()
        for f in upgrades[version:]:
            print 'appling upgrade: %s (%s)' % (f.__name__, f.__doc__)
            f()

        web.update("metadata", where="id=1", version=len(upgrades))
    except:
        web.rollback()
        print  'upgrade failed.'
        raise
    else:
        web.commit()
        print 'upgrade successful.'

@upgrade
def add_metadata():
    """metadata table is added to database to keep track of db version."""
    web.query("CREATE TABLE metadata (id serial primary key, version int)"); 
    web.insert("metadata", version=0)

@upgrade
def add_login_table():
    """add login table"""
    web.query("""
        CREATE TABLE login (
          id serial primary key,
          name text unique,
          email text,
          password text
        )""")

def initialize_revisions():
    pages = web.query("SELECT * FROM page")

    for p in pages:
        page_id = p.id
        versions = web.query("SELECT * FROM version WHERE page_id=$page_id", vars=locals())
        for i, v in enumerate(versions):
            id = v.id
            web.update('version', where='id=$id', revision=i+1, vars=locals())

@upgrade
def add_login_table():
    """add login table"""
    web.query("""
        CREATE TABLE login (
          id serial primary key,
          name text unique,
          email text,
          password text
        )""")

@upgrade
def add_login_table():
    """add login table"""
    web.query("""
        CREATE TABLE login (
          id serial primary key,
          name text unique,
          email text,
          password text
        )""")

@upgrade
def add_version_revision():
    """revision column is added to version table."""
    web.query("ALTER TABLE version ADD COLUMN revision int")
    initialize_revisions()

@upgrade
def add_review_table():
    """adding review column to support user review for pages."""
    web.query("""
        CREATE TABLE review (
            id serial primary key,
            site_id int references site,
            page_id int references page,
            user_id int references login,
            revision int,
            unique (site_id, page_id, user_id)
        )""")

@upgrade
def add_review_table():
    """adding review column to support user review for pages."""
    web.query("""
        CREATE TABLE review (
            id serial primary key,
            site_id int references site,
            page_id int references page,
            user_id int references login,
            revision int,
            unique (site_id, page_id, user_id)
        )""")

if __name__ == "__main__":
    web.load()
    apply_upgrades()
