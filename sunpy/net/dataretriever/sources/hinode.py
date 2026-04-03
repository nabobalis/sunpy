from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import os
from pathlib import Path

import requests
from astropy.time import Time
from scipy.io import readsav

from sunpy.data import manager
from sunpy.net import attr, attrs as a
from sunpy.net.attr import AttrAnd, AttrOr, AttrWalker, DataAttr
from sunpy.net.base_client import BaseClient, QueryResponseTable, convert_row_to_table
from sunpy.net.dataretriever.attrs.hinode import Channel, Mode
from sunpy.util.net import parse_header

FG_CATALOG_URLS = [
    "https://soho.nascom.nasa.gov/sdb/hinode/sot/sot_genxcat_sirius/sot20260323_0000_NE1894.geny",
]

FG_CATALOG_SHA256 = "404eadb30e3baea51383ae7590c80f7a01c83e80d8adabf7d3de7b28882244ff"


@manager.require(
    "hinode_sot_fg_catalog",
    FG_CATALOG_URLS,
    FG_CATALOG_SHA256,
)
def get_fg_catalog_path() -> Path:
    return manager.get("hinode_sot_fg_catalog")


def load_fg_catalog():
    """
    Return the parsed IDL/genx catalog object from the cached local file.
    """
    path = get_fg_catalog_path()
    data = readsav(path, python_dict=True, verbose=False)

    for value in data.values():
        names = getattr(getattr(value, "dtype", None), "names", None)
        if names:
            lowered = {n.lower() for n in names}
            if "date_obs" in lowered or "anytim_dobs" in lowered:
                return value

    raise RuntimeError("Could not find FG catalog table in the genx file.")

walker = AttrWalker()


@walker.add_creator(AttrOr)
def _create_or(wlk, tree):
    out = []
    for sub in tree.attrs:
        out.extend(wlk.create(sub))
    return out


@walker.add_creator(AttrAnd, DataAttr)
def _create_and(wlk, tree):
    params = {}
    wlk.apply(tree, params)
    return [params]


@walker.add_applier(AttrAnd)
def _apply_and(wlk, tree, params):
    for attribute in tree.attrs:
        wlk.apply(attribute, params)


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


@walker.add_applier(Channel)
def _apply_channel(wlk, query, params):
    params["channel"] = str(query.value)


@walker.add_applier(Mode)
def _apply_mode(wlk, query, params):
    params["mode"] = str(query.value)


def _as_str(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore")
    return str(value)


def _record_get(record, *names, default=None):
    available = {}
    dtype = getattr(record, "dtype", None)
    dtype_names = getattr(dtype, "names", None)
    if dtype_names:
        for name in dtype_names:
            available[name.lower()] = record[name]

    if hasattr(record, "keys"):
        for key in record.keys():
            available[str(key).lower()] = record[key]

    for name in names:
        if name.lower() in available:
            return available[name.lower()]
    return default


def _match_text(needle, haystack):
    if not needle:
        return True
    if haystack is None:
        return False
    return needle.lower() in haystack.lower()


class _HinodeBaseClient(BaseClient):
    _session = requests.Session()

    @staticmethod
    def _row_to_filepath(path: Path, row, resp, url: str) -> Path:
        name = os.path.basename(url.rstrip("/"))
        if resp is not None:
            cdheader = resp.headers.get("Content-Disposition")
            if cdheader:
                _, params = parse_header(cdheader)
                name = params.get("filename", name) or name
        return Path(str(path).format(file=name, **row.response_block_map))

    def _enqueue_url(self, downloader, path: Path, row, url: str):
        from functools import partial
        downloader.enqueue_file(url, filename=partial(self._row_to_filepath, path, row))


class HinodeSOTFGClient(_HinodeBaseClient):
    """
    Catalog-backed Fido client for Hinode SOT FG.
    """

    @classmethod
    def _can_handle_query(cls, *query):
        allowed = {a.Time, a.Instrument, a.Level, Channel, Mode}
        qtypes = {type(x) for x in query}
        if not allowed.issuperset(qtypes):
            return False

        inst = [x for x in query if isinstance(x, a.Instrument)]
        if not inst:
            return False

        return str(inst[0].value).strip().lower() in {"sot-fg", "fg", "hinode/sot-fg"}

    @classmethod
    def register_values(cls):
        return {
            a.Instrument: [("SOT-FG", "Hinode Solar Optical Telescope Filtergraph")],
            a.Source: [("Hinode", "Hinode / Solar-B")],
            a.Provider: [("DARTS", "ISAS/JAXA DARTS archive")],
            a.Level: [("0", "Level 0"), ("1", "Level 1")],
            Channel: [
                ("Ca II H", "SOT-FG channel"),
                ("G band", "SOT-FG channel"),
                ("Fe I 630.2", "SOT-FG channel"),
            ],
            Mode: [("*", "Matched against FG catalog metadata")],
        }

    @staticmethod
    @lru_cache(maxsize=1)
    def _catalog_rows():
        return list(load_fg_catalog())

    @staticmethod
    def _record_time(record) -> datetime:
        date_obs = _record_get(record, "DATE_OBS", "date_obs")
        if date_obs:
            return Time(_as_str(date_obs)).to_datetime()

        anytim = _record_get(record, "ANYTIM_DOBS", "anytim_dobs")
        if anytim:
            return Time(_as_str(anytim)).to_datetime()

        raise ValueError("No time field found in FG catalog row.")

    @classmethod
    def _passes_filters(cls, record, params):
        t = cls._record_time(record)
        if t < params["start"] or t > params["end"]:
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
                _as_str(_record_get(record, "GEN_ID", "gen_id", default="")),
            ])
            if not _match_text(params["mode"], mode_text):
                return False

        return True

    @classmethod
    def _directory_url(cls, record, level):
        root = {
            "0": "https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/",
            "1": "https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1/",
        }[level]

        t = cls._record_time(record)
        obsdir = _as_str(_record_get(record, "OBSDIR", "obsdir", default="FG")).strip("/")
        return f"{root}{t:%Y/%m/%d}/{obsdir}/"

    @classmethod
    def _file_prefix(cls, record):
        t = cls._record_time(record)
        prefix = _as_str(_record_get(record, "FPREFIX", "fprefix", default=""))
        return f"{prefix}{t:%Y%m%d_%H%M%S}"

    def search(self, *args):
        query = attr.and_(*args)
        blocks = walker.create(query)

        rows = []
        catalog = self._catalog_rows()

        for params in blocks:
            level = params.get("level", "1")
            for record in catalog:
                try:
                    if not self._passes_filters(record, params):
                        continue

                    t = self._record_time(record)
                    rows.append({
                        "Start Time": t,
                        "End Time": t,
                        "Instrument": "SOT-FG",
                        "Source": "Hinode",
                        "Provider": "DARTS",
                        "Level": level,
                        "Channel": _as_str(_record_get(record, "WAVE", "wave", "WAVEID", "waveid", default="")),
                        "Mode": _as_str(_record_get(record, "OBS_TYPE", "obs_type", default="")),
                        "Directory URL": self._directory_url(record, level),
                        "File Prefix": self._file_prefix(record),
                        "url": self._directory_url(record, level),
                    })
                except Exception:
                    continue

        return QueryResponseTable(rows, client=self)

    def _list_links(self, url):
        import re
        html = self._session.get(url, timeout=30).text
        return [
            requests.compat.urljoin(url, href)
            for href in re.findall(r'href=["\\\']([^"\\\']+)["\\\']', html, re.I)
            if not href.startswith(("#", "?"))
        ]

    @convert_row_to_table
    def fetch(self, query_results, *, path: Path, downloader, **kwargs):
        for row in query_results:
            directory_url = row["Directory URL"]
            prefix = row["File Prefix"]

            for url in self._list_links(directory_url):
                name = os.path.basename(url.rstrip("/"))
                if name.startswith(prefix) and name.lower().endswith(".fits"):
                    self._enqueue_url(downloader, path, row, url)
