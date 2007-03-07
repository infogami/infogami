from infogami.utils import markdown
import web
import os
from infogami import config

wiki_processors = []
def register_wiki_processor(p):
    wiki_processors.append(p)

def get_markdown(text):
    md = markdown.Markdown(source=text, safe_mode=False)
    md.postprocessors += wiki_processors
    return md

def get_doc(text):
    return get_markdown(text)._transform()

def format(text): 
    return str(get_markdown(text))

def link(path, text=None):
    return '<a href="%s">%s</a>' % (web.ctx.homepath + path, text or path)

def url(path):
    if path.startswith('/'):
        return web.ctx.homepath + path
    else:
        return path

def add_stylesheet(path):
    web.ctx.stylesheets.append(url(path))
    return ""

def spacesafe(text):
    text = web.websafe(text)
    text = text.replace(' ', '&nbsp;');
    return text

web.template.Template.globals.update(dict(
  changequery = web.changequery,
  datestr = web.datestr,
  numify = web.numify,
  format = format,
  link = link,
  url = url,
  add_stylesheet = add_stylesheet,
  spacesafe = spacesafe,
))

render = web.storage()

def load_templates(dir):
    cache = getattr(config, 'cache_templates', True)

    path = dir + "/templates/"
    if os.path.exists(path):
        name = os.path.basename(dir)
        render[name] = web.template.render(path, cache=cache)

def render_site(url, page):
    from infogami.core import auth
    user = auth.get_user()
    return render.core.site(page, user, web.ctx.stylesheets)

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
    
