"""
This module provides a web scraper.
"""
import re
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from time import sleep
from urllib.parse import urlsplit

from fsspec.core import url_to_fs

from sunpy import log
from sunpy.extern.parse import compile as compile_pattern
from sunpy.extern.parse import parse
from sunpy.net.scraper_utils import date_floor, extract_timestep, get_timerange_from_exdict
from sunpy.util.decorators import deprecated
from sunpy.util.exceptions import SunpyDeprecationWarning

__all__ = ['Scraper']

# So that proxies set in the environment are used.
_HTTP_OPTIONS = {'client_kwargs': {'trust_env': True}}
# Time codes finer than an hour, which give too many directory names to guess.
_FINE = re.compile('%[MSef]')

# "parse" expressions to convert into datetime format
PARSE_TIME_CONVERSIONS = {
    "{year:4d}": "%Y", "{year:2d}": "%y",
    "{month:2d}": "%m",
    "{month_name:l}": "%B",
    "{month_name_abbr:l}": "%b",
    "{day:2d}": "%d", "{day_of_year:3d}": "%j",
    "{hour:2d}": "%H",
    "{minute:2d}": "%M",
    "{second:2d}": "%S",
    "{microsecond:6d}": "%f",
    "{millisecond:3d}": "%e",
    "{week_number:2d}": "%W",
}

class Scraper:
    """
    A scraper to scrap web data archives based on dates.

    Parameters
    ----------
    format : `str`
        A string containing the url with the date and other information to be
        extracted encoded as ``parse`` formats, and any other ``kwargs`` parameters
        as a string format, the former represented using double curly-brackets
        to differentiate from the latter.
        This can also be a uri to a local file patterns.
    kwargs : `dict`
        A dictionary containing the values to be replaced in the pattern.

    Attributes
    ----------
    pattern : `str`
        The pattern with the parse format.
    datetime_pattern : `str`
        The parse pattern in the datetime format.

    Examples
    --------
    >>> from sunpy.net import Scraper
    >>>
    >>> pattern = ('https://proba2.sidc.be/{instrument}/data/bsd/{{year:4d}}/{{month:2d}}/{{day:2d}}/'
    ...            '{instrument}_lv1_{{year:4d}}{{month:2d}}{{day:2d}}_{{hour:2d}}{{minute:2d}}{{second:2d}}.fits')
    >>> swap = Scraper(format=pattern, instrument='swap')
    >>>
    >>> print(swap.pattern)
    https://proba2.sidc.be/swap/data/bsd/{year:4d}/{month:2d}/{day:2d}/swap_lv1_{year:4d}{month:2d}{day:2d}_{hour:2d}{minute:2d}{second:2d}.fits
    >>>
    >>> print(swap.datetime_pattern)
    https://proba2.sidc.be/swap/data/bsd/%Y/%m/%d/swap_lv1_%Y%m%d_%H%M%S.fits

    Notes
    -----
    Times are written in the pattern with ``{{year:4d}}``, ``{{year:2d}}``, ``{{month:2d}}``, ``{{month_name:l}}``,
    ``{{month_name_abbr:l}}``, ``{{day:2d}}``, ``{{day_of_year:3d}}``, ``{{week_number:2d}}``, ``{{hour:2d}}``,
    ``{{minute:2d}}``, ``{{second:2d}}``, ``{{millisecond:3d}}`` and ``{{microsecond:6d}}``.

    The pattern is followed one directory at a time.
    A directory named only with years, months, days or hours is requested for every time in the search range.
    Any other directory is found by listing its parent, so its name can hold anything the pattern can match,
    such as a finer time or a value that is not a time at all.
    Archives are read with `fsspec <https://filesystem-spec.readthedocs.io/en/latest/>`__, so any URL scheme it supports can be searched.
    """
    #: How many directories are listed at once, for archives served over HTTP.
    max_conn = 5

    def __init__(self, format, **kwargs):
        pattern = format.format(**kwargs)
        datetime_pattern = pattern
        for k, v in PARSE_TIME_CONVERSIONS.items():
            if k in datetime_pattern:
                datetime_pattern = datetime_pattern.replace(k,v)
        self.datetime_pattern = datetime_pattern
        # so that they don't conflict later on, either one can help in extracting year
        if "year:4d" in pattern and "year:2d" in pattern:
            pattern = pattern.replace("year:2d", ":2d")
        self.pattern = pattern

    @property
    @deprecated(since="8.1", obj_type="property")
    def domain(self):
        """
        The scheme and host of the pattern.
        """
        return f"{urlsplit(self.pattern).scheme}://{urlsplit(self.pattern).netloc}/"

    @property
    @deprecated(since="8.1", obj_type="property")
    def now(self):
        """
        The pattern filled in with the current time.
        """
        milliseconds = re.search(r'\%e', self.datetime_pattern)
        if not milliseconds:
            return datetime.now().strftime(self.datetime_pattern)
        now = datetime.now()
        milliseconds_ = int(now.microsecond / 1000.)
        return now.strftime(f'{self.datetime_pattern[0:milliseconds.start()]}{milliseconds_:03d}{self.datetime_pattern[milliseconds.end():]}')

    @deprecated(since="8.1")
    def matches(self, filepath, date):
        """
        Checks if the given filepath is how the file path is expected
        to look on given date based on the pattern.

        Parameters
        ----------
        filepath : `str`
            File path to check.
        date : `datetime.datetime` or `astropy.time.Time`
            The date for which to check.

        Returns
        -------
        `bool`
            `True` if the given filepath matches with the calculated one for given date, else `False`.
        """
        return parse(date.strftime(self.datetime_pattern), filepath) is not None

    @deprecated(since="8.1")
    def range(self, timerange):
        """
        Gets the directories for a certain range of time.

        Parameters
        ----------
        timerange : `~sunpy.time.timerange.TimeRange`
            Time interval where to find the directories for a given pattern.

        Returns
        -------
        `list` of `str`
            All the possible directories valid for the time range given.
            Notice that these directories may not exist in the archive.
        """
        # find directory structure - without file names
        directorypattern = ''
        if '/' in self.datetime_pattern:
            directorypattern = '/'.join(self.datetime_pattern.split('/')[:-1]) + '/'
        with warnings.catch_warnings():
            # The helpers used here are deprecated along with this method.
            warnings.simplefilter('ignore', SunpyDeprecationWarning)
            timestep = extract_timestep(directorypattern)
            if timestep is None:
                return [directorypattern]
            directories = []
            cur = date_floor(timerange.start, timestep)
            end = date_floor(timerange.end, timestep) + timestep
            while cur < end:
                directories.append(cur.strftime(directorypattern))
                cur = cur + timestep
            return directories

    def filelist(self, timerange):
        """
        Returns the list of existent files in the archive for the given time
        range.

        Parameters
        ----------
        timerange : `~sunpy.time.TimeRange`
            Time interval where to find the directories for a given pattern.

        Returns
        -------
        filesurls : `list` of `str`
            List of all the files found between the time range given.

        Examples
        --------
        >>> from sunpy.net import Scraper
        >>> pattern = ('https://proba2.sidc.be/{instrument}/data/bsd/{{year:4d}}/{{month:2d}}/{{day:2d}}/'
        ...            '{instrument}_lv1_{{year:4d}}{{month:2d}}{{day:2d}}_{{hour:2d}}{{minute:2d}}{{second:2d}}.fits')
        >>> swap = Scraper(pattern, instrument='swap')
        >>> from sunpy.time import TimeRange
        >>> timerange = TimeRange('2015-01-01T00:08:00','2015-01-01T00:12:00')
        >>> print(swap.filelist(timerange))  # doctest: +REMOTE_DATA
        ['https://proba2.sidc.be/swap/data/bsd/2015/01/01/swap_lv1_20150101_000857.fits',
         'https://proba2.sidc.be/swap/data/bsd/2015/01/01/swap_lv1_20150101_001027.fits',
         'https://proba2.sidc.be/swap/data/bsd/2015/01/01/swap_lv1_20150101_001157.fits']

        While writing the pattern, we can also leverage parse capabilities by using the ``{{}}`` notation to match parts of the filename that cannot be known beforehand:

        >>> from sunpy.net import Scraper
        >>> from sunpy.time import TimeRange
        >>> pattern = 'https://proba2.sidc.be/lyra/data/bsd/{{year:4d}}/{{month:2d}}/{{day:2d}}/{{}}_lev{{Level:1d}}_std.fits'
        >>> lyra = Scraper(pattern)
        >>> timerange = TimeRange('2023-03-06T00:00:00','2023-03-06T00:10:00')
        >>> print(lyra.filelist(timerange)) # doctest: +REMOTE_DATA
        ['https://proba2.sidc.be/lyra/data/bsd/2023/03/06/lyra_20230306-000000_lev2_std.fits',
        'https://proba2.sidc.be/lyra/data/bsd/2023/03/06/lyra_20230306-000000_lev3_std.fits']
        """
        return [meta['url'] for meta in self.extract_files_meta(timerange)]

    def _search(self, timerange, matcher=None):
        """
        Finds the files that match the pattern within ``timerange``.

        Parameters
        ----------
        timerange : `~sunpy.time.TimeRange`
            Time interval to search.
        matcher : `dict`, optional
            The allowed values of fields in the pattern.

        Returns
        -------
        `list` of `dict`, `list` of `Exception`
            The metadata of each file found, and the errors from directories that could not be listed.
        """
        if not urlsplit(self.pattern).scheme:
            raise ValueError("The pattern must be a URL, such as one starting with https://, ftp:// or file://.")
        segments, strfs = self.pattern.split('/'), self.datetime_pattern.split('/')
        first = next((i for i, segment in enumerate(segments) if '{' in segment), len(segments) - 1)
        base = '/'.join(segments[:first]) + '/'
        fs, _ = url_to_fs(base, **(_HTTP_OPTIONS if base.startswith('http') else {}))
        nodes, errors = [(base, {})], []
        # Only a filesystem built for it can list several directories at once.
        with ThreadPoolExecutor(self.max_conn if fs.async_impl else 1) as pool:
            for segment, strf in zip(segments[first:-1], strfs[first:-1]):
                if '{' not in segment:
                    nodes = [(url + segment + '/', fields) for url, fields in nodes]
                elif '{' in strf or _FINE.search(strf):
                    nodes = self._descend(pool, fs, nodes, segment, timerange, matcher, errors)
                else:
                    names = self._candidates(strf, timerange)
                    nodes = self._keep(nodes, [names] * len(nodes), segment, timerange, matcher)
            nodes = self._descend(pool, fs, nodes, segments[-1], timerange, matcher, errors, last=True)
        return [{**fields, 'url': url} for url, fields in nodes], errors

    def _descend(self, pool, fs, nodes, segment, timerange, matcher, errors, last=False):
        """
        Lists every directory in ``nodes`` and keeps the names that match ``segment``.
        """
        listed = list(pool.map(lambda node: self._list(fs, node[0]), nodes))
        errors += [error for _, error in listed if error is not None]
        return self._keep(nodes, [names for names, _ in listed], segment, timerange, matcher, last)

    @staticmethod
    def _keep(nodes, names, segment, timerange, matcher, last=False):
        """
        Extends each of ``nodes`` with those of its ``names`` that can still lead to a wanted file.
        """
        parser = compile_pattern(segment)
        kept = []
        for (url, seen), found in zip(nodes, names):
            for name in found:
                match = parser.parse(name)
                # A field that is repeated in the pattern has to keep its value.
                if match is None or any(seen.get(key, value) != value for key, value in match.named.items()):
                    continue
                if matcher and any(matcher.get(key) and str(value) not in matcher[key]
                                   for key, value in match.named.items()):
                    continue
                fields = {**seen, **match.named}
                start = None
                # A directory can only be ruled out by its time once the year is known.
                if last or 'year' in fields:
                    found_range = get_timerange_from_exdict(fields)
                    if not found_range.intersects(timerange):
                        continue
                    start = found_range.start.datetime
                kept.append((start, (url + name + ('' if last else '/'), fields)))
        if last:
            # Files come back in time order, and in name order within the same time.
            kept.sort(key=lambda item: item[0])
        return [node for _, node in kept]

    @staticmethod
    def _candidates(strf, timerange):
        """
        The names that ``strf`` gives over ``timerange``, in time order.
        """
        floor, step = ('%Y%m%d%H', timedelta(hours=1)) if '%H' in strf else ('%Y%m%d', timedelta(days=1))
        current, end = (datetime.strptime(time.strftime(floor), floor) for time in (timerange.start, timerange.end))
        names = {}
        while current <= end:
            names[current.strftime(strf)] = None
            current += step
        return list(names)

    @staticmethod
    def _list(fs, directory):
        """
        The names in ``directory``, and the error if it could not be listed.
        """
        path = fs._strip_protocol(directory)
        for attempt in range(6):
            try:
                entries = fs.ls(path, detail=False)
                break
            except FileNotFoundError:
                # Ignore missing directories (issue #2684).
                log.debug(f"Directory {directory} not found.")
                return [], None
            except Exception as error:
                # A busy server answers with one of these and can be asked again.
                if getattr(error, 'status', None) not in (429, 504) or attempt == 5:
                    log.debug(f"Failed to list {directory}: {error}")
                    return [], error
                try:
                    retry_after = int(error.headers['Retry-After'])
                except Exception:
                    retry_after = 2
                log.debug(f"Got {error.status} while listing {directory}, waiting {retry_after} seconds to retry.")
                sleep(retry_after)
        prefix = path.rstrip('/') + '/'
        entries = [entry.rstrip('/') for entry in entries]
        names = {entry.removeprefix(prefix).removeprefix('./') if entry.startswith(prefix) else entry.rsplit('/', 1)[-1]
                 for entry in entries}
        return sorted(name for name in names if name not in ('', '.', '..') and '/' not in name), None

    def extract_files_meta(self, timerange, matcher=None):
        """
        Returns the metadata held in the URL of each file in the archive for the given time range.

        Parameters
        ----------
        timerange : `~sunpy.time.TimeRange`
            Time interval to search.
        matcher : `dict`, optional
            The values allowed for fields in the pattern, as a list of strings for each field name.
            Defaults to `None`, which allows every value.

        Returns
        -------
        `list` of `dict`
            For each file, the value of every named field in the pattern and the file's ``url``.

        Examples
        --------
        >>> from sunpy.net import Scraper
        >>> from sunpy.time import TimeRange
        >>> pattern = 'https://proba2.sidc.be/lyra/data/bsd/{{year:4d}}/{{month:2d}}/{{day:2d}}/{{}}_lev{{Level:1d}}_std.fits'
        >>> lyra = Scraper(pattern)
        >>> timerange = TimeRange('2023-03-06T00:00:00','2023-03-06T00:10:00')
        >>> lyra.extract_files_meta(timerange, matcher={'Level': ['3']})  # doctest: +REMOTE_DATA
        [{'year': 2023, 'month': 3, 'day': 6, 'Level': 3, 'url': 'https://proba2.sidc.be/lyra/data/bsd/2023/03/06/lyra_20230306-000000_lev3_std.fits'}]
        """
        files, errors = self._search(timerange, matcher)
        if errors:
            raise errors[0]
        return files

    # The name this method had before it was public.
    _extract_files_meta = extract_files_meta
