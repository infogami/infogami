class Site:
    """
    The basic data model of the software. A Site represents one wiki at a specific URL
    with a set of templates and users and pages and so on.
    """

    def get(self, name):
        """
        Gets the latest version of the page named `name`. Returns a `web.storage` object 
        with a bundle of attributes.
        """
        pass
    
    def put(self, name, page):
        """
        Saves a new version of a page.
        """
        pass
    
    def history(self, name):
        """
        Gets the history of a page. Returns a list of `web.storage` objects in 
        chronological order.
        """
        pass
