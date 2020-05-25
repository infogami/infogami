"""
Macro extension to markdown.

Macros take argument string as input and returns result as markdown text.
"""
from __future__ import print_function

import os

import web

from infogami.utils import storage, template
from infogami.utils.markdown import markdown


# macros loaded from disk
diskmacros = template.DiskTemplateSource()
# macros specified in the code
codemacros = web.storage()

macrostore = storage.DictPile()
macrostore.add_dict(diskmacros)
macrostore.add_dict(codemacros)

def macro(f):
    """Decorator to register a markdown macro.
    Macro is a function that takes argument string and returns result as markdown string.
    """
    codemacros[f.__name__] = f
    return f

def load_macros(plugin_root, lazy=False):
    """Adds $plugin_root/macros to macro search path."""
    path = os.path.join(plugin_root, 'macros')
    if os.path.isdir(path):
        diskmacros.load_templates(path, lazy=lazy)

#-- macro execution

def safeeval_args(args):
    """Evalues the args string safely using templator."""
    result = [None]
    def f(*args, **kwargs):
        result[0] = args, kwargs
    code = "$def with (f)\n$f(%s)" % args
    web.template.Template(web.safestr(code))(f)
    return result[0]

def call_macro(name, args):
    if name in macrostore:
        try:
            macro = macrostore[name]
            args, kwargs = safeeval_args(args)
            result = macro(*args, **kwargs)
        except Exception as e:
            i = web.input(_method="GET", debug="false")
            if i.debug.lower() == "true":
                raise
            result = "%s failed with error: <pre>%s</pre>" % (name, web.websafe(str(e)))
            import traceback
            traceback.print_exc()
        return str(result).decode('utf-8')
    else:
        return "Unknown macro: <pre>%s</pre>" % name

MACRO_PLACEHOLDER = "asdfghjjkl%sqwertyuiop"

class MacroPattern(markdown.BasePattern):
    """Inline pattern to replace macros."""
    def __init__(self, md):
        pattern = r'{{([a-zA-Z0-9_]*)\((.*)\)}}'
        markdown.BasePattern.__init__(self, pattern)
        self.markdown = md

    def handleMatch(self, m, doc):
        name, args = m.group(2), m.group(3)

        # markdown uses place-holders to replace html blocks.
        # markdown.HtmlStash stores the html blocks to be replaced
        placeholder = self.store(self.markdown, (name, args))
        return doc.createTextNode(placeholder)

    def store(self, md, macro_info):
        placeholder = MACRO_PLACEHOLDER % md.macro_count
        md.macro_count += 1
        md.macros[placeholder] = macro_info
        return placeholder

def replace_macros(html, macros):
    """Replaces the macro place holders with real macro output."""
    for placeholder, macro_info in list(macros.items()):
        name, args = macro_info
        html = html.replace("<p>%s\n</p>" % placeholder, web.safestr(call_macro(name, args)))

    return html

class MacroExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        md.inlinePatterns.append(MacroPattern(md))
        md.macro_count = 0
        md.macros = {}

def makeExtension(configs={}):
    return MacroExtension(configs=configs)

#-- sample macros

@macro
def HelloWorld():
    """Hello world macro."""
    return "<b>Hello, world</b>."

@macro
def ListOfMacros():
    """Lists all available macros."""
    out = ""
    out += "<ul>"
    for name, macro in list(macrostore.items()):
        out += '  <li><b>%s</b>: %s</li>\n' % (name, macro.__doc__ or "")
    out += "</ul>"
    return out

if __name__ == "__main__":
    text = "{{HelloWorld()}}"
    md = markdown.Markdown(source=text, safe_mode=False)
    MacroExtension().extendMarkdown(md, {})
    html = md.convert()
    print(replace_macros(html, md.macros))
