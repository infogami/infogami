import webtest

def suite():
    bugs = [239238]

    modules = ["test_infobase"] + ["bug_%d" % bug for bug in bugs]
    return webtest.suite(modules)

if __name__ == "__main__":
    webtest.main()

