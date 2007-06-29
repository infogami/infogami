from tdb import SimpleTDBImpl, NotFound, hook

impl = SimpleTDBImpl()

root = impl.root
setup = impl.setup
withID = impl.withID
withName = impl.withName
withIDs = impl.withIDs
withNames = impl.withNames
new = impl.new
Things = impl.Things
Versions = impl.Versions