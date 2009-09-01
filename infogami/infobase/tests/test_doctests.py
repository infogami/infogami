import doctest

def test_doctest():
    yield _test_doctest, "infogami.infobase.account"
    yield _test_doctest, "infogami.infobase.bootstrap"
    yield _test_doctest, "infogami.infobase.cache"
    yield _test_doctest, "infogami.infobase.client"
    yield _test_doctest, "infogami.infobase.common"
    yield _test_doctest, "infogami.infobase.core"
    yield _test_doctest, "infogami.infobase.dbstore"
    yield _test_doctest, "infogami.infobase.infobase"
    yield _test_doctest, "infogami.infobase.logger"
    yield _test_doctest, "infogami.infobase.logreader"
    yield _test_doctest, "infogami.infobase.lru"
    yield _test_doctest, "infogami.infobase.readquery"
    yield _test_doctest, "infogami.infobase.utils"
    yield _test_doctest, "infogami.infobase.writequery"

def _test_doctest(modname):
    mod = __import__(modname, None, None, ['x'])
    doctest.testmod(mod)