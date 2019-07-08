import datetime
from infogami.infobase import logreader

def test_nextday():
    assert logreader.nextday(datetime.date(2010, 10, 20)) == datetime.date(2010, 10, 21)
    assert logreader.nextday(datetime.date(2010, 10, 31)) == datetime.date(2010, 11, 1)    

def test_daterange():
    def f(begin, end):
        return list(logreader.daterange(begin, end))

    oct10 = datetime.date(2010, 10, 10)
    oct11 = datetime.date(2010, 10, 11)
    assert f(oct10, oct10) == [oct10]
    assert f(oct10, oct11) == [oct10, oct11]
    assert f(oct11, oct10) == []

def test_to_timestamp():
    assert logreader.to_timestamp('2010-01-02T03:04:05.678900') == datetime.datetime(2010, 1, 2, 3, 4, 5, 678900)

class TestLogFile:
    def test_file2date(self):
        logfile = logreader.LogFile("foo")
        assert logfile.file2date("foo/2010/10/20.log") == datetime.date(2010, 10, 20)


    def test_date2file(self):
        logfile = logreader.LogFile("foo")
        assert logfile.date2file(datetime.date(2010, 10, 20)) == "foo/2010/10/20.log"

    def test_tell(self, tmpdir):
        root = tmpdir.mkdir("log")
        logfile = logreader.LogFile(root.strpath)

        # when there are no files, it must tell the epoch time
        assert logfile.tell() == datetime.date.fromtimestamp(0).isoformat() + ":0"

    def test_find_filelist(self, tmpdir):
        root = tmpdir.mkdir("log")
        logfile = logreader.LogFile(root.strpath)

        # when there are no files, it should return empty list.
        assert logfile.find_filelist() == []
        assert logfile.find_filelist(from_date=datetime.date(2010, 10, 10)) == []

        # create empty log file and check if it returns them
        d = root.mkdir("2010").mkdir("10")
        f1 = d.join("01.log")
        f1.write("")
        f2 = d.join("02.log")
        f2.write("")
        assert logfile.find_filelist() == [f1.strpath, f2.strpath]
        assert logfile.find_filelist(from_date=datetime.date(2010, 10, 2)) == [f2.strpath]

        # create a bad file and make it behaves correctly
        d.join("foo.log").write("")
        assert logfile.find_filelist() == [f1.strpath, f2.strpath]

    def test_readline(self, tmpdir):
        root = tmpdir.mkdir("log")
        logfile = logreader.LogFile(root.strpath)
        assert logfile.readline() == ''

        root.mkdir("2010").mkdir("10")
        f = root.join("2010/10/01.log")
        f.write("helloworld\n")
        assert logfile.readline() == 'helloworld\n'

        f.write("hello 1\n", mode='a')
        f.write("hello 2\n", mode='a')
        assert logfile.readline() == 'hello 1\n'
        assert logfile.readline() == 'hello 2\n'
        assert logfile.readline() == ''

    def test_seek(self, tmpdir):
        root = tmpdir.mkdir("log")
        logfile = logreader.LogFile(root.strpath)

        # seek should not have any effect when there are no log files.
        pos = logfile.tell()
        logfile.seek("2010-10-10:0")
        pos2 = logfile.tell()
        assert pos == pos2

        # when the requested file is not found, offset should go to the next available file.
        root.mkdir("2010").mkdir("10")
        f = root.join("2010/10/20.log")
        f.write("")

        logfile.seek("2010-10-10:0")
        assert logfile.tell() == "2010-10-20:0"

