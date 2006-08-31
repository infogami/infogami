import re
import markdown
import web

def keyencode(text): return text.replace(' ', '_')
def keydecode(text): return text.replace('_', ' ')

link_re = web.re_compile(r'(?<!\\)\[\[(.*?)(?:\|(.*?))?\]\]')
def do_links(text, links=False):
    linksto = []

    #@@ needs to not replace in <pre> and so on

    def mangle(match):
        t = match.group()
        matches = match.groups()
        link = matches[0]
        anchor = matches[1] or link
        link = keyencode(link)
        linksto.append(link)
        return '<a class="internal" href="/%s">%s</a>' % (link, anchor)

    text = re.sub(link_re, mangle, text)
    if links: return linksto
    return text

def format(text): return do_links(markdown.markdown(text))

render = web.template.render('core/templates/', cache=False)

web.template.Template.globals.update(dict(
  changequery = web.changequery,
  datestr = web.datestr,
  numify = web.numify,
  format = format,
))
