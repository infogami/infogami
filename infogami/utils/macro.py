"""
Macro extension to markdown.

Macros take argument string as input and returns result as markdown text.
"""
from markdown import markdown
import web
from storage import SiteLocalDict

_macros = SiteLocalDict()

def _get_macro(name):
    from context import context
    site = context.get("site")
    return _macros[site and site.id].get(name, _macros[None].get(name))

def macro(f):
    """Decorator to register a markdown macro.
    Macro is a function that takes argument string and returns result as markdown string.
    """
    register_macro(f.__name__, f)
    return f
    
def register_macro(name, f):
    _macros[name] = f
    
def unregister_macro(name):
    if name in _macros:
        del _macros[name]

def safeeval_args(args):
    """Evalues the args string safely using templator."""
    result = [None]
    def f(*args, **kwargs):
        result[0] = args, kwargs
    web.template.Template("$def with (f)\n$f(%s)" % args)(f)
    return result[0]
    
def call_macro(name, args):
    if name in _macros:
        try:
            macro = _macros[name]
            args, kwargs = safeeval_args(args)
            result = macro(*args, **kwargs)
        except Exception, e:
            result = "%s failed with error: <pre>%s</pre>" % (name, web.websafe(str(e)))
        return str(result).decode('utf-8')
    else:
        return "Unknown macro: <pre>%s</pre>" % name

MACRO_PLACEHOLDER = "asdfghjjkl%sqwertyuiop"

class MacroPattern(markdown.BasePattern):
    """Inline pattern to replace macros."""
    def __init__(self, md):
        pattern = r'{{(.*)\((.*)\)}}'
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
    for placeholder, macro_info in macros.items():
        name, args = macro_info
        html = html.replace(placeholder, call_macro(name, args))
        
    return html

class MacroExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        md.inlinePatterns.append(MacroPattern(md))
        md.macro_count = 0
        md.macros = {}

def makeExtension(configs={}): 
    return MacroExtension(configs=configs)

@macro
def HelloWorld():
    """Hello world macro."""
    return "<b>Hello, world</b>."

@macro
def ListOfMacros():
    """Lists all available macros."""
    out = ""
    out += "<ul>"
    for name, macro in _macros.items():
        out += '  <li><b>%s</b>: %s</li>\n' % (name, macro.__doc__ or "")
    out += "</ul>"
    return out
    
if __name__ == "__main__":
    def get_markdown(text):
        md = markdown.Markdown(source=text, safe_mode=False)
        makeExtension().extendMarkdown(md, markdown.__dict__)
        return md
    
    print get_markdown("This is HelloWorld Macro. {{HelloWorld()}}\n\n" + 
            "And this is the list of available macros. {{ListOfMacros()}}")
