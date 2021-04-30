"""
Plugin to move pages between wiki and disk.

This plugin provides 2 actions: push and pull.
push moves pages from disk to wiki and pull moves pages from wiki to disk.

TODOs:
* As of now pages are stored as python dict. Replace it with a human-readable format.
"""
from __future__ import print_function

import os

from six import iteritems
import web

import infogami
from infogami import tdb
from infogami.core import db
from infogami.utils import delegate
from infogami.utils.context import context


def listfiles(root, filter=None):
    """Returns an iterator over all the files in a directory recursively.
    If filter is specified only those files matching the filter are returned.
    Returned paths will be relative to root.
    """
    if not root.endswith(os.sep):
        root += os.sep

    for dirname, dirnames, filenames in os.walk(root):
        for f in filenames:
            path = os.path.join(dirname, f)
            path = path[len(root) :]
            if filter is None or filter(path):
                yield path


def storify(d):
    """Recursively converts dict to web.storage object.

    >>> d = storify({'x: 1, y={'z': 2}})
    >>> d.x
    1
    >>> d.y.z
    2
    """
    if isinstance(d, dict):
        return web.storage([(k, storify(v)) for k, v in d.items()])
    elif isinstance(d, list):
        return [storify(x) for x in d]
    else:
        return d


def _readpages(root):
    """Reads and parses all root/*.page files and returns results as a dict."""

    def read(root, path):
        path = path or "__root__"
        text = open(os.path.join(root, path + ".page")).read()
        d = eval(text)
        return storify(d)

    pages = {}
    for path in listfiles(root, filter=lambda path: path.endswith('.page')):
        path = path[: -len(".page")]
        if path == "__root__":
            name = ""
        else:
            name = path
        pages[name] = read(root, path)
    return pages


def _savepage(page, create_dependents=True, comment=None):
    """Saves a page from dict."""

    def getthing(name, create=False):
        if isinstance(name, tdb.Thing):
            return name
        try:
            return db.get_version(context.site, name)
        except:
            if create and create_dependents:
                thing = db.new_version(context.site, name, getthing("type/thing"), {})
                thing.save()
                return thing
            else:
                raise

    def thingify(data, getparent):
        """Converts data into thing or primitive value."""
        if isinstance(data, list):
            return [thingify(x, getparent) for x in data]
        elif isinstance(data, dict):
            name = data.name
            if data.get('child'):
                d = dict([(k, thingify(v, getparent)) for k, v in data.d.items()])
                type = thingify(data.type, getparent)
                thing = db.new_version(getparent(), name, type, d)
                thing.save()
                return thing
            else:
                return getthing(name, create=True)
        else:
            return data

    name = page.name
    type = getthing(page.type.name, create=True)
    d = {}

    getself = lambda: getthing(name, create=True)
    for k, v in page.d.items():
        d[k] = thingify(v, getself)

    _page = db.new_version(context.site, name, type, d)
    _page.save(author=context.user, comment=comment, ip=web.ctx.ip)
    return _page


def thing2dict(page):
    """Converts thing to dict."""

    def simplify(x, page):
        if isinstance(x, tdb.Thing):
            # for type/property-like values
            if x.parent.id == page.id:
                t = thing2dict(x)
                t['child'] = True
                return t
            else:
                return dict(name=x.name)
        elif isinstance(x, list):
            return [simplify(a, page) for a in x]
        else:
            return x

    data = dict(name=page.name, type={'name': page.type.name})
    d = data['d'] = {}
    for k, v in iteritems(page.d):
        d[k] = simplify(v, page)
    return data


@infogami.action
def pull(root, paths_files):
    """Move specified pages from wiki to disk."""

    def write(path, data):
        dir = os.path.dirname(filepath)
        if not os.path.exists(dir):
            os.makedirs(dir)
        f = open(filepath, 'w')
        f.write(repr(data))
        f.close()

    pages = {}
    paths = [line.strip() for line in open(paths_files).readlines()]
    paths2 = []

    for path in paths:
        if path.endswith('/*'):
            path = path[:-2]  # strip trailing /*
            paths2 += [p.name for p in db._list_pages(context.site, path)]
        else:
            paths2.append(path)

    for path in paths2:
        print("pulling page", path, file=web.debug)
        page = db.get_version(context.site, path)
        name = page.name or '__root__'
        data = thing2dict(page)
        filepath = os.path.join(root, name + ".page")
        write(filepath, data)


@infogami.action
def push(root):
    """Move pages from disk to wiki."""
    pages = _readpages(root)
    _pushpages(pages)


def _pushpages(pages):
    tdb.transact()
    try:
        for p in pages.values():
            print('saving', p.name)
            _savepage(p)
    except:
        tdb.rollback()
        raise
    else:
        tdb.commit()


@infogami.install_hook
@infogami.action
def moveallpages():
    """Move pages from all plugins."""
    pages = {}
    for plugin in delegate.plugins:
        path = os.path.join(plugin.path, 'pages')
        pages.update(_readpages(path))
    _pushpages(pages)


@infogami.action
def tdbdump(filename, created_after=None, created_before=None):
    """Creates tdb log of entire database."""
    from infogami.tdb import logger

    f = open(filename, 'w')
    logger.set_logfile(f)

    # get in chunks of 10000 to limit the load on db.
    N = 10000
    offset = 0
    while True:
        versions = tdb.Versions(
            offset=offset,
            limit=N,
            orderby='version.id',
            created_after=created_after,
            created_before=created_before,
        ).list()
        offset += N
        if not versions:
            break

        # fill the cache with things corresponding to the versions.
        # otherwise, every thing must be queried separately.
        tdb.withIDs([v.thing_id for v in versions])
        for v in versions:
            t = v.thing
            logger.transact()
            if v.revision == 1:
                logger.log('thing', t.id, name=t.name, parent_id=t.parent.id)

            logger.log(
                'version',
                v.id,
                thing_id=t.id,
                author_id=v.author_id,
                ip=v.ip,
                comment=v.comment,
                revision=v.revision,
                created=v.created.isoformat(),
            )
            logger.log('data', v.id, __type__=t.type, **t.d)
            logger.commit()
    f.close()


@infogami.action
def datadump(filename):
    """Writes dump of latest versions of all pages in the system.
    User info is excluded.
    """

    def dump(predicate=None):
        things = {}
        # get in chunks of 10000 to limit the load on db.
        N = 10000
        offset = 0

        while True:
            things = tdb.Things(
                parent=context.site, offset=offset, limit=N, orderby='thing.id'
            )
            offset += N
            if not things:
                break
            for t in things:
                if predicate and not predicate(t):
                    continue
                data = thing2dict(t)
                f.write(str(data))
                f.write('\n')

    f = open(filename, 'w')
    # dump the everything except users
    dump(lambda t: t.type.name != 'type/user')
    f.close()


@infogami.action
def dataload(filename):
    """Loads data dumped using datadump action into the database."""
    lines = open(filename).xreadlines()
    tdb.transact()
    try:
        for line in lines:
            data = storify(eval(line))
            _savepage(data)
    except:
        tdb.rollback()
        raise
    else:
        tdb.commit()
