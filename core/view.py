import re
from utils import markdown
import web
from utils import delegate

def keyencode(text): return text.replace(' ', '_')
def keydecode(text): return text.replace('_', ' ')

def get_markdown(text):
   md = markdown.Markdown(source=text, safe_mode=False)
   md.postprocessors += delegate.wiki_processors
   return md

def get_doc(text):
    return get_markdown(text)._transform()

def format(text): 
    return str(get_markdown(text))

render = web.template.render('core/templates/', cache=False)

web.template.Template.globals.update(dict(
  changequery = web.changequery,
  datestr = web.datestr,
  numify = web.numify,
  format = format,
))
