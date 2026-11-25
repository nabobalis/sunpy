from datetime import datetime

import pytest
from dateutil.relativedelta import relativedelta

from sunpy.net.scraper_utils import date_floor, extract_timestep, get_timerange_from_exdict
from sunpy.time import TimeRange, parse_time

DATETIME_PATTERN_EXAMPLES = [
    ('%b%y', relativedelta(months=1)),
    ('%m%y', relativedelta(months=1)),
    ('%H%d', relativedelta(hours=1)),
    ('%y%b', relativedelta(months=1)),
]

@pytest.mark.parametrize(('pattern', 'mintime'), DATETIME_PATTERN_EXAMPLES)
def test_extract_timestep(pattern, mintime):
    assert mintime == extract_timestep(pattern)

@pytest.mark.parametrize(('exdict', 'start', 'end'), [
    ({"year": 2000}, '2000-01-01 00:00:00', '2000-12-31 23:59:59.999000'),
    ({"year": 2016, "month": 2}, '2016-02-01 00:00:00', '2016-02-29 23:59:59.999000'),
    ({'year': 2019, 'month': 2, 'day': 28}, '2019-02-28 00:00:00', '2019-02-28 23:59:59.999000'),
    ({'year': 2019, 'month': 2, 'day': 28, 'hour': 23}, '2019-02-28 23:00:00', '2019-02-28 23:59:59.999000'),
    ({'year': 2019, 'month': 2, 'day': 28, 'hour': 23, 'minute': 59},
     '2019-02-28 23:59:00', '2019-02-28 23:59:59.999000'),
    ({'year': 2020, 'month': 7, 'day': 31, 'hour': 23, 'minute': 59, 'second': 59},
     '2020-07-31 23:59:59', '2020-07-31 23:59:59.999000'),
    ({'year': 96, 'month': 1, 'day': 15}, '1996-01-15 00:00:00', '1996-01-15 23:59:59.999000'),
    ({'year': 7, 'month_name_abbr': 'Aug'}, '2007-08-01 00:00:00', '2007-08-31 23:59:59.999000'),
    ({'year': 2020, 'month_name': 'February'}, '2020-02-01 00:00:00', '2020-02-29 23:59:59.999000'),
    ({'year': 2020, 'day_of_year': 100}, '2020-04-09 00:00:00', '2020-04-09 23:59:59.999000'),
    ({'year': 2020, 'week_number': 0}, '2020-01-01 00:00:00', '2020-01-05 23:59:59.999000'),
    ({'year': 2020, 'week_number': 1}, '2020-01-06 00:00:00', '2020-01-12 23:59:59.999000'),
    ({'year': 2020, 'week_number': 52}, '2020-12-28 00:00:00', '2020-12-31 23:59:59.999000'),
    ({'year': 2013, 'month': 4, 'day': 10, 'hour': 23, 'minute': 12, 'second': 11, 'millisecond': 119},
     '2013-04-10 23:12:11.119', '2013-04-10 23:12:12.118'),
    ({'year': 2013, 'month': 4, 'day': 10, 'hour': 23, 'minute': 12, 'second': 11, 'microsecond': 119000},
     '2013-04-10 23:12:11.119', '2013-04-10 23:12:12.118'),
])
def test_get_timerange_from_exdict(exdict, start, end):
    tr = TimeRange(start, end)
    file_timerange = get_timerange_from_exdict(exdict)
    assert file_timerange == tr

@pytest.mark.parametrize(('testdate', 'pattern', 'floor_val'), [
    ((2004, 3, 6), '%y', datetime(2004, 1, 1, 0, 0)),
    ((2004, 3, 6), '%b%y', datetime(2004, 3, 1, 0, 0)),
    ((2023, 3, 12), '%y%M', datetime(2023, 3, 12, 0, 0)),
    ((2023, 2, 3), '%m%d', datetime(2023, 2, 3, 0, 0)),
    ((2023, 2, 23), '%d%H', datetime(2023, 2, 23, 0, 0)),
    ((2023, 12, 12), '%H%S', datetime(2023, 12, 12, 0, 0)),
])
def test_date_floor(testdate, pattern, floor_val):
    date = parse_time(testdate)
    timestep = extract_timestep(pattern)
    assert date_floor(date, timestep) == floor_val
