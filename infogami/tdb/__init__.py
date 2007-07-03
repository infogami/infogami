from tdb import SimpleTDBImpl, BetterTDBImpl, CachedTDBImpl 
from tdb import NotFound, hook, Thing

impl = SimpleTDBImpl()
#impl = BetterTDBImpl()
#impl = CachedTDBImpl(impl)

root = impl.root
setup = impl.setup
withID = impl.withID
withName = impl.withName
withIDs = impl.withIDs
withNames = impl.withNames
new = impl.new
Things = impl.Things
Versions = impl.Versions
