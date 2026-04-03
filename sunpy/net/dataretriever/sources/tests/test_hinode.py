import tempfile
from unittest import mock

import pytest

import sunpy.net.dataretriever.sources.hinode as hinode
from sunpy.net import attrs as a
from sunpy.net.dataretriever.client import QueryResponse
from sunpy.time import parse_time


@pytest.fixture
def fg_client():
    return hinode.HinodeSOTFGClient()


@pytest.fixture
def sp_client():
    return hinode.HinodeSOTSPClient()


class DummyDownloader:
    def __init__(self):
        self.calls = []

    def enqueue_file(self, url, filename, **kwargs):
        self.calls.append((url, filename, kwargs))

    def download(self):
        return self.calls


def mock_query_object(client, detector='FG', level='1', url=None):
    if url is None:
        if detector == 'FG':
            url = ('https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1/'
                   '2011/12/13/FG/H0600/FG20111213_060000.0.fits')
        else:
            url = ('https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1hao/'
                   '2011/12/13/SP3D/20111213_020000/20111213_020000_L1.0.fits')

    obj = {
        'Start Time': parse_time('2011-12-13T06:00:00'),
        'End Time': parse_time('2011-12-13T06:00:00'),
        'Instrument': 'SOT',
        'SOTDetector': detector,
        'Level': level,
        'Source': 'Hinode',
        'Provider': 'DARTS',
        'url': url,
    }
    return QueryResponse([obj], client=client)


@pytest.mark.parametrize(
    ('client_cls', 'detector', 'level', 'expected'),
    [
        (hinode.HinodeSOTFGClient, 'FG', '0', True),
        (hinode.HinodeSOTFGClient, 'FG', '1', True),
        (hinode.HinodeSOTFGClient, 'SP', '1', False),
        (hinode.HinodeSOTFGClient, 'FG', '2', False),
        (hinode.HinodeSOTSPClient, 'SP', '0', True),
        (hinode.HinodeSOTSPClient, 'SP', '1', True),
        (hinode.HinodeSOTSPClient, 'SP', '2', True),
        (hinode.HinodeSOTSPClient, 'SP', '2.1', True),
        (hinode.HinodeSOTSPClient, 'FG', '1', False),
    ],
)
def test_can_handle_query(client_cls, detector, level, expected):
    query = (
        a.Time('2011-12-13 06:00', '2011-12-13 07:00'),
        a.Instrument('SOT'),
        a.Level(level),
        a.hinode.SOTDetector(detector),
    )
    assert client_cls._can_handle_query(*query) is expected


@pytest.mark.parametrize(
    ('level', 'timerange', 'filesmeta', 'expected_urls'),
    [
        (
            1,
            ('2011-12-13 06:00', '2011-12-13 06:15'),
            [
                {
                    'year': 2011,
                    'month': 12,
                    'day': 13,
                    'hour': 6,
                    'minute': 10,
                    'second': 0,
                    'subsec': 0,
                    'url': ('https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1/'
                            '2011/12/13/FG/H0600/FG20111213_061000.0.fits'),
                },
                {
                    'year': 2011,
                    'month': 12,
                    'day': 13,
                    'hour': 6,
                    'minute': 0,
                    'second': 0,
                    'subsec': 0,
                    'url': ('https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1/'
                            '2011/12/13/FG/H0600/FG20111213_060000.0.fits'),
                },
            ],
            [
                'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1/2011/12/13/FG/H0600/FG20111213_060000.0.fits',
                'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1/2011/12/13/FG/H0600/FG20111213_061000.0.fits',
            ],
        ),
        (
            0,
            ('2013-07-13 00:13:32', '2013-07-13 00:13:33'),
            [{
                'year': 2013,
                'month': 7,
                'day': 13,
                'hour': 0,
                'minute': 13,
                'second': 32,
                'subsec': 7,
                'url': ('https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/'
                        '2013/07/13/FG/H0000/FG20130713_001332.7.fits'),
            }],
            ['https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/2013/07/13/FG/H0000/FG20130713_001332.7.fits'],
        ),
    ],
)
def test_search_fg(fg_client, level, timerange, filesmeta, expected_urls):
    with mock.patch('sunpy.net.dataretriever.client.Scraper._extract_files_meta', return_value=filesmeta):
        qr = fg_client.search(
            a.Time(*timerange),
            a.Instrument('SOT'),
            a.Level(level),
            a.hinode.SOTDetector('FG'),
        )

    assert [str(u) for u in qr['url']] == expected_urls
    assert qr['Level'][0] == str(level)
    assert qr['SOTDetector'][0] == 'FG'


@pytest.mark.parametrize(
    ('level', 'timerange', 'filesmeta', 'expected_urls'),
    [
        (
            1,
            ('2011-12-13 02:00', '2011-12-13 04:30'),
            [
                {
                    'year': 2011,
                    'month': 12,
                    'day': 13,
                    'hour': 2,
                    'minute': 0,
                    'second': 0,
                    'url': 'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1hao/2011/12/13/SP3D/20111213_020000/20111213_020000_L1.0.fits',
                },
                {
                    'year': 2011,
                    'month': 12,
                    'day': 13,
                    'hour': 4,
                    'minute': 30,
                    'second': 0,
                    'url': 'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1hao/2011/12/13/SP3D/20111213_043000/20111213_043000_L1.0.fits',
                },
            ],
            [
                'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1hao/2011/12/13/SP3D/20111213_020000/20111213_020000_L1.0.fits',
                'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1hao/2011/12/13/SP3D/20111213_043000/20111213_043000_L1.0.fits',
            ],
        ),
        (
            0,
            ('2013-07-13 10:02:00', '2013-07-13 10:03:00'),
            [
                {
                    'year': 2013,
                    'month': 7,
                    'day': 13,
                    'hour': 10,
                    'minute': 2,
                    'second': 50,
                    'url': 'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/2013/07/13/SP4D/H1000/SP4D20130713_100250.1.fits',
                },
                {
                    'year': 2013,
                    'month': 7,
                    'day': 13,
                    'hour': 10,
                    'minute': 2,
                    'second': 54,
                    'url': 'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/2013/07/13/SP4D/H1000/SP4D20130713_100254.0.fits',
                },
            ],
            [
                'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/2013/07/13/SP4D/H1000/SP4D20130713_100250.1.fits',
                'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/2013/07/13/SP4D/H1000/SP4D20130713_100254.0.fits',
            ],
        ),
    ],
)
def test_search_sp(sp_client, level, timerange, filesmeta, expected_urls):
    with mock.patch('sunpy.net.dataretriever.client.Scraper._extract_files_meta', return_value=filesmeta):
        qr = sp_client.search(
            a.Time(*timerange),
            a.Instrument('SOT'),
            a.Level(level),
            a.hinode.SOTDetector('SP'),
        )

    assert len(qr) == len(expected_urls)
    assert [str(u) for u in qr['url']] == expected_urls


REAL_URL_CASES = [
    (
        'FG',
        '0',
        '2013-07-13 00:13:32',
        '2013-07-13 00:13:33',
        'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/2013/07/13/FG/H0000/FG20130713_001332.7.fits',
    ),
    (
        'SP',
        '0',
        '2013-07-13 10:02:50',
        '2013-07-13 10:02:51',
        'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level0/2013/07/13/SP4D/H1000/SP4D20130713_100250.1.fits',
    ),
]


@pytest.mark.remote_data
@pytest.mark.parametrize(
    ('detector', 'level', 'start', 'end', 'expected_url'),
    REAL_URL_CASES,
)
def test_real_archive_urls(fg_client, sp_client, detector, level, start, end,
                           expected_url):
    hinode_client = fg_client if detector == 'FG' else sp_client
    qr = hinode_client.search(
        a.Time(start, end),
        a.Instrument('SOT'),
        a.Level(level),
        a.hinode.SOTDetector(detector),
    )

    assert len(qr) == 1
    assert qr[0]['url'] == expected_url

    with tempfile.TemporaryDirectory() as tmpdir:
        file = hinode_client.fetch(qr, path=tmpdir)
    assert file[0].split('/')[-1] == expected_url.split('/')[-1]

def test_search_unsupported_fg_level(fg_client):
    qr = fg_client.search(
        a.Time('2011-12-13 06:00', '2011-12-13 07:00'),
        a.Instrument('SOT'),
        a.Level(2),
        a.hinode.SOTDetector('FG'),
    )
    assert len(qr) == 0


def test_dummy_fetch_fg(fg_client, tmp_path):
    downloader = DummyDownloader()
    qr = mock_query_object(fg_client)

    result = fg_client.fetch(
        qr[0],
        path=tmp_path / '{sotdetector}' / '{file}',
        downloader=downloader,
    )

    assert result == downloader.calls
    assert downloader.calls == [
        (
            'https://data.darts.isas.jaxa.jp/pub/hinode/sot/level1/2011/12/13/FG/H0600/FG20111213_060000.0.fits',
            tmp_path / 'FG' / 'FG20111213_060000.0.fits',
            {},
        ),
    ]


def test_dummy_fetch_sp(sp_client, tmp_path):
    downloader = DummyDownloader()
    qr = mock_query_object(sp_client, detector='SP', url='https://example.com/20111213_020000/file_a.fits')
    result = sp_client.fetch(qr, path=tmp_path, downloader=downloader)

    assert result == downloader.calls
    assert downloader.calls == [
        ('https://example.com/20111213_020000/file_a.fits', tmp_path / 'file_a.fits', {}),
    ]


def test_attr_reg():
    assert hasattr(a, 'hinode')
    assert a.hinode.SOTDetector.fg == a.hinode.SOTDetector('FG')
    assert a.hinode.SOTDetector.sp == a.hinode.SOTDetector('SP')


def test_show(fg_client):
    mock_qr = mock_query_object(fg_client)
    qrshow0 = mock_qr.show()
    qrshow1 = mock_qr.show('Start Time', 'SOTDetector')
    allcols = {'Start Time', 'End Time', 'Instrument', 'SOTDetector', 'Level', 'Source', 'Provider', 'url'}
    assert not allcols.difference(qrshow0.colnames)
    assert qrshow1.colnames == ['Start Time', 'SOTDetector']
    assert qrshow0['Instrument'][0] == 'SOT'
