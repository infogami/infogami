
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
    d = web.storage(value=value)
    thing = web.storage(d=web.storage(value=value), name="", type=type)
    thing.update(d)
    return thing
    
def set_error(msg):
    if not context.error: context.error = ''
    context.error += '\n' + msg

def render_site(url, page):
    return render.site(page)

@public
def thingrepr(value, type=None):
    if isinstance(value, list):
        return ','.join(thingrepr(t, type) for t in value)

    # and some more? DefaultThing etc?
    if isinstance(value, (tdb.Thing, dict)):
        return render.repr(value)
    else:
        value = value_to_thing(value, type)
        return render.repr(value)
        
@public
def thinginput(type, name, value, **attrs):
    """Renders html input field of given type."""
    if isinstance(type, basestring):
        from infogami.core import db
        type = db.get_type(context.site, type)
        
    if type.d.get("is_primitive"):
        value = value_to_thing(value, type)
    elif not isinstance(value, (tdb.Thing, dict)):
        from infogami.core import thingutil
        value = thingutil.DefaultThing(type)
    
    return render.input(value, name)

@public
def thingdiff(type, name, v1, v2):
    if v1 == v2:
        return ""
    else:
        if not isinstance(v1, tdb.Thing): v1 = value_to_thing(v1, type)
        if not isinstance(v2, tdb.Thing): v2 = value_to_thing(v2, type)
        return render.xdiff(v1, v2, name)
        
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

