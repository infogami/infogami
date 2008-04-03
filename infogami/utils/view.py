
import web
import os

import infogami
from infogami import tdb
from infogami.core.diff import simple_diff, better_diff
from infogami.utils import i18n
from infogami.utils.markdown import markdown, mdx_footnotes

from context import context
import template
import macro
import storage

#@@ This must be moved to some better place
from infogami.tdb.lru import lrumemoize

wiki_processors = []
def register_wiki_processor(p):
    wiki_processors.append(p)
    
def _register_mdx_extensions(md):
    """Register required markdown extensions."""
    # markdown's interface to specifying extensions is really painful.
    mdx_footnotes.makeExtension({}).extendMarkdown(md, markdown.__dict__)
    macro.makeExtension({}).extendMarkdown(md, markdown.__dict__)
    
def get_markdown(text):
    md = markdown.Markdown(source=text, safe_mode=False)
    _register_mdx_extensions(md)
    md.postprocessors += wiki_processors
    return md

def get_doc(text):
    return get_markdown(text)._transform()

web.template.Template.globals.update(dict(
  changequery = web.changequery,
  url = web.url,
  datestr = web.datestr,
  numify = web.numify,
  ctx = context,
  _ = i18n.strings,
  macros = storage.ReadOnlyDict(macro.macrostore),
  diff = simple_diff,
  better_diff = better_diff,
  find_i18n_namespace = i18n.find_i18n_namespace,
    
  # common utilities
  int = int,
  str = str,
  bool=bool,
  list = list,
  set = set,
  dict = dict,
  min = min,
  max = max,
  range = range,
  len = len,
  repr=repr,
  isinstance=isinstance,
  enumerate=enumerate,
  hasattr = hasattr,
  Dropdown = web.form.Dropdown,
  slice = slice,
  debug = web.debug,
))

render = template.render

def public(f):
    """Exposes a funtion in templates."""
    web.template.Template.globals[f.__name__] = f
    return f

@public    
def safeint(value):
    """Convers the value to integer. Returns 0, if the conversion fails."""
    try:
        return int(value)
    except Exception:
        return 0

@public
def query_param(name, default=None):
    i = web.input(_m='GET')
    return i.get(name, default)

@public
def join(sep, items):
    items = [web.utf8(item or "") for item in items]
    return web.utf8(sep).join(items)
    
@public
def format(text):
    html, macros = _format(text)
    return macro.replace_macros(html, macros)
    
@lrumemoize(1000)
def _format(text):
    text = web.utf8(text).decode('utf-8')
    md = get_markdown(text)
    html = md.convert().encode('utf-8')
    return html, md.macros

@public
def link(path, text=None):
    return '<a href="%s">%s</a>' % (web.ctx.homepath + path, text or path)

@public
def homepath():
    return web.ctx.homepath        

@public
def add_stylesheet(path):
    if web.url(path) not in context.stylesheets:
        context.stylesheets.append(web.url(path))
    return ""
    
@public
def add_javascript(path):
    if web.url(path) not in context.javascripts:
        context.javascripts.append(web.url(path))
    return ""

@public
def spacesafe(text):
    text = web.websafe(text)
    #@@ TODO: should take care of space at the begining of line also
    text = text.replace('  ', ' &nbsp;');
    return text

def value_to_thing(value, type):
    if value is None: value = ""
    return web.storage(value=value, is_primitive=True, type=type)
    
def set_error(msg):
    if not context.error: context.error = ''
    context.error += '\n' + msg

def render_site(url, page):
    return render.site(page)

@public
def thingrepr(value, type=None):
    if isinstance(value, list):
        return ','.join(thingrepr(t, type) for t in value)
        
    from infogami.infobase import client        
    if type is None and value is client.nothing:
        return ""
    
    if isinstance(value, client.Thing):
        type = value.type
        
    return render.repr(thingify(type, value))
        
@public
def thinginput(type, name, value, **attrs):
    """Renders html input field of given type."""
    return render.input(thingify(type, value), name)
    
def thingify(type, value):
    # if type is given as string then get the type from db
    if type is None:
        type = '/type/string'
        
    if isinstance(type, basestring):
        from infogami.core import db
        type = db.get_version(type)
        
    PRIMITIVE_TYPES = "/type/key", "/type/string", "/type/text", "/type/int", "/type/float", "/type/boolean"    
    from infogami.infobase import client
        
    if type.key not in PRIMITIVE_TYPES and isinstance(value, basestring) and not value.strip():
        value = web.ctx.site.new('', {'type': type})

    if type.key not in PRIMITIVE_TYPES and isinstance(value, client.Nothing):
        value = web.ctx.site.new('', {'type': type})
    
    # primitive values
    if not isinstance(value, client.Thing):
        value = web.storage(value=value, is_primitive=True, type=type)
        
    return value

@public
def thingdiff(type, name, v1, v2):
    if v1 == v2:
        return ""
    else:
        return render.xdiff(thingify(type, v1), thingify(type, v2), name)
        
@public
def thingview(page):
    return render.view(page)

@public    
def thingedit(page):
    return render.edit(page)

@infogami.install_hook
@infogami.action
def movefiles():
    """Move files from every plugin into static directory."""    
    import delegate
    import shutil
    def cp_r(src, dest):
        if not os.path.exists(src):
            return
            
        if os.path.isdir(src):
            if not os.path.exists(dest):
                os.mkdir(dest)
            for f in os.listdir(src):
                frm = os.path.join(src, f)
                to = os.path.join(dest, f)
                cp_r(frm, to)
        else:
            print 'copying %s to %s' % (src, dest)
            shutil.copy(src, dest)
    
    static_dir = os.path.join(os.getcwd(), "static")
    for plugin in delegate.plugins:
        src = os.path.join(plugin.path, "files")
        cp_r(src, static_dir)

@infogami.install_hook
def movetypes():
    def property(type, name, expected_type, unique, rendering_hint=None):
        q = {
            'create': 'unless_exists',
            'key': type + '/' + name,
            'name': name,
            'type': '/type/property',
            'expected_type': expected_type,
            'unique': unique
        }
        if rendering_hint:
            q['rendering_hint'] = rendering_hint
        return q
        
    def backreference(type, name, expected_type, property_name):
        return {
            'create': 'unless_exists',
            'key': type + '/' + name,
            'name': name,
            'type': '/type/backreference',
            'expected_type': expected_type,
            'property_name': property_name
        }
        
    def readfunc(text):
        return eval(text, {'property': property, 'backreference': backreference})
    move("types", ".type", recursive=False, readfunc=readfunc)

@infogami.install_hook
def movepages():
    move('pages', '.page', recursive=False)

def move(dir, extension, recursive=False, readfunc=None):
    import delegate
        
    readfunc = readfunc or eval
    pages = []    
    for p in delegate.plugins:
        path = os.path.join(p.path, dir)
        if os.path.exists(path) and os.path.isdir(path):
            files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith(extension)]
            for f in files:
                type = readfunc(open(f).read())
                pages.append(type)

    delegate.admin_login()
    result = web.ctx.site.write(pages, "install")
    for key in result.created:
        print 'created', key
    for key in result.updated:
        print 'updated', key

@infogami.action
def write(filename):
    q = open(filename).read()
    print web.ctx.site.write(q)
    

# this is not really the right place to move this, but couldn't find a better place than this.     
def require_login(f):
    def g(*a, **kw):
        if not web.ctx.site.get_user():
            return login_redirect()
        return f(*a, **kw)

    return g

def login_redirect(path=None):
    import urllib
    if path is None:
        path = web.ctx.fullpath

    query = urllib.urlencode({"redirect":path})
    web.seeother("/account/login?" + query)
    raise StopIteration
