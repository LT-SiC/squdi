# -*- coding: utf-8 -*-
"""
Dummy version of the TimeTagger hardware module (qudi.hardware.timetagger ... class TT).

It needs neither the TimeTagger python package nor a device. All measurement objects mimic the small part
of the TimeTagger API that the logic modules use (getData, start, stop, clear, ready, ...) and return
simulated data.

Most important for the gated counter / queue:
    count_between_markers(n_values=...) creates `self.gated_counter_countbetweenmarkers`, which "measures"
    n_values gates within `measurement_time` seconds. getData() returns an int32 array of length n_values
    (not yet measured gates are 0, like the real TimeTagger), ready() becomes True when all gates are filled.
    Counts per gate are Poisson distributed with a dark and a bright level, e.g. for a Lorentzian-free,
    but bimodal "spin readout" like signal.

For the timetagger_logic (counter, histogram, correlation, dump) the dummy provides
    _constraints            dict as the logic and the GUI read it:
                            ['corr']['channel_start'], ['corr']['channel_stop'], ['hist']['trigger_channel'],
                            ['hist']['channels'] (channels offered for the histogram), ['counter']['channels']
    counter(...)            rolling trace: the last n_values bins, newest bin last, with getDataNormalized() in counts/s
    histogram(...)          accumulating exponential decay (lifetime_ps)
    correlation(...)        accumulating antibunching dip, getDataNormalized() is g2 (1 far away, dip at 0)
    write_into_file(...)    file writer whose getTotalSize() grows with time

Example config (the options of the real TT module can stay in the config, they are accepted and ignored):

hardware:
    timetagger:
        module.Class: 'dummy.timetagger_dummy.TT'
        options:
            constraints:              # optional, merged into the defaults shown here
                corr:
                    channel_start: 1
                    channel_stop: 2
                hist:
                    trigger_channel: 5
                    channels: [1, 2, 3, 4]    # channels offered in the GUI
                counter:
                    channels: [1, 2, 3, 4]    # one checkbox and curve per channel in the GUI
            measurement_time: 2.0     # seconds until a count_between_markers measurement is ready
            mean_dark: 0.1            # mean counts per gate of the dark state
            mean_bright: 2.0          # mean counts per gate of the bright state
            bright_fraction: 0.5      # fraction of gates in the bright state
            count_rate: 5.0e4         # counts/s per channel of the counter
            hist_rate: 1.0e4          # events/s in the histogram
            lifetime_ps: 12000        # decay time of the histogram
            corr_rate: 1.0e3          # events per correlation bin and second
            antibunching_ps: 3000     # width of the g2 dip
"""

import copy
import threading
import time

import numpy as np

from qudi.core.configoption import ConfigOption
from qudi.interface.timetagger_interface import TimeTaggerInterface


def _opt(options, key, default=None):
    """ Read key from a dict-like ConfigOption. The real TT module uses False if an option is missing. """
    if isinstance(options, dict) and key in options:
        return options[key]
    return default


class _DummyCountBetweenMarkers:
    """ Stand-in for TimeTagger.CountBetweenMarkers. Gates are 'measured' linearly in time. """

    def __init__(self, n_values, measurement_time, sampler):
        self._n_values = max(int(n_values), 1)
        self._measurement_time = float(measurement_time)
        self._sampler = sampler
        self._lock = threading.Lock()
        self._running = True                 # like the real object, it starts measuring on creation
        self._elapsed = 0.0                  # accumulated measuring time
        self._t_start = time.monotonic()
        self._data = self._sampler(self._n_values)

    # -- internal --------------------------------------------------------------------------------------------
    def _elapsed_now(self):
        return self._elapsed + ((time.monotonic() - self._t_start) if self._running else 0.0)

    def _n_done(self):
        if self._measurement_time <= 0:
            return self._n_values
        return int(min(self._n_values, self._n_values * self._elapsed_now() / self._measurement_time))

    # -- TimeTagger API --------------------------------------------------------------------------------------
    def getData(self):
        with self._lock:
            out = np.zeros(self._n_values, dtype=np.int32)
            k = self._n_done()
            out[:k] = self._data[:k]
            return out

    def getIndex(self):
        return np.arange(self._n_values)

    def ready(self):
        with self._lock:
            return self._n_done() >= self._n_values

    def isRunning(self):
        return self._running

    def start(self):
        with self._lock:
            if not self._running:
                self._running = True
                self._t_start = time.monotonic()

    def stop(self):
        with self._lock:
            if self._running:
                self._elapsed = self._elapsed_now()
                self._running = False

    def clear(self):
        with self._lock:
            self._elapsed = 0.0
            self._t_start = time.monotonic()
            self._data = self._sampler(self._n_values)

    def waitUntilFinished(self, timeout=-1):
        t0 = time.monotonic()
        while not self.ready():
            if timeout is not None and timeout >= 0 and (time.monotonic() - t0) * 1000 > timeout:
                return False
            time.sleep(0.01)
        return True

    def sync(self):
        pass


class _DummyMeasurement:
    """ Generic stand-in for Histogram, Correlation, Counter, Countrate, TimeDifferences, Dump. """

    def __init__(self, rng, shape, mean=1.0, bin_width_ps=1):
        self._rng = rng
        self._shape = shape if isinstance(shape, tuple) else (shape,)
        self._mean = mean
        self._bin_width_ps = bin_width_ps

    def getData(self):
        return self._rng.poisson(self._mean, size=self._shape).astype(np.int32)

    def getIndex(self):
        return np.arange(self._shape[-1]) * self._bin_width_ps   # time of the bins in ps

    def getDataNormalized(self):
        return self.getData().astype(float)

    def ready(self):
        return True

    def isRunning(self):
        return True

    def start(self):
        pass

    def stop(self):
        pass

    def clear(self):
        pass

    def waitUntilFinished(self, timeout=-1):
        return True

    def sync(self):
        pass


class _DummyCounter(_DummyMeasurement):
    """ Stand-in for TimeTagger.Counter: the last n_values bins of all channels, the newest bin is last. """

    def __init__(self, rng, channels, bin_width_ps, n_values, rate):
        self._channels = list(channels)
        n_channels = max(len(self._channels), 1)
        super().__init__(rng, (n_channels, max(int(n_values), 1)), bin_width_ps=max(int(bin_width_ps), 1))
        self._bin_s = self._bin_width_ps * 1e-12
        self._rate = float(rate)
        self._lock = threading.Lock()
        self.clear()

    def clear(self):
        self._data = np.zeros(self._shape)
        self._t_last = time.monotonic()

    def _advance(self):
        n_new = int((time.monotonic() - self._t_last) / self._bin_s)
        if n_new <= 0:
            return
        self._t_last += n_new * self._bin_s
        n_new = min(n_new, self._shape[1])
        new = self._rng.poisson(self._rate * self._bin_s, size=(self._shape[0], n_new))
        self._data = np.concatenate([self._data[:, n_new:], new], axis=1)

    def getData(self):
        with self._lock:
            self._advance()
            return self._data.astype(np.int32)

    def getDataNormalized(self):
        """ Counts per second. """
        return self.getData() / self._bin_s


class _DummyHistogram(_DummyMeasurement):
    """ Stand-in for TimeTagger.Histogram: exponential decay that accumulates with time. """

    def __init__(self, rng, n_bins, bin_width_ps, rate, lifetime_ps):
        super().__init__(rng, (max(int(n_bins), 1),), bin_width_ps=max(int(bin_width_ps), 1))
        t = (np.arange(self._shape[0]) + 0.5) * self._bin_width_ps
        pdf = np.exp(-t / float(lifetime_ps))
        self._pdf = pdf / pdf.sum()
        self._rate = float(rate)
        self._lock = threading.Lock()
        self.clear()

    def clear(self):
        self._acc = np.zeros(self._shape)
        self._t_last = time.monotonic()

    def getData(self):
        with self._lock:
            now = time.monotonic()
            self._acc += self._rng.poisson(self._rate * (now - self._t_last) * self._pdf)
            self._t_last = now
            return self._acc.astype(np.int64)

    def getDataNormalized(self):
        return self.getData().astype(float)


class _DummyCorrelation(_DummyMeasurement):
    """ Stand-in for TimeTagger.Correlation: g2 of a single emitter (antibunching dip at zero delay). """

    def __init__(self, rng, n_bins, bin_width_ps, rate_per_bin, antibunching_ps):
        super().__init__(rng, (max(int(n_bins), 1),), bin_width_ps=max(int(bin_width_ps), 1))
        self._index = (np.arange(self._shape[0]) - self._shape[0] // 2) * self._bin_width_ps
        self._g2 = 1.0 - 0.9 * np.exp(-np.abs(self._index) / float(antibunching_ps))
        self._rate = float(rate_per_bin)
        self._lock = threading.Lock()
        self.clear()

    def clear(self):
        self._acc = np.zeros(self._shape)
        self._elapsed_events = 0.0
        self._t_last = time.monotonic()

    def getIndex(self):
        return self._index   # delay in ps, symmetric around 0

    def _advance(self):
        now = time.monotonic()
        dt = now - self._t_last
        self._acc += self._rng.poisson(self._rate * dt * self._g2)
        self._elapsed_events += self._rate * dt
        self._t_last = now

    def getData(self):
        with self._lock:
            self._advance()
            return self._acc.astype(np.int64)

    def getDataNormalized(self):
        """ g2: 1 for long delays, a dip at zero delay; the noise decreases with the measuring time. """
        with self._lock:
            self._advance()
            if self._elapsed_events <= 0:
                return np.ones(self._shape)
            return self._acc / self._elapsed_events


class _DummyFileWriter:
    """ Stand-in for TimeTagger.FileWriter. """

    def __init__(self, rate_bytes_per_s=1e6):
        self._rate = rate_bytes_per_s
        self._t0 = time.monotonic()
        self._stopped_size = None

    def getTotalSize(self):
        if self._stopped_size is not None:
            return self._stopped_size
        return int((time.monotonic() - self._t0) * self._rate)

    def stop(self):
        self._stopped_size = self.getTotalSize()


class _DummyCombiner:
    """ Stand-in for TimeTagger.Combiner (a virtual channel). """

    def __init__(self, channels):
        self.channels = channels

    def getChannel(self):
        return 100

    def getData(self):
        return np.zeros(1, dtype=np.int32)


class _DummyTagger:
    """ Stand-in for the object returned by createTimeTagger(). Setters only remember the values. """

    def __init__(self):
        self.trigger_level = {}
        self.deadtime = {}
        self.input_delay = {}
        self.test_signal = {}

    def getSerial(self):
        return 'DUMMY-0000'

    def setTriggerLevel(self, channel, level):
        self.trigger_level[channel] = level

    def setDeadtime(self, channel, deadtime):
        self.deadtime[channel] = deadtime

    def setInputDelay(self, channel, delay):
        self.input_delay[channel] = delay

    def setTestSignal(self, channel, enabled):
        self.test_signal[channel] = enabled

    def setConditionalFilter(self, *args, **kwargs):
        pass

    def reset(self):
        pass


# read by timetagger_logic (corr, hist trigger channel) and by the timetagger GUI (counter and hist channel lists)
_DEFAULT_CONSTRAINTS = {
    'corr': {'channel_start': 1, 'channel_stop': 2},
    'hist': {'trigger_channel': 5, 'channels': [1, 2, 3, 4]},
    'counter': {'channels': [1, 2, 3, 4]},
}

class TT(TimeTaggerInterface):
    # same options as the real TT module, so the config block can be swapped without editing
    _hist = ConfigOption('hist', {'click_channel': 1, 'start_channel': 5, 'binwidth': 1000, 'number_of_bins': 1000})
    _time_diff = ConfigOption('time_diff', False)
    _corr = ConfigOption('corr', {'channel_start': 1, 'channel_stop': 2, 'binwidth': 1000, 'number_of_bins': 1000})
    _combiner = ConfigOption('combiner', False)
    _counter = ConfigOption('counter', {'channels': [1, 2, 3, 4], 'bins_width': int(1e9), 'n_values': 1000})
    _constraints_cfg = ConfigOption('constraints', None)
    _test_channels = ConfigOption('test_channels', False)
    _channels_params = ConfigOption('channels_params', False)
    _count_between_markers = ConfigOption('count_between_markers', False)

    # options of the dummy
    _measurement_time = ConfigOption('measurement_time', 2.0)
    _mean_dark = ConfigOption('mean_dark', 0.1)
    _mean_bright = ConfigOption('mean_bright', 2.0)
    _bright_fraction = ConfigOption('bright_fraction', 0.5)
    _count_rate = ConfigOption('count_rate', 5.0e4)
    _hist_rate = ConfigOption('hist_rate', 1.0e4)
    _lifetime_ps = ConfigOption('lifetime_ps', 12000)
    _corr_rate = ConfigOption('corr_rate', 1.0e3)
    _antibunching_ps = ConfigOption('antibunching_ps', 3000)
    _seed = ConfigOption('seed', None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sample_rate = 50
        chan_alphabet = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight']
        self.channel_codes = dict(zip(chan_alphabet, list(range(1, 9, 1))))
        self.tagger = None
        self.gated_counter_countbetweenmarkers = None

    @property
    def _constraints(self):
        """ Read by the timetagger_logic: channels of the correlation and the histogram (and of the counter).
        The defaults are updated with the 'constraints' option of the config. """
        constraints = copy.deepcopy(_DEFAULT_CONSTRAINTS)
        for key, value in (self._constraints_cfg or {}).items():
            if isinstance(value, dict):
                constraints.setdefault(key, {}).update(value)
            else:
                constraints[key] = value
        return constraints

    # -- qudi module -----------------------------------------------------------------------------------------
    def on_activate(self):
        self._rng = np.random.default_rng(self._seed)
        self.setup_TT()
        self.tagger.setTriggerLevel(1, 0.08)
        self.tagger.setTriggerLevel(2, 0.08)
        self.tagger.setDeadtime(1, 70000)
        self.log.warning('Using the DUMMY TimeTagger: all counts are simulated.')

    def on_deactivate(self):
        if self.gated_counter_countbetweenmarkers is not None:
            self.gated_counter_countbetweenmarkers.stop()
        self.gated_counter_countbetweenmarkers = None
        self.tagger = None

    def setup_TT(self):
        self.tagger = _DummyTagger()
        for channel in (self._test_channels or []):
            self.tagger.setTestSignal(channel, True)
        channels = _opt(self._combiner, 'channels', [])
        self._combined_channels = self.combiner(channels)

    def restart_timetagger(self):
        """ The logic calls this if setting up a counter timed out. Here it just makes a fresh dummy tagger. """
        self.setup_TT()

    # -- simulated signal ------------------------------------------------------------------------------------
    def _sample_gates(self, n):
        """ Counts per gate: Poisson with a dark or bright mean level, chosen per gate. """
        bright = self._rng.random(n) < self._bright_fraction
        mean = np.where(bright, self._mean_bright, self._mean_dark)
        return self._rng.poisson(mean).astype(np.int32)

    # -- TimeTagger API used by the logic --------------------------------------------------------------------
    def count_between_markers(self, n_values=1, **kwargs):
        self.gated_counter_countbetweenmarkers = _DummyCountBetweenMarkers(
            n_values=n_values,
            measurement_time=self._measurement_time,
            sampler=self._sample_gates,
        )

    def histogram(self, **kwargs):
        n_bins = int(kwargs.get('number_of_bins', _opt(self._hist, 'number_of_bins', 1000)))
        bin_width_ps = int(kwargs.get('bin_width', kwargs.get('binwidth', _opt(self._hist, 'binwidth', 1000))))
        return _DummyHistogram(self._rng, n_bins, bin_width_ps, self._hist_rate, self._lifetime_ps)

    def correlation(self, **kwargs):
        n_bins = int(kwargs.get('number_of_bins', _opt(self._corr, 'number_of_bins', 1000)))
        bin_width_ps = int(kwargs.get('bin_width', kwargs.get('binwidth', _opt(self._corr, 'binwidth', 1000))))
        return _DummyCorrelation(self._rng, n_bins, bin_width_ps, self._corr_rate, self._antibunching_ps)

    def delay_channel(self, channel, delay):
        self.tagger.setInputDelay(channel, delay)

    def dump(self, dumpPath, filtered_channels=None):
        return _DummyMeasurement(self._rng, 1, mean=0.0)

    def countrate(self, channels=None):
        if channels is None:
            channels = _opt(self._counter, 'channels', [1])
        return _DummyMeasurement(self._rng, len(channels), mean=1000.0)

    def counter(self, **kwargs):
        channels = kwargs.get('channels', _opt(self._counter, 'channels', [1]))
        n_values = int(kwargs.get('n_values', _opt(self._counter, 'n_values', 1)))
        bin_width_ps = int(kwargs.get('bin_width', kwargs.get('bins_width', _opt(self._counter, 'bins_width', 1))))
        return _DummyCounter(self._rng, channels, bin_width_ps, n_values, self._count_rate)

    def combiner(self, channels):
        return _DummyCombiner(channels)

    def time_differences(self, **kwargs):
        n_bins = int(_opt(self._time_diff, 'n_bins', 1000))
        n_hist = int(_opt(self._time_diff, 'n_histograms', 1))
        return _DummyMeasurement(self._rng, (n_hist, n_bins), mean=5.0)

    def write_into_file(self, filename, channels):
        return _DummyFileWriter()