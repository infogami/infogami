from utils import markdown
import web
import os

def keyencode(text): return text.replace(' ', '_')
def keydecode(text): return text.replace('_', ' ')

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

web.template.Template.globals.update(dict(
  changequery = web.changequery,
  datestr = web.datestr,
  numify = web.numify,
  format = format,
))

render = web.template.render('utils/templates/')

def add_stylesheet(plugin, path):
    fullpath = "%s/static/%s/%s" % (web.ctx.homepath, plugin, path)
    web.ctx.stylesheets.append(fullpath)

def render_site(page):
    return render.site(page, web.ctx.stylesheets)

def get_static_resource(path):
    rx = web.re_compile(r'^static/([^/]*)/(.*)$')
    result = rx.match(path)
    if not result:
        return web.notfound()

    plugin, path = result.groups()

    # this distinction will go away when core is also treated like a plugin.
    if plugin == 'core':
        fullpath = "core/static/%s" % (path)
    else:
        fullpath = "plugins/%s/static/%s" % (plugin, path)

    if not os.path.exists(fullpath):
        return web.notfound()
    else:
        return open(fullpath).read()
    
