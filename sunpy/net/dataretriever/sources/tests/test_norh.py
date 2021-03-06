import pytest
from hypothesis import HealthCheck, given, settings

import astropy.units as u
from astropy.time import Time, TimeDelta

import sunpy.net.dataretriever.sources.norh as norh
from sunpy.net import Fido
from sunpy.net import attrs as a
from sunpy.net.dataretriever.client import QueryResponse
from sunpy.net.fido_factory import UnifiedResponse
from sunpy.net.tests.strategies import range_time, time_attr
from sunpy.time.timerange import TimeRange


@pytest.fixture
def LCClient():
    return norh.NoRHClient()


# Don't use time_attr here for speed.
def test_query_no_wave(LCClient):
    with pytest.raises(ValueError):
        LCClient.search(a.Time("2016/10/1", "2016/10/2"), a.Instrument.norh)


@pytest.mark.remote_data
@pytest.mark.parametrize("timerange,url_start,url_end", [
    (TimeRange('2012/4/21', '2012/4/21'),
     'ftp://solar-pub.nao.ac.jp/pub/nsro/norh/data/tcx/2012/04/tca120421',
     'ftp://solar-pub.nao.ac.jp/pub/nsro/norh/data/tcx/2012/04/tca120421'
     ),
    (TimeRange('2012/12/1', '2012/12/2'),
     'ftp://solar-pub.nao.ac.jp/pub/nsro/norh/data/tcx/2012/12/tca121201',
     'ftp://solar-pub.nao.ac.jp/pub/nsro/norh/data/tcx/2012/12/tca121202'
     ),
    (TimeRange('2012/3/7', '2012/3/14'),
     'ftp://solar-pub.nao.ac.jp/pub/nsro/norh/data/tcx/2012/03/tca120307',
     'ftp://solar-pub.nao.ac.jp/pub/nsro/norh/data/tcx/2012/03/tca120314'
     )
])
def test_get_url_for_time_range(LCClient, timerange, url_start, url_end):
    urls = LCClient._get_url_for_timerange(timerange, wavelength=17*u.GHz)
    assert isinstance(urls, list)
    assert urls[0] == url_start
    assert urls[-1] == url_end


@given(time_attr())
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_can_handle_query(LCClient, time):
    ans1 = LCClient._can_handle_query(time, a.Instrument.norh)
    assert ans1 is True
    ans1 = LCClient._can_handle_query(time, a.Instrument.norh,
                                      a.Wavelength(10*u.GHz))
    assert ans1 is True
    ans2 = LCClient._can_handle_query(time)
    assert ans2 is False


@pytest.mark.remote_data
@pytest.mark.parametrize("wave", [a.Wavelength(17*u.GHz), a.Wavelength(34*u.GHz)])
@given(time=range_time(Time('1992-6-1')))
@settings(max_examples=2, deadline=50000, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_query(LCClient, time, wave):
    qr1 = LCClient.search(time, a.Instrument.norh, wave)
    assert isinstance(qr1, QueryResponse)
    # Not all hypothesis queries are going to produce results, and
    if qr1:
        # There are no observations everyday
        #  so the results found have to be equal or later than the queried time
        #  (looking at the date because it may search for miliseconds, but only date is available)
        assert qr1.time_range().start.strftime('%Y-%m-%d') >= time.start.strftime('%Y-%m-%d')
        #  and the end time equal or smaller.
        # hypothesis can give same start-end, but the query will give you from start to end (so +1)
        assert qr1.time_range().end <= time.end + TimeDelta(1*u.day)


def test_wavelength_range(LCClient):
    with pytest.raises(ValueError):
        LCClient.search(
            a.Time("2016/10/1", "2016/10/2"), a.Instrument.norh,
            a.Wavelength(17 * u.GHz, 34 * u.GHz))


def test_query_wrong_wave(LCClient):
    with pytest.raises(ValueError):
        LCClient.search(a.Time("2016/10/1", "2016/10/2"), a.Instrument.norh,
                        a.Wavelength(50*u.GHz))


@pytest.mark.remote_data
@pytest.mark.parametrize("time,instrument,wave", [
    (a.Time('2012/10/4', '2012/10/4'), a.Instrument.norh, a.Wavelength(17*u.GHz)),
    (a.Time('2012/10/4', '2012/10/4'), a.Instrument.norh, a.Wavelength(34*u.GHz))])
def test_get(LCClient, time, instrument, wave):
    qr1 = LCClient.search(time, instrument, wave)
    download_list = LCClient.fetch(qr1)
    assert len(download_list) == len(qr1)


@pytest.mark.remote_data
@pytest.mark.parametrize(
    "time, instrument, wave",
    [(a.Time('2012/10/4', '2012/10/4'), a.Instrument.norh, a.Wavelength(17*u.GHz) | a.Wavelength(34*u.GHz))])
def test_fido(time, instrument, wave):
    qr = Fido.search(time, instrument, wave)
    assert isinstance(qr, UnifiedResponse)
    response = Fido.fetch(qr)
    assert len(response) == qr[0]._numfile + qr[1]._numfile


def test_attr_reg():
    assert a.Instrument.norh == a.Instrument('NORH')


def test_client_repr(LCClient):
    """
    Repr check
    """
    output = str(LCClient)
    assert output[:50] == 'sunpy.net.dataretriever.sources.norh.NoRHClient\n\nP'
