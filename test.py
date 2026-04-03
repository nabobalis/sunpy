from sunpy.net import Fido, attrs as a
from sunpy.net.dataretriever.attrs.hinode import SOTDetector, Channel

res = Fido.search(
    a.Time("2011-12-14 00:00", "2011-12-14 06:00"),
    a.Instrument("SOT"),
    SOTDetector("FG"),
    Channel("Ca II H"),
    a.Level(1),
)
print(res)

res2 = Fido.search(
    a.Time("2011-12-14 00:00", "2011-12-14 06:00"),
    a.Instrument("SOT"),
    SOTDetector("SP"),
    a.Level("2.1"),
)
print(res2)
