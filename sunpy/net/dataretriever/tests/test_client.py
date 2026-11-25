from unittest import mock

import pytest

from sunpy.net import attrs as a
from sunpy.net.dataretriever import LYRAClient
from sunpy.net.dataretriever.client import QueryResponse
from sunpy.time import parse_time


def test_reprs():
    rowdict = {}
    rowdict['Start Time'] = parse_time("2012/1/1")
    rowdict['End Time'] = parse_time("2012/1/2")
    resp = QueryResponse([rowdict])
    assert isinstance(resp, QueryResponse)
    strs = ["2012-01-01T00:00:00.000", "2012-01-02T00:00:00.000"]
    assert all(s in str(resp) for s in strs)
    assert all(s in repr(resp) for s in strs)


def test_time_range():
    rows = [{'Start Time': parse_time("2020/01/01"), 'End Time': parse_time("2020/01/02")},
            {'Start Time': parse_time("2019/01/01"), 'End Time': parse_time("2019/01/02")}]
    resp = QueryResponse(rows)

    assert resp.time_range().start == parse_time("2019/01/01")
    assert resp.time_range().end == parse_time("2020/01/02")


def test_missing_time_range():
    rows = [{'wibble': 1}]
    resp = QueryResponse(rows)

    assert resp.time_range() is None


def test_baseurl_is_rejected():
    with mock.patch.object(LYRAClient, 'baseurl', 'https://example.com/'):
        with pytest.raises(ValueError, match='baseurl'):
            LYRAClient().search(a.Time('2025/1/1', '2025/1/2'), a.Instrument.lyra)


def test_search_errors():
    fs = mock.Mock(async_impl=False, _strip_protocol=lambda url: url, ls=mock.Mock(side_effect=OSError('archive is down')))
    with mock.patch('sunpy.net.scraper.url_to_fs', return_value=(fs, None)):
        qr = LYRAClient().search(a.Time('2025/1/1', '2025/1/1 12:00'), a.Instrument.lyra)
    assert len(qr) == 0
    assert [str(error) for error in qr.errors] == ['archive is down']
