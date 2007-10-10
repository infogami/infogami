"""
Plugin to move pages between wiki and disk.

This plugin provides 2 actions: push and pull.
push moves pages from disk to wiki and pull moves pages from wiki to disk.

TODOs:
* As of now pages are stored as python dict. Replace it with a human-readable format.
"""

import web
import os

import infogami
from infogami import tdb
from infogami.core import db
from infogami.utils import delegate
from infogami.utils.context import context

def listfiles(root, filter=None):
    """Returns an iterator over all the files in a directory recursively.
    If filter is specified only those, which match the filter are returned.
    The returned paths will be relative to root.
    """
    if not root.endswith(os.sep):
        root += os.sep
        
    for dirname, dirnames, filenames in os.walk(root):
        for f in filenames:
            path = os.path.join(dirname, f)
            path = path[len(root):]
            if filter is None or filter(path):
                yield path

@infogami.action        
def push(root):
    """Move pages from disk to wiki."""
    pages = _readpages(root)
    _pushpages(pages)
    
def _readpages(root):
    def storify(d):
        """Recursively converts dict to web.storage object."""
        if isinstance(d, dict):
            return web.storage([(k, storify(v)) for k, v in d.items()])
        else:
            return d
            
    def read(root, path):
        path = path or "__root__"    
        text = open(os.path.join(root, path + ".page")).read()
        d = eval(text)
        return storify(d)
        
    pages = {}
    for path in listfiles(root, filter=lambda path: path.endswith('.page')):
        path = path[:-len(".page")]
        if path == "__root__":
            name = ""
        else:
            name = path
        pages[name] = read(root, path)
    return pages

def _pushpages(pages):
    """Push pages in the proper order."""
    def getthing(thing, create=False):
        if isinstance(thing, tdb.Thing):
            return thing
        else:
            name = thing
            try:
                return db.get_version(context.site, name)
            except:
                if create:
                    thing = db.new_version(context.site, name, getthing("type/thing"), {})
                    thing.save()
                    return thing
                else:
                    raise
            
    def postorder_traversal(nodes, getchildren, visitor, breakcycle):
        """Performs post-order traversal over graph rooted at `node`. 
        `getchildren(node)` returns children of node in the graph.
        `visitor(node)` is called when a node is visited. 
        Incase there is a cycle in the graph, `breakcycle(node)` is called 
        to take the necessary action.
        """
        print >> web.debug, 'postorder_traversal'
        visited = {}
        visiting = {}
        
        def visit(node):
            print >> web.debug, 'visit:', node
            if node in visited:
                return
            elif node in visiting:
                return breakcycle(node)
            else:
                print >> web.debug, 'visit: visiting node', node
                visiting[node] = 1
                visit_all(getchildren(node))
                visitor(node)
                visited[node] = 1
                del visiting[node]
        
        def visit_all(nodes):
            for n in nodes: 
                visit(n)
                
        visit_all(nodes)
                
    def save_all_pages(pages):
        def get_compound_properties(type):
            """Returns names of all non-primitive properties of a type."""
            return [p.name for p in type.d.properties if not getthing(p.d.type).d.get('is_primitive')]

        def getchildren(name):
            if name in pages:
                page = pages[name]
                yield page.type

                type = pages.get(page.type) or getthing(page.type)
                for k in get_compound_properties(type):
                    v = page.d.get(k)
                    if v is not None and isinstance(v, str): 
                        yield v
                    else:
                        assert isinstance(v, dict)
                        
        def breakcycle(name):
            """When there is a cycle in the graph, a thing with that name 
            must be created to break the cycle."""
            print >> web.debug, 'breakcycle: ', name
            getthing(name, create=True)
            
        postorder_traversal(pages.keys(), getchildren, savepage, breakcycle)
        
    def thingify(data, type, getparent):
        """If type is primitive, return the same.
        """
        type = getthing(type)
        if type.d.get('is_primitive'):
            return data
        elif isinstance(data, str):
            return getthing(data)
        elif isinstance(data, dict):
            name = data.name
            #@@ Why data.type is not used? need any assertion?
            thing = db.new_version(getparent(), name, type, data.d)
            thing.save()
            return thing
        else:
            raise ValueError, data, type
        
    def savepage(name):
        if name not in pages:
            print >> web.debug, 'savepage: ignoring', name
            # when name is not in pages, just make sure that page is present in the wiki.
            return getthing(name)
            
        print >> web.debug, 'savepage: saving page', name
            
        page = pages[name]
        name = page.name
        type = getthing(page.type)
        d = {}
        
        getself = lambda: getthing(name, create=True)
        
        for p in type.d.properties:
            if p.name in page.d:
                d[p.name] = thingify(page.d[p.name], p.d.type, getself)
        
        _page = db.new_version(context.site, name, type, d)
        _page.save()
        
    print >> web.debug, '_pushpages'
    save_all_pages(pages)
        
@infogami.action
def pull(root, paths_files):
    """Move specified pages from wiki to disk."""
    pages = {}
    paths = [line.strip() for line in open(paths_files).readlines()]
    for path in paths:
        print >> web.debug, "pulling page", path
        _pullone(root, path)

def _pullone(root, path):
    def simplify(x, page):
        if isinstance(x, tdb.Thing):
            # for type/property-like values
            if x.parent.id == page.id:
                return thing2dict(x)
            else:
                return x.name
        elif isinstance(x, list):
            return [simplify(a, page) for a in x]
        else:
            return x
            
    def thing2dict(page):
        data = dict(name=page.name, type=page.type.name)
        d = data['d'] = {}
        for k, v in page.d.iteritems():
            d[k] = simplify(v, page)
        return data
            
    def write(path, data):
        dir = os.path.dirname(filepath)
        if not os.path.exists(dir):
            os.makedirs(dir)
        f = open(filepath, 'w')
        f.write(repr(data))
        f.close()
        
    page = db.get_version(context.site, path)
    data = thing2dict(page)
    name = page.name or "__root__"
    filepath = os.path.join(root, name + ".page") 
    write(filepath, data)
    
@infogami.install_hook
@infogami.action
def moveallpages():
    """Move pages from all plugins."""
    pages = {}
    for plugin in delegate.plugins:
        path = os.path.join(plugin.path, 'pages')
        pages.update(_readpages(path))
    _pushpages(pages)