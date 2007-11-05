import unittest
import testutil

class InstallTest(unittest.TestCase):
    def testInstall(self):
        testutil.createdb()
        testutil.run_action('install')

    def testPushPull(self):
        testutil.createdb()
        pages_dir = testutil.tempdir()
        paths = ['', 'type/*', 'templates/*']
        paths_file = testutil.write_tempfile("".join(paths))
        testutil.run_action('install')
        testutil.run_action('pull', [pages_dir, paths_file])
        
