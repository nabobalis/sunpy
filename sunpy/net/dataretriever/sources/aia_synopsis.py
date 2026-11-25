import numpy as np

import astropy.units as u

from sunpy.net import attrs as a
from sunpy.net.dataretriever import GenericClient

__all__ = ["AIASynopsisClient"]


class AIASynopsisClient(GenericClient):
    """
    A client for retrieving AIA "synoptic" data from the JSOC.

    This dataset is not synoptic like HMI and MDI Synoptic images which are images of the solar surface reconstructed from many observations over a solar rotation but rather a synopsis of AIA data.

    The AIA synoptic data are calibrated Level 1.5 images with reduced 1k x 1k resolution at regular 2-minute cadence.

    Note
    ----

    This client does not support multiple wavelengths in a single query. If you want to download multiple wavelengths, you need to do it in separate queries.

    References
    ----------
    * `Readme <https://jsoc1.stanford.edu/data/aia/synoptic/README.html>`__

    Examples
    --------
    >>> from sunpy.net import Fido, attrs as a
    >>> results = Fido.search(a.Time("2016/1/1", "2016/1/1 00:01:00"),
    ...                       a.Instrument.aia, a.Level("1.5s"))  # doctest: +REMOTE_DATA
    >>> results  # doctest: +REMOTE_DATA
    <sunpy.net.fido_factory.UnifiedResponse object at ...>
    Results from 1 Provider:
    <BLANKLINE>
    9 Results from the AIASynopsisClient:
    Source: https://jsoc1.stanford.edu/data/aia/synoptic/
    <BLANKLINE>
           Start Time               End Time        Instrument  Physobs  Source Provider Level Wavelength
    ----------------------- ----------------------- ---------- --------- ------ -------- ----- ----------
    2016-01-01 00:00:00.000 2016-01-01 00:00:59.999        AIA intensity    SDO     JSOC  1.5S         94
    2016-01-01 00:00:00.000 2016-01-01 00:00:59.999        AIA intensity    SDO     JSOC  1.5S        131
    2016-01-01 00:00:00.000 2016-01-01 00:00:59.999        AIA intensity    SDO     JSOC  1.5S        171
    2016-01-01 00:00:00.000 2016-01-01 00:00:59.999        AIA intensity    SDO     JSOC  1.5S        193
    2016-01-01 00:00:00.000 2016-01-01 00:00:59.999        AIA intensity    SDO     JSOC  1.5S        211
    2016-01-01 00:00:00.000 2016-01-01 00:00:59.999        AIA intensity    SDO     JSOC  1.5S        304
    2016-01-01 00:00:00.000 2016-01-01 00:00:59.999        AIA intensity    SDO     JSOC  1.5S        335
    2016-01-01 00:00:00.000 2016-01-01 00:00:59.999        AIA intensity    SDO     JSOC  1.5S       1600
    2016-01-01 00:00:00.000 2016-01-01 00:00:59.999        AIA intensity    SDO     JSOC  1.5S       4500
    <BLANKLINE>
    <BLANKLINE>
    """
    pattern = ('https://jsoc1.stanford.edu/data/aia/synoptic/'
               '{{year:4d}}/{{month:2d}}/{{day:2d}}/H{{hour:2d}}00/AIA{{year:4d}}{{month:2d}}{{day:2d}}_{{hour:2d}}{{minute:2d}}_{{Wavelength:04d}}.fits')
    required = {a.Time, a.Instrument, a.Level}

    @property
    def info_url(self):
        return "https://jsoc1.stanford.edu/data/aia/synoptic/"

    @classmethod
    def pre_search_hook(cls, *args, **kwargs):
        baseurl, pattern, matchdict = super().pre_search_hook(*args, **kwargs)
        if "Wavelength" in matchdict:
            # The scraper matches strings, so the wavelength has to be written as it is in the filenames.
            wavelength = matchdict["Wavelength"].min.to_value(u.AA, u.equivalencies.spectral())
            matchdict["Wavelength"] = str(np.round(wavelength)).replace(".0", "")
        return baseurl, pattern, matchdict

    def search(self, *args, **kwargs):
        response = super().search(*args, **kwargs)
        sample = [arg.value for arg in args if isinstance(arg, a.Sample)]
        if sample and len(response):
            # The sample rate has to be applied here, counting from the first file found.
            elapsed = (response['Start Time'] - response['Start Time'][0]).to_value(u.s)
            response = response[elapsed % sample[0] == 0]
        return response

    @classmethod
    def register_values(cls):
        adict = {
            a.Instrument: [("AIA", "Data from the Atmospheric Imaging Assembly instrument.")],
            a.Physobs: [
                ("intensity", "Brightness or intensity of the solar atmosphere at different wavelengths.")
            ],
            a.Source: [("SDO", "The Solar Dynamics Observatory.")],
            a.Provider: [("JSOC", "Joint Science Operations Center at Stanford.")],
            a.Level: [("1.5s", "Level 1.5 data processed for quicker analysis.")],
        }
        return adict
