from tdb import SimpleTDBImpl, CachedTDBImpl
from tdb import NotFound, hook, Thing

impl = CachedTDBImpl()

root = impl.root
setup = impl.setup
withID = impl.withID
withName = impl.withName
withIDs = impl.withIDs
withNames = impl.withNames
new = impl.new
Things = impl.Things
Versions = impl.Versions
stats = impl.stats
transact = impl.transact
rollback = impl.rollback
commit = impl.commit
