#! /usr/bin/env python
"""Script to run infobase.

USAGE:

* Run Infobase http server at port 7070.

    $ python run_infobase.py -f infobase.yaml -p 7070

* Run Infobase as fastcgi server at port 7070

    $ python run_infobase.py --fastcgi -f infobase.yaml -p 7070
"""
import sys

from optparse import OptionParser
import yaml
import web

import infogami
from infogami.infobase import cache, config, lru, server

def parse_args():
    parser = OptionParser(usage="%(prog)s -f config_file [-p port] [--fastcgi]", version=infogami.__version__)

    parser.add_option("-f", dest="config_file", help="config file")
    parser.add_option("-p", "--port", dest="port", default=5964, type="int", help="port (default: %default)")
    parser.add_option("--fastcgi", dest="fastcgi", action="store_true", default=False, help="run as fastcgi")

    (options, args) = parser.parse_args()

    if options.config_file == None:
        print parser.error("Missing config file")
    return options.__dict__

def setup_infobase():
    plugins = []
    # setup python path and load plugins
    sys.path += config.get('python_path', [])
    for p in config.get('plugins') or []:
        plugins.append(__import__(p, None, None, ["x"]))
        print >> web.debug, "loaded plugin", p

    if config.get('cache_size'):
        cache.global_cache = lru.LRU(config.cache_size)

    d = config.db_parameters
    web.config.db_parameters = dict(
        dbn=d.get('engine', 'postgres'),
        host=d.get('host', 'localhost'),
        db=d['database'],
        user=d['username'],
        pw=d.get('password') or ''
    )

    sys.argv = [sys.argv[0]]
    if config.fastcgi:
        sys.argv.append('fastcgi')

    #TODO: take care of binding_address
    port = config.get('port') or 8080
    sys.argv.append(str(port))

    for p in plugins:
        m = getattr(p, 'init_plugin', None)
        m and m()

def main():
    options = parse_args()
    runtime_config = yaml.load(open(options['config_file']))
    for k, v in runtime_config.items():
        setattr(config, k, v)

    for k, v in options.items():
        setattr(config, k, v)

    setup_infobase()

    from infogami.infobase import server
    server.run()

if __name__ == "__main__":
    main()


