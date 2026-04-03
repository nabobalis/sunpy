from sunpy.net.attr import SimpleAttr


class Channel(SimpleAttr):
    """
    Hinode SOT-FG filter / channel name, e.g. 'Ca II H', 'G band', 'Fe I 630.2'.
    """


class Mode(SimpleAttr):
    """
    Hinode observing mode string.

    For FG this is matched against catalog metadata (OBS_TYPE / GEN_ID-like fields).
    For SP this is currently informational; the simple archive-backed client below
    does not yet parse mode metadata from the remote archive.
    """
