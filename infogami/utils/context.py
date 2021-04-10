"""
Threaded context for infogami.
"""
import web

# Placeholder for keeping context defaults. This is populated by
# the app on startup.
defaults = web.storage()


class InfogamiContext(web.ThreadedDict):
    """
    Threaded context for infogami.
    Uses web.ctx for providing a thread-specific context for infogami.
    """

    def load(self):
        self.update(defaults)

    def __getattr__(self, name):
        # In some error conditions, context is not initialzied.
        # Using the default as fallback.
        try:
            return web.ThreadedDict.__getattr__(self, name)
        except AttributeError:
            return getattr(defaults, name)


context = InfogamiContext()
