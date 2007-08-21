import web
import os

import infogami
from infogami import config, tdb
from infogami.core.diff import simple_diff
from infogami.utils.i18n import i18n
from infogami.utils.markdown import markdown, mdx_footnotes

from context import context
import macro
import storage

#@@ This must be moved to some better place
from infogami.tdb.lru import lrumemoize

wiki_processors = []
def register_wiki_processor(p):
    wiki_processors.append(p)
    
def register_markdown_extionsion(name, m):
    markdown_extensions[name] = m

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
  datestr = web.datestr,
  numify = web.numify,
  ctx = context,
  _ = i18n(),
  macros = storage.ReadOnlyDict(macro._macros),
  diff = simple_diff,
  
  # common utilities
  int = int,
  str = str,
  bool=bool,
  list = list,
  set = set,
  dict = dict,
  range = range,
  len = len,
  repr=repr,
  isinstance=isinstance,
  enumerate=enumerate,
  hasattr = hasattr,
  Dropdown = web.form.Dropdown,
  slice = slice,
))

render = web.storage()

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
    md = get_markdown(text.decode('utf-8'))
    html = md.convert().encode('utf-8')
    return html, md.macros

@public
def link(path, text=None):
    return '<a href="%s">%s</a>' % (web.ctx.homepath + path, text or path)

@public
def url(path):
    if path.startswith('/'):
        return web.ctx.homepath + path
    else:
        return path

@public
def homepath():
    return web.ctx.homepath        

@public
def add_stylesheet(path):
    if url(path) not in context.stylesheets:
        context.stylesheets.append(url(path))
    return ""
    
@public
def add_javascript(path):
    if url(path) not in context.javascripts:
        context.javascripts.append(url(path))
    return ""

@public
def spacesafe(text):
    text = web.websafe(text)
    text = text.replace(' ', '&nbsp;');
    return text
    
@public
def thingrepr(value):
    if isinstance(value, list):
        return ','.join(thingrepr(t) for t in value)
    if isinstance(value, tdb.Thing):
        return render.core.repr(value)
    else:
        return str(value)
    
def set_error(msg):
    if not context.error: context.error = ''
    context.error += '\n' + msg

def load_templates(dir):
    cache = getattr(config, 'cache_templates', True)

    path = dir + "/templates/"
    if os.path.exists(path):
        name = os.path.basename(dir)
        render[name] = web.template.render(path, cache=cache)

def load_macros(dir):
    cache = getattr(config, 'cache_templates', True)

    path = dir + "/macros/"
    if os.path.exists(path):
        macros = web.template.render(path, cache=cache)
        names = [name[:-5] for name in os.listdir(path) if name.endswith('.html')]
        for name in names:
            macro.register_macro(name, getattr(macros, name))
        
def render_site(url, page):
    return render.core.site(page)

def get_static_resource(path):
    rx = web.re_compile(r'^files/([^/]*)/(.*)$')
    result = rx.match(path)
    if not result:
        return web.notfound()

    plugin, path = result.groups()

    # this distinction will go away when core is also treated like a plugin.
    if plugin == 'core':
        fullpath = "infogami/core/files/%s" % (path)
    else:
        fullpath = "infogami/plugins/%s/files/%s" % (plugin, path)

    if not os.path.exists(fullpath):
        return web.notfound()
    else:
        return open(fullpath).read()

_inputs = storage.storage.utils_inputs

@public
def render_input(type, name, value, **attrs):
    """Renders html input field of given type."""
    return _inputs.get(type.name, _inputs['type/string'])(name, value, **attrs)
    
def register_input_renderer(typename, f):
    _inputs[typename] = f

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
