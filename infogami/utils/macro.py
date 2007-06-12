"""
Macro extension to markdown.

Macros take argument string as input and returns result as markdown text.
"""
import markdown
import web
from storage import DefaultDict

# 2D dict
# site_id -> name -> macro
_macros = DefaultDict({})

def _get_macro(name):
    from context import context
    site = context.get("site")
    return _macros[site and site.id].get(name, _macros[None].get(name))

def macro(f):
    """Decorator to register a markdown macro.
    Macro is a function that takes argument string and returns result as markdown string.
    """
    register_macro(None, f.__name__, f)
    return f
    
def register_macro(site, name, f):
    _macros[site and site.id][name] = f
    
def unregister_macro(site, name):
    if name in _macros[site and site.id]:
        del _macros[site and site.id][name]

def safeeval_args(args):
    """Evalues the args string safely using templator."""
    result = [None]
    def f(*args, **kwargs):
        result[0] = args, kwargs
    web.template.Template("$def with (f)\n$f(%s)" % args)(f)
    return result[0]
    
def call_macro(name, args):
    macro = _get_macro(name)
    if macro:
        try:
            args, kwargs = safeeval_args(args)
            result = macro(*args, **kwargs)
        except Exception, e:
            result = "%s failed with error: <pre>%s</pre>" % (name, web.websafe(str(e)))
        return result
    else:
        return "Unknown macro: <pre>%s</pre>" % name

class MacroPattern(markdown.BasePattern):
    """Inline pattern to replace macros."""
    def __init__(self, stash):
        pattern = r'{{(.*)\((.*)\)}}'
        markdown.BasePattern.__init__(self, pattern)
        self.stash = stash

    def handleMatch(self, m, doc):
        name, args = m.group(2), m.group(3)
        html = call_macro(name, args)

        # markdown uses place-holders to replace html blocks. 
        # markdown.HtmlStash stores the html blocks to be replaced
        placeholder = self.stash.store(html)
        return doc.createTextNode(placeholder)

class MacroExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        md.inlinePatterns.append(MacroPattern(md.htmlStash))

def makeExtension(configs={}): 
    return MacroExtension(configs=configs)

@macro
def HelloWorld():
    """Hello world macro."""
    return "<b>Hello, world</b>."

@macro
def ListOfMacros():
    """Lists all available macros."""
    from context import context 
    site = context.site
    a = _macros[None].keys()
    b = _macros[site and site.id].keys()
    
    out = ""
    out += "<ul>"
    for name in sorted(set(a+b)):
        macro = _get_macro(name)
        out += '  <li><b>%s</b>: %s</li>\n' % (name, macro.__doc__ or "")
    out += "</ul>"
    return out
    
if __name__ == "__main__":
    def get_markdown(text):
        md = markdown.Markdown(source=text, safe_mode=False)
        md = macromarkdown(md)
        return md
    
    print get_markdown("This is HelloWorld Macro. {{HelloWorld()}}\n\n" + 
            "And this is the list of available macros. {{ListOfMacros()}}")