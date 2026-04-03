from __future__ import annotations

import os
import re
import tempfile
from datetime import timedelta
from functools import partial
from pathlib import Path
from urllib.parse import urljoin

import requests
from astropy.time import Time
from scipy.io import readsav

from sunpy.net import attr, attrs as a
from sunpy.net.attr import AttrAnd, AttrOr, AttrWalker, DataAttr
from sunpy.net.base_client import BaseClient, QueryResponseTable, convert_row_to_table
from sunpy.util.net import parse_header

import sunpy.net.dataretriever.attrs.hinode as hattrs


__all__ = ["HinodeSOTClient"]



walker = AttrWalker()

@walker.add_creator(AttrOr)
def _create_or(wlk, tree):
    queries = []
    for sub in tree.attrs:
        queries.extend(wlk.create(sub))
    return queries

@walker.add_creator(AttrAnd, DataAttr)
def _create_and(wlk, tree):
    params = {}
    wlk.apply(tree, params)
    return [params]

@walker.add_applier(AttrAnd)
def _apply_and(wlk, tree, params):
    for sub in tree.attrs:
        wlk.apply(sub, params)

@walker.add_applier(a.Time)
def _apply_time(wlk, query, params):
    params["start"] = query.start.to_datetime()
    params["end"] = query.end.to_datetime()

@walker.add_applier(a.Level)
def _apply_level(wlk, query, params):
    params["level"] = str(query.value)

@walker.add_applier(a.Instrument)
def _apply_instrument(wlk, query, params):
    params["instrument"] = str(query.value)

@walker.add_applier(hattrs.SOTDetector)
def _apply_detector(wlk, query, params):
    params["detector"] = str(query.value).upper()

@walker.add_applier(hattrs.Channel)
def _apply_channel(wlk, query, params):
    params["channel"] = str(query.value)

@walker.add_applier(hattrs.Mode)
def _apply_mode(wlk, query, params):
    params["mode"] = str(query.value)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def _as_str(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore")
    return str(value)


def _record_get(record, *names, default=None):
    found = {}

    dtype = getattr(record, "dtype", None)
    names_in_dtype = getattr(dtype, "names", None)
    if names_in_dtype:
        for name in names_in_dtype:
            found[name.lower()] = record[name]

    if hasattr(record, "keys"):
        for key in record.keys():
            found[str(key).lower()] = record[key]

    for name in names:
        if name.lower() in found:
            return found[name.lower()]

    return default


def _daterange(start, end):
    day = start.date()
    while day <= end.date():
        yield day
        day += timedelta(days=1)


def _match_text(needle, haystack):
    if not needle:
        return True
    if not haystack:
        return False
    return needle.lower() in haystack.lower()


class HinodeSOTClient(BaseClient):
    """
    Shared SOT catalog-backed Fido client.

    Search:
      - reads daily SOT catalog files under sot_genxcat or sot_genxcat_sirius
      - filters rows to FG or SP if requested

    Fetch:
      - FG rows resolve to SOT level0/level1 archive files
      - SP rows resolve to SP archive scan directories / files
    """

    CATALOG_ROOTS = {
        "quicklook": "https://soho.nascom.nasa.gov/sdb/hinode/sot/sot_genxcat/",
        "sirius": "https://soho.nascom.nasa.gov/sdb/hinode/sot/sot_genxcat_sirius/",
        # easy to add:
        # "level1": "https://soho.nascom.nasa.gov/sdb/hinode/sot/sot_genxcat_level1/",
    }

    FG_LEVEL_ROOTS = {
        "0": "https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/",
        "1": "https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1/",
    }

    SP_LEVEL_ROOTS = {
        "1": "https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1hao/",
        "2.1": "https://data.darts.isas.jaxa.jp/pub/hinode/sot/level2.1hao/",
    }

    _session = requests.Session()

    def __init__(self, *, catalog_variant="sirius", timeout=30.0):
        self.catalog_variant = catalog_variant
        self.timeout = timeout
        self._listing_cache = {}

    @classmethod
    def _can_handle_query(cls, *query):
        supported = {a.Time, a.Instrument, a.Level,
                     hattrs.SOTDetector, hattrs.Channel, hattrs.Mode}
        qtypes = {type(x) for x in query}
        if not supported.issuperset(qtypes):
            return False

        inst = [x for x in query if isinstance(x, a.Instrument)]
        if not inst:
            return False

        return str(inst[0].value).strip().lower() in {"sot", "hinode/sot"}

    @classmethod
    def register_values(cls):
        return {
            a.Instrument: [("SOT", "Hinode Solar Optical Telescope")],
            a.Source: [("Hinode", "Hinode / Solar-B")],
            a.Provider: [("SOHO/NASCOM", "SOT daily catalog"),
                         ("DARTS", "ISAS/JAXA DARTS archive")],
            a.Level: [("0", "Level 0"), ("1", "Level 1"), ("2.1", "Level 2.1")],
            hattrs.SOTDetector: [("FG", "Filtergraph"), ("SP", "Spectro-Polarimeter")],
            hattrs.Channel: [("Ca II H", "SOT FG channel"),
                             ("G band", "SOT FG channel"),
                             ("Fe I 630.2", "SOT FG channel")],
            hattrs.Mode: [("*", "Matched against OBS_TYPE-like catalog metadata")],
        }

    def _http_get(self, url):
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp

    def _list_links(self, url):
        if url in self._listing_cache:
            return self._listing_cache[url]

        html = self._http_get(url).text
        links = []
        for href in _HREF_RE.findall(html):
            if href.startswith("#") or href.startswith("?"):
                continue
            links.append(urljoin(url, href))

        out = []
        seen = set()
        for link in links:
            if link not in seen:
                seen.add(link)
                out.append(link)

        self._listing_cache[url] = out
        return out

    def _find_daily_catalog_url(self, day):
        root = self.CATALOG_ROOTS[self.catalog_variant]
        pattern = re.compile(rf"sot{day:%Y%m%d}_0000_[^/]+\.geny$", re.IGNORECASE)

        for link in self._list_links(root):
            if pattern.search(link):
                return link
        return None

    def _load_daily_catalog_rows(self, url):
        resp = self._http_get(url)
        with tempfile.NamedTemporaryFile(suffix=".geny") as tmp:
            tmp.write(resp.content)
            tmp.flush()
            data = readsav(tmp.name, python_dict=True, verbose=False)

        for value in data.values():
            names = getattr(getattr(value, "dtype", None), "names", None)
            if names:
                lowered = {name.lower() for name in names}
                if "date_obs" in lowered or "anytim_dobs" in lowered:
                    return list(value)

        raise RuntimeError(f"Could not identify catalog table in {url}")

    @staticmethod
    def _record_time(record):
        date_obs = _record_get(record, "DATE_OBS", "date_obs")
        if date_obs:
            return Time(_as_str(date_obs)).to_datetime()

        anytim = _record_get(record, "ANYTIM_DOBS", "anytim_dobs")
        if anytim:
            return Time(_as_str(anytim)).to_datetime()

        raise ValueError("No DATE_OBS or ANYTIM_DOBS in row")

    @staticmethod
    def _classify_row(record):
        """
        Conservative row classification for shared SOT catalogs.
        """
        obsdir = _as_str(_record_get(record, "OBSDIR", "obsdir", default="")).upper()
        obs_type = _as_str(_record_get(record, "OBS_TYPE", "obs_type", default="")).upper()
        slit = _as_str(_record_get(record, "SLIT", "slit", default="")).upper()
        fprefix = _as_str(_record_get(record, "FPREFIX", "fprefix", default="")).upper()

        joined = " ".join([obsdir, obs_type, slit, fprefix])

        if "SP" in joined or "SP3D" in joined:
            return "SP"

        if any(token in joined for token in ("FG", "BFI", "NFI")):
            return "FG"

        return "UNKNOWN"

    @classmethod
    def _passes_filters(cls, record, params):
        t = cls._record_time(record)
        if t < params["start"] or t > params["end"]:
            return False

        detector = cls._classify_row(record)
        if "detector" in params and params["detector"] != detector:
            return False

        if "channel" in params:
            channel_text = " ".join([
                _as_str(_record_get(record, "WAVE", "wave", default="")),
                _as_str(_record_get(record, "WAVEID", "waveid", default="")),
            ])
            if not _match_text(params["channel"], channel_text):
                return False

        if "mode" in params:
            mode_text = " ".join([
                _as_str(_record_get(record, "OBS_TYPE", "obs_type", default="")),
                _as_str(_record_get(record, "TARGET", "target", default="")),
                _as_str(_record_get(record, "OBSTITLE", "obstitle", default="")),
            ])
            if not _match_text(params["mode"], mode_text):
                return False

        return True

    @classmethod
    def _fg_directory_url(cls, record, level):
        t = cls._record_time(record)
        obsdir = _as_str(_record_get(record, "OBSDIR", "obsdir", default="FG")).strip("/")
        hourdir = f"H{t:%H}00"
        root = cls.FG_LEVEL_ROOTS.get(level, cls.FG_LEVEL_ROOTS["1"])
        return urljoin(root, f"{t:%Y/%m/%d}/{obsdir}/{hourdir}/")

    @classmethod
    def _fg_prefix(cls, record):
        t = cls._record_time(record)
        prefix = _as_str(_record_get(record, "FPREFIX", "fprefix", default=""))
        return f"{prefix}{t:%Y%m%d_%H%M%S}"

    @classmethod
    def _sp_parent_url(cls, record, level):
        t = cls._record_time(record)
        root = cls.SP_LEVEL_ROOTS.get(level, cls.SP_LEVEL_ROOTS["1"])
        return urljoin(root, f"{t:%Y/%m/%d}/SP3D/")

    @classmethod
    def _sp_obsid(cls, record):
        t = cls._record_time(record)
        return t.strftime("%Y%m%d_%H%M%S")

    def search(self, *args):
        query = attr.and_(*args)
        blocks = walker.create(query)

        results = []
        for params in blocks:
            for day in _daterange(params["start"], params["end"]):
                catalog_url = self._find_daily_catalog_url(day)
                if not catalog_url:
                    continue

                try:
                    rows = self._load_daily_catalog_rows(catalog_url)
                except Exception:
                    continue

                for record in rows:
                    try:
                        if not self._passes_filters(record, params):
                            continue

                        detector = self._classify_row(record)
                        t = self._record_time(record)
                        level = params.get("level", "1")

                        result = {
                            "Start Time": t,
                            "End Time": t,
                            "Instrument": "SOT",
                            "SOT Detector": detector,
                            "Source": "Hinode",
                            "Provider": "SOHO/NASCOM",
                            "Level": level,
                            "Channel": _as_str(_record_get(record, "WAVE", "wave", "WAVEID", "waveid", default="")),
                            "Mode": _as_str(_record_get(record, "OBS_TYPE", "obs_type", default="")),
                            "Catalog URL": catalog_url,
                            "OBSDIR": _as_str(_record_get(record, "OBSDIR", "obsdir", default="")),
                            "FPREFIX": _as_str(_record_get(record, "FPREFIX", "fprefix", default="")),
                        }

                        if detector == "FG":
                            result["url"] = self._fg_directory_url(record, level)
                            result["File Prefix"] = self._fg_prefix(record)
                        elif detector == "SP":
                            result["url"] = self._sp_parent_url(record, level)
                            result["SP ObsID"] = self._sp_obsid(record)
                        else:
                            result["url"] = ""

                        results.append(result)
                    except Exception:
                        continue

        return QueryResponseTable(results, client=self)

    @staticmethod
    def _make_filename(path, row, resp, url):
        name = os.path.basename(url.rstrip("/"))
        if resp is not None:
            cd = resp.headers.get("Content-Disposition")
            if cd:
                _, params = parse_header(cd)
                name = params.get("filename", name) or name
        return Path(str(path).format(file=name, **row.response_block_map))

    def _enqueue_url(self, downloader, path, row, url):
        downloader.enqueue_file(url, filename=partial(self._make_filename, path, row))

    @convert_row_to_table
    def fetch(self, query_results, *, path, downloader, **kwargs):
        include_sidecars = kwargs.pop("include_sidecars", False)

        for row in query_results:
            detector = row["SOT Detector"]

            if detector == "FG":
                directory_url = row["url"]
                prefix = row["File Prefix"]

                for link in self._list_links(directory_url):
                    name = os.path.basename(link.rstrip("/"))
                    if name.startswith(prefix) and name.lower().endswith(".fits"):
                        self._enqueue_url(downloader, path, row, link)

            elif detector == "SP":
                parent = row["url"]
                obsid = row["SP ObsID"]

                for scandir in self._list_links(parent):
                    if obsid not in scandir:
                        continue

                    if not scandir.endswith("/"):
                        continue

                    for link in self._list_links(scandir):
                        base = os.path.basename(link.rstrip("/")).lower()
                        if include_sidecars:
                            if base.endswith((".fits", ".txt", ".xml", ".log", ".save")):
                                self._enqueue_url(downloader, path, row, link)
                        else:
                            if base.endswith(".fits"):
                                self._enqueue_url(downloader, path, row, link)
