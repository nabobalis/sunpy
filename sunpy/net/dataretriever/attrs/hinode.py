from sunpy.net.attr import SimpleAttr


class SOTDetector(SimpleAttr):
    """
    High-level SOT subsystem, e.g. 'FG' or 'SP'.
    """


class Channel(SimpleAttr):
    """
    Filter / wavelength-like label for FG rows, e.g. 'Ca II H', 'G band'.
    """


class Mode(SimpleAttr):
    """
    Free-text observing mode matched against catalog metadata such as OBS_TYPE.
    """
