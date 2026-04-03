from sunpy.net import attrs as a
from sunpy.net.dataretriever.attrs import hinode as hattrs
from sunpy.net.dataretriever.client import GenericClient, QueryResponse
from sunpy.net.scraper import Scraper
from sunpy.time import TimeRange

__all__ = ['HinodeSOTFGClient', 'HinodeSOTSPClient']


_ARCHIVE_URLS = (
    'https://data.darts.isas.jaxa.jp/pub/hinode/sot/',
    'https://sot.lmsal.com/data/sot/',
)
_SP_LEVEL_DIRS_MAP = {
    '0': 'level0',
    '1': 'level1hao',
    '2': 'level2hao',
    '2.1': 'level2.1hao',
}

class HinodeSOTFGClient(GenericClient):
    """
    Provides access to the Hinode Solar Optical Telescope (SOT)  Filtergraph (FG) data archive.

    Hosted by the `Data ARchives and Transmission System (DARTS) archive <https://darts.isas.jaxa.jp/en>`__.

    Examples
    --------
    >>> from sunpy.net import Fido, attrs as a
    >>> results = Fido.search(a.Time("2013-07-13 00:13:32", "2013-07-13 00:13:33"),
    ...                       a.Instrument.sot, a.Level(0), a.hinode.SOTDetector('FG'))  # doctest: +REMOTE_DATA
    >>> results  # doctest: +REMOTE_DATA
    <sunpy.net.fido_factory.UnifiedResponse object at ...>
    Results from 1 Provider:
    <BLANKLINE>
    1 Results from the HinodeSOTFGClient:
    Source: https://data.darts.isas.jaxa.jp/pub/hinode/sot/
    <BLANKLINE>
           Start Time               End Time        Instrument Source Provider Level SOTDetector
    ----------------------- ----------------------- ---------- ------ -------- ----- -----------
    2013-07-13 00:13:32.000 2013-07-13 00:13:32.999        SOT HINODE    DARTS     0          FG
    <BLANKLINE>
    <BLANKLINE>
    """
    required = {a.Time, a.Instrument, a.Level, hattrs.SOTDetector}
    pattern = (
        "https://data.darts.isas.jaxa.jp/pub/hinode/sot/level{Level}/{{year:4d}}/{{month:2d}}/{{day:2d}}/FG/"
        "H{{hour:2d}}00/"
        "FG{{year:4d}}{{month:2d}}{{day:2d}}_"
        "{{hour:2d}}{{minute:2d}}{{second:2d}}.{{}}.fits"
    )

    @classmethod
    def _attrs_module(cls):
        return 'hinode', 'sunpy.net.dataretriever.attrs.hinode'

    @classmethod
    def register_values(cls):
        from sunpy.net import attrs as a

        return {
            a.Instrument: [("SOT", "Hinode Solar Optical Telescope")],
            a.Source: [("Hinode", "Hinode / Solar-B")],
            a.Provider: [("DARTS", "ISAS/JAXA DARTS archive")],
            a.Level: [("0", "Level 0"), ("1", "Level 1")],
            a.hinode.SOTDetector: [("FG", "Filtergraph")],
        }

    @property
    def info_url(self):
        return _ARCHIVE_URLS[0]

    def post_search_hook(self, exdict, matchdict):
        rowdict = super().post_search_hook(exdict, matchdict)
        return rowdict

    def search(self, *args, **kwargs):
        matchdict = self._get_match_dict(*args, **kwargs)
        level = str(matchdict['Level'][0])
        if level not in ['0', '1']:
            return QueryResponse([], client=self)
        formatted_pattern = self.pattern.replace('{Level}', level)
        patterns = [formatted_pattern, formatted_pattern.replace(_ARCHIVE_URLS[0], _ARCHIVE_URLS[1])]
        tr = TimeRange(matchdict['Start Time'], matchdict['End Time'])
        rows = []
        seen_urls = set()
        for pat in patterns:
            scraper = Scraper(format=pat)
            try:
                filemeta = scraper._extract_files_meta(tr, matcher=matchdict)
            except Exception:
                filemeta = []
            for i in filemeta:
                url = i.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    rows.append(self.post_search_hook(i, matchdict))
            if filemeta:
                break
        rows.sort(key=lambda x: x['Start Time'])
        return QueryResponse(rows, client=self)


class HinodeSOTSPClient(GenericClient):
    """
    Provides access to the Hinode Solar Optical Telescope (SOT)  Spectral-polarimeter (SP) data archive.

    Hosted by the `Data ARchives and Transmission System (DARTS) archive <https://darts.isas.jaxa.jp/en>`__.

    Examples
    --------
    >>> from sunpy.net import Fido, attrs as a
    >>> results = Fido.search(a.Time("2013-07-13 10:02:00", "2013-07-13 10:03:00"),
    ...                       a.Instrument.sot, a.Level(0), a.hinode.SOTDetector('SP'))  # doctest: +REMOTE_DATA
    >>> results  # doctest: +REMOTE_DATA
    <sunpy.net.fido_factory.UnifiedResponse object at ...>
    Results from 1 Provider:
    <BLANKLINE>
    3 Results from the HinodeSOTSPClient:
    Source: https://data.darts.isas.jaxa.jp/pub/hinode/sot/
    <BLANKLINE>
           Start Time               End Time        Instrument Source Provider Level SOTDetector
    ----------------------- ----------------------- ---------- ------ -------- ----- -----------
    2013-07-13 10:02:50.000 2013-07-13 10:02:50.000        SOT Hinode    DARTS     0          SP
    2013-07-13 10:02:54.000 2013-07-13 10:02:54.000        SOT Hinode    DARTS     0          SP
    2013-07-13 10:02:58.000 2013-07-13 10:02:58.000        SOT Hinode    DARTS     0          SP
    <BLANKLINE>
    <BLANKLINE>
    """
    required = {a.Time, a.Instrument, a.Level, hattrs.SOTDetector}

    # Pattern for level 0 data
    pattern_level0 = (
        "https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/{{year:4d}}/{{month:2d}}/{{day:2d}}/SP4D/H{{hour:2d}}00/"
        "SP4D{{year:4d}}{{month:2d}}{{day:2d}}_{{hour:2d}}{{minute:2d}}{{second:2d}}.{{}}.fits"
    )
    # Pattern for level 1, 2, 2.1 data
    pattern_other = (
        "https://data.darts.isas.jaxa.jp/pub/hinode/sot/{{level_dir}}/{{year:4d}}/{{month:2d}}/{{day:2d}}/SP3D/"
        "{{year:4d}}{{month:2d}}{{day:2d}}_{{hour:2d}}{{minute:2d}}{{second:2d}}/"
        "SP3D{{year:4d}}{{month:2d}}{{day:2d}}_{{hour:2d}}{{minute:2d}}{{second:2d}}_{{}}.fits"
    )

    @classmethod
    def _attrs_module(cls):
        return 'hinode', 'sunpy.net.dataretriever.attrs.hinode'

    @classmethod
    def register_values(cls):
        from sunpy.net import attrs as a

        return {
            a.Instrument: [("SOT", "Hinode Solar Optical Telescope")],
            a.Source: [("Hinode", "Hinode / Solar-B")],
            a.Provider: [("DARTS", "ISAS/JAXA DARTS archive")],
            a.Level: [("0", "Level 0"), ("1", "Level 1"), ("2", "Level 2"), ("2.1", "Level 2.1")],
            a.hinode.SOTDetector: [("SP", "Spectro-Polarimeter")],
        }

    @property
    def info_url(self):
        return _ARCHIVE_URLS[0]

    def post_search_hook(self, exdict, matchdict):
        rowdict = super().post_search_hook(exdict, matchdict)
        rowdict['End Time'] = rowdict['Start Time']
        rowdict['Source'] = 'Hinode'
        rowdict['Provider'] = 'DARTS'
        return rowdict

    def search(self, *args, **kwargs):
        matchdict = self._get_match_dict(*args, **kwargs)
        level = str(matchdict['Level'][0])
        level_dir = _SP_LEVEL_DIRS_MAP[level]
        if level == '0':
            patterns = [self.pattern_level0, self.pattern_level0.replace(_ARCHIVE_URLS[0], _ARCHIVE_URLS[1])]
        else:
            patterns = [self.pattern_other, self.pattern_other.replace(_ARCHIVE_URLS[0], _ARCHIVE_URLS[1])]
        tr = TimeRange(matchdict['Start Time'], matchdict['End Time'])
        rows = []
        seen_urls = set()
        for pat in patterns:
            scraper = Scraper(format=pat, level_dir=level_dir)
            try:
                filemeta = scraper._extract_files_meta(tr, matcher=matchdict)
            except Exception:
                filemeta = []
            for i in filemeta:
                url = i.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    rows.append(self.post_search_hook(i, matchdict))
            if filemeta:
                break
        rows.sort(key=lambda x: x['Start Time'])
        return QueryResponse(rows, client=self)
