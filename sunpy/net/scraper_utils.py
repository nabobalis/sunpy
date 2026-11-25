import calendar
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from sunpy.time import TimeRange
from sunpy.util.decorators import deprecated

__all__ = ["extract_timestep", "date_floor", "get_timerange_from_exdict"]

TIME_QUANTITIES = {
    'day': timedelta(days=1),
    'hour': timedelta(hours=1),
    'minute': timedelta(minutes=1),
    'second': timedelta(seconds=1),
    'millisecond': timedelta(milliseconds=1)
}


@deprecated(since="8.1")
def extract_timestep(directoryPattern):
    """
    Obtain the smallest time step for the given pattern.

    Parameters
    ----------
    directoryPattern : `str`
        The pattern containing the datetime-formats

    Returns
    -------
    `dateutil.relativedelta.relativedelta`
        The smallest timestep unit from the provided pattern.
    """
    if "%S" in directoryPattern:
        return relativedelta(seconds=1)
    elif "%M" in directoryPattern:
        return relativedelta(minutes=1)
    elif any(hour in directoryPattern for hour in ["%H"]):
        return relativedelta(hours=1)
    elif any(day in directoryPattern for day in ["%d", "%j"]):
        return relativedelta(days=1)
    elif any(month in directoryPattern for month in ["%b", "%B", "%m"]):
        return relativedelta(months=1)
    elif any(year in directoryPattern for year in ["%Y", "%y"]):
        return relativedelta(years=1)
    else:
        return None


@deprecated(since="8.1")
def date_floor(date, timestep):
    """
    Return the "floor" of the given date and timestep.

    Parameters
    ----------
    date : `datetime.datetime` or `astropy.time.Time`
        The date to floor.
    timestep : `dateutil.relativedelta.relativedelta`
        The smallest timestep to floor.

    Returns
    -------
    `datetime.datetime`
        The time floored at the given time step
    """
    date_parts = [int(p) for p in date.strftime('%Y,%m,%d,%H,%M,%S').split(',')]
    date_parts[-1] = date_parts[-1] % 60
    date = datetime(*date_parts)
    orig_time_tup = date.timetuple()
    time_tup = [orig_time_tup.tm_year, orig_time_tup.tm_mon, orig_time_tup.tm_mday,
                orig_time_tup.tm_hour, orig_time_tup.tm_min, orig_time_tup.tm_sec]
    if timestep == relativedelta(minutes=1):
        time_tup[-1] = 0
    elif timestep == relativedelta(hours=1):
        time_tup[-2:] = [0, 0]
    elif timestep == relativedelta(days=1):
        time_tup[-3:] = [0, 0, 0]
    elif timestep == relativedelta(months=1):
        time_tup[-4:] = [1, 0, 0, 0]
    elif timestep == relativedelta(years=1):
        time_tup[-5:] = [1, 1, 0, 0, 0]

    return datetime(*time_tup)


def get_timerange_from_exdict(exdict):
    """
    Function to get URL's timerange using extracted metadata.
    It computes start and end times first using the given
    dictionary and then returns a timerange.

    Parameters
    ----------
    exdict : `dict`
        Metadata extracted from the file's url.

    Returns
    -------
    `~sunpy.time.TimeRange`
        The time range of the file.
    """
    # This function deliberately does NOT use astropy.time because it is not
    # needed, and the performance overheads in dealing with astropy.time.Time
    # objects are large
    exdict = dict(exdict)
    year = int(exdict.get('year', 100))
    if year < 100:
        # The same pivot as strptime's %y
        exdict['year'] = year + (1900 if year >= 69 else 2000)
    for name, code in (('month_name', '%B'), ('month_name_abbr', '%b')):
        if name in exdict:
            exdict.setdefault('month', datetime.strptime(exdict[name], code).month)
    if 'day_of_year' in exdict:
        date = datetime(int(exdict.get('year', 1)), 1, 1) + timedelta(days=int(exdict['day_of_year']) - 1)
        exdict['month'], exdict['day'] = date.month, date.day
    if 'week_number' in exdict and 'year' in exdict and 'day' not in exdict:
        # The weeks of strftime's %W: they start on a Monday and stay within their year.
        year = int(exdict['year'])
        monday = datetime.strptime(f"{year} {int(exdict['week_number'])} 1", '%Y %W %w')
        start, end = max(monday, datetime(year, 1, 1)), min(monday + timedelta(days=7), datetime(year + 1, 1, 1))
        return TimeRange(start, end - TIME_QUANTITIES['millisecond'])
    datetypes = ['year', 'month', 'day']
    timetypes = ['hour', 'minute', 'second']
    dtlist = [int(exdict.get(d, 1)) for d in datetypes]
    dtlist.extend([int(exdict.get(t, 0)) for t in timetypes])
    startTime = datetime(*dtlist, 1000*int(exdict.get('millisecond', 0)) + int(exdict.get('microsecond', 0)))
    tdelta = TIME_QUANTITIES['millisecond']
    if "second" in exdict:
        tdelta = TIME_QUANTITIES['second']
    elif "minute" in exdict:
        tdelta = TIME_QUANTITIES['minute']
    elif "hour" in exdict:
        tdelta = TIME_QUANTITIES['hour']
    elif "day" in exdict:
        tdelta = TIME_QUANTITIES['day']
    elif "month" in exdict:
        days_in_month = calendar.monthrange(int(exdict['year']), int(exdict['month']))[1]
        tdelta = days_in_month*TIME_QUANTITIES['day']
    elif "year" in exdict:
        if calendar.isleap(int(exdict['year'])):
            tdelta = 366*TIME_QUANTITIES['day']
        else:
            tdelta = 365*TIME_QUANTITIES['day']
    endTime = startTime + tdelta - TIME_QUANTITIES['millisecond']
    return TimeRange(startTime, endTime)
