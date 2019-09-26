from test import webtest

def suite():
    modules = ["test_doctests", "test_dbstore", "test_infobase"]
    return webtest.suite(modules)

if __name__ == "__main__":
    webtest.main()

