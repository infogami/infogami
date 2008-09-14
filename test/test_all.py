import webtest

def suite():
    modules = ["test_doctests"]
    return webtest.suite(modules)

if __name__ == "__main__":
    webtest.main()

