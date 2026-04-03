from sunpy.net import Fido, attrs as a
from sunpy.net.dataretriever.attrs.hinode import Channel

fg = Fido.search(
    a.Time("2011-02-15T00:00:00", "2011-02-15T12:00:00"),
    a.Instrument("SOT-FG"),
    a.Level(1),
    Channel("Ca II H"),
)

files_fg = Fido.fetch(
    fg,
    path="data/hinode/{instrument}/{start_time:%Y%m%d}/{file}",
)
