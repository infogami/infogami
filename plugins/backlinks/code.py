"""
backlinks: keep track of what links where

Creates a new set of database tables to keep track of link structure
and creates a new `m=backlinks` to display the results.
"""

from utils import delegate
import db
import web
from core import view
import re

render = web.template.render('plugins/backlinks/templates/')

class hooks:
    __metaclass__ = delegate.hook
    def on_new_version(site, path, data):
        db.new_links(site, path, get_links(data))

class backlinks (delegate.mode):
    def GET(self, site, path):
        links = db.get_links(site, path)
        print render.backlinks(links)

def get_links(text):
    """Returns all links in the text."""
    doc = view.get_doc(text)
    def is_link(e):
        return e.type == 'element'      \
            and e.nodeName == 'a'       \
            and e.attribute_values.get('class', '') == 'internal'

    links = []
    for a in  doc.find(is_link):
       links.append(a.attribute_values['href']) 

    return links

link_re = web.re_compile(r'(?<!\\)\[\[(.*?)(?:\|(.*?))?\]\]')
class wikilinks:
    """markdown postprocessor for [[wikilink]] support."""
    def process_links(self, node):
        print >> web.debug, '-- begin --', repr(node.value)
        doc = node.doc
        text = node.value
        new_nodes = []
        position = [0]

        def mangle(match):
            start, end = position[0], match.start()
            position[0] = match.end()
            text_node = doc.createTextNode(text[start:end])

            matches = match.groups()
            link = matches[0]
            anchor = matches[1] or link
            #link = keyencode(link)

            print >> web.debug, '**', start, end, text_node.value

            link_node = doc.createElement('a')
            link_node.setAttribute('href', link)
            link_node.setAttribute('class', 'internal')
            link_node.appendChild(doc.createTextNode(anchor))

            new_nodes.append(text_node)
            new_nodes.append(link_node)

            return ''

        re.sub(link_re, mangle, text)

        start = position[0]
        end = len(text)
        text_node = doc.createTextNode(text[start:end])
        print >> web.debug, '**', start, end, text_node.value
        print >> web.debug, '-- end --'

        new_nodes.append(text_node)

        return new_nodes

    def replace_node(self, node, new_nodes):
        """Removes the node from its parent and inserts new_nodes at that position."""
        parent = node.parent
        position = parent.childNodes.index(node)
        parent.removeChild(node)

        for n in new_nodes:
            parent.insertChild(position, n)
            position += 1

    def run(self, doc):
        def test(e):
            return e.type == 'text' and link_re.search(e.value)

        for node in doc.find(test):
            new_nodes = self.process_links(node)
            self.replace_node(node, new_nodes)

delegate.register_wiki_processor(wikilinks())

