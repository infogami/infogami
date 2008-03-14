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

## incase you want to generate tdb log
#import infogami.tdb.tdb
#infogami.tdb.logger.set_logfile(open("tdb.log", "a"))

@infogami.install_hook
@infogami.action
def createsite():
    from infogami.infobase import Infobase
    web.load()
    Infobase().create_site(infobase.config.site, infobase.config.admin_password)

if __name__ == "__main__":
    infogami.run()
