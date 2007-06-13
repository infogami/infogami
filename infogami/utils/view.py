from infogami.utils.markdown import markdown, mdx_footnotes
from context import context
import web
import os
from infogami import config, tdb
from infogami.utils.i18n import i18n
from storage import storage
import macro

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
  query = tdb.Things, #@@not safe
  _ = i18n(),
  
  # common utilities
  int = int,
  str = str,
  list = list,
  set = set,
  dict = dict,
  range = range,
  len = len,
  enumerate=enumerate,
  hasattr = hasattr,
  Dropdown = web.form.Dropdown,
))

render = web.storage()

def public(f):
    """Exposes a funtion in templates."""
    web.template.Template.globals[f.__name__] = f
    return f

@public
def format(text):
    return get_markdown(text).convert()

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
    context.stylesheets.append(url(path))
    return ""
    
@public
def add_javascript(path):
    context.javascripts.append(url(path))
    return ""

@public
def spacesafe(text):
    text = web.websafe(text)
    text = text.replace(' ', '&nbsp;');
    return text
    
def set_error(msg):
    if not context.error: context.error = ''
    context.error += ' ' + msg

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

_inputs = storage.utils_inputs

@public
def render_input(type, name, value, **attrs):
    """Renders html input field of given type."""
    #@@ quick fix for type='thing foo'
    type = type.split()[0]
    return _inputs[type](name, value, **attrs)
    
def register_input_renderer(type, f):
    _inputs[type] = f
