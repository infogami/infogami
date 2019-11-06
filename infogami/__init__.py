"""Infogami: Structured Wiki (http://infogami.org)"""
from __future__ import print_function

__version__ = "0.5dev"

import web
import sys
from infogami import config


usage = """
Infogami

list of commands:

run             start the webserver
dbupgrade       upgrade the database
help            show this
"""

_actions = []
def action(f):
    """Decorator to register an infogami action."""
    _actions.append(f)
    return f

_install_hooks = []
def install_hook(f):
    """Decorator to register install hook."""
    _install_hooks.append(f)
    return f

def find_action(name):
    for a in _actions:
        if a.__name__ == name:
            return a

def _setup():
    #if config.db_parameters is None:
    #    raise Exception('infogami.config.db_parameters is not specified')

    if config.site is None:
        raise Exception('infogami.config.site is not specified')

    if config.bugfixer:
        web.webapi.internalerror = web.emailerrors(config.bugfixer, web.debugerror)
        web.internalerror = web.webapi.internalerror
    web.config.db_parameters = config.db_parameters
    web.config.db_printing = config.db_printing

    if config.get("debug", None) is not None:
        web.config.debug = config.debug

    from infogami.utils import delegate
    delegate._load()

    # setup context etc.
    delegate.fakeload()

@action
def startserver(*args):
    """Start webserver."""
    from infogami.utils import delegate
    sys.argv = [sys.argv[0]] + list(args)
    web.ctx.clear()
    delegate.app.run(*config.middleware)

@action
def help(name=None):
    """Show this help."""

    a = name and find_action(name)

    print("Infogami Help")
    print("")

    if a:
        print("    %s\t%s" %  (a.__name__, a.__doc__))
    else:
        print("Available actions")
        for a in _actions:
            print("    %s\t%s" %  (a.__name__, a.__doc__))

@action
def install():
    """Setup everything."""

    # set debug=False to avoid reload magic.
    web.config.debug = False

    from infogami.utils import delegate
    delegate.fakeload()
    if not web.ctx.site.exists():
        web.ctx.site.create()

    delegate.admin_login()
    for a in _install_hooks:
        print(a.__name__, file=web.debug)
        a()

@action
def shell(*args):
    """Interactive Shell"""
    if not "--ipython" in args:
        from code import InteractiveConsole
        console = InteractiveConsole()
        console.push("import infogami")
        console.push("from infogami.utils import delegate")
        console.push("from infogami.core import db")
        console.push("from infogami.utils.context import context as ctx")
        console.push("delegate.fakeload()")
        console.interact()
    else:
        """IPython Interactive Shell - IPython must be installed to use."""
        # remove an argument that confuses ipython
        sys.argv.pop(sys.argv.index("--ipython"))
        from IPython.Shell import IPShellEmbed
        import infogami
        from infogami.utils import delegate
        from infogami.core import db
        from infogami.utils.context import context as ctx
        delegate.fakeload()
        ipshell = IPShellEmbed()
        ipshell()

@action
def runscript(filename, *args):
    """Executes given script after setting up the plugins.
    """
    sys.argv = [filename] + list(args)
    g = {"__name__": "__main__"}
    with open(filename) as in_file:
        exec(in_file.read(), g, g)

def run_action(name, args=[]):
    a = find_action(name)
    if a:
        a(*args)
    else:
        print('unknown command', name, file=sys.stderr)
        help()

def run(args=None):
    if args is None:
        args = sys.argv[1:]

    _setup()
    if len(args) == 0:
        run_action("startserver")
    else:
        run_action(args[0], args[1:])

def load_config(config_file):
    import yaml
    from infogami.infobase import config as infobase_config
    from infogami.infobase import server as infobase_server
    from infogami.infobase import lru

    def storify(d):
        if isinstance(d, dict):
            return web.storage((k, storify(v)) for k, v in d.items())
        elif isinstance(d, list):
            return [storify(x) for x in d]
        else:
            return d

    # load config
    runtime_config = yaml.load(open(config_file))

    # update config
    for k, v in runtime_config.items():
        setattr(config, k, storify(v))

    for k, v in runtime_config.get('infobase', {}).items():
        setattr(infobase_config, k, storify(v))

    # setup python path
    sys.path += config.get('python_path', [])

    config.db_parameters = infobase_server.parse_db_parameters(config.db_parameters)
    web.config.db_parameters = config.db_parameters

    # setup infobase
    if config.get('cache_size'):
        from infogami.infobase import cache
        cache.global_cache = lru.LRU(config.cache_size)

    if config.get('secret_key'):
        infobase_config.secret_key = config.secret_key

    # setup smtp_server
    if config.get('smtp_server'):
        web.config.smtp_server = config.smtp_server

def main(config_file, *args):
    """Start Infogami using config file."""
    load_config(config_file)
    run(args)
