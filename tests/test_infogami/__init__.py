import os

import web

import infogami
from infogami.infobase import server
from infogami.utils.delegate import app

# overwrite _cleanup to stop clearing thread state between requests
app._cleanup = lambda *a: None

db_parameters = dict(dbn="postgres", db="infogami_test", user=os.environ["USER"], pw="")


def setup_module(module):
    monkey_patch_browser()

    infogami.config.site = "infogami.org"
    infogami.config.db_parameters = web.config.db_parameters = db_parameters

    server.get_site("infogami.org")  # to initialize db

    module.db = server._infobase.store.db
    module.db.printing = False
    module.t = module.db.transaction()

    infogami._setup()


def teardown_module(module):
    module.t.rollback()


def monkey_patch_browser():
    def check_errors(self):
        errors = [
            self.get_text(e)
            for e in self.get_soup().findAll(attrs={'id': 'error'})
            + self.get_soup().findAll(attrs={'class': 'wrong'})
        ]
        if errors:
            raise web.BrowserError(errors[0])

    _do_request = web.AppBrowser.do_request

    def do_request(self, req):
        response = _do_request(self, req)
        if self.status != 200:
            raise web.BrowserError(str(self.status))
        self.check_errors()
        return response

    web.AppBrowser.do_request = do_request
    web.AppBrowser.check_errors = check_errors
