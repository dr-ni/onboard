class Error(Exception):
    """ Base class for Onboard exceptions """
    pass

class SVGSyntaxError(Error):
    """ 
    Exception thrown by Onboard when there is an error passing an SVG
    file
    """

    def __init__(self, file, message):
        self.file = file
        """
        The SVG file that was being parsed when the error occurred
        """

        self.message = message
        """
        Explanation of the error
        """
