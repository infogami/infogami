"""
Sample run.py
"""
import infogami

## your db parameters
infogami.config.db_parameters = dict(dbn='postgres', db="infogami", user='yourname', pw='')

## site name 
infogami.config.site = 'infogami.org'
infogami.config.admin_password = "admin123"

## add additional plugins and plugin path
#infogami.config.plugin_path += ['plugins']
#infogami.config.plugins += ['search']

def createsite():
    import web
    from infogami.infobase.infobase import Infobase
    web.config.db_parameters = infogami.config.db_parameters
    web.config.db_printing = True
    web.load()
    Infobase().create_site(infogami.config.site, infogami.config.admin_password)

if __name__ == "__main__":
    import sys

    if '--schema' in sys.argv:
        from infogami.infobase.dbstore import Schema
        print Schema().sql()
    elif '--createsite' in sys.argv:
        createsite()
    else:
        infogami.run()

