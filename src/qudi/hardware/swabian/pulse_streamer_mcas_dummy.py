# -*- coding: utf-8 -*-
"""
Dummy for the Swabian PulseStreamer: same qudi module API as ``pulse_streamer_mcas.PulseStreamerMcas``, no device,
no ``pulsestreamer`` / ``tinyrpc`` packages needed.

All module-level logic (channel map, ``setSequence``, ``constant``, ``Night``, ``convert_pulse`` ...) is the real code;
only the JSON-RPC connection is replaced by a recorder. Everything that would have been sent to the device can be
inspected:

    ps.proxy.calls            list of (method name, args) of every JSON-RPC call
    ps.last_stream            last uploaded sequence, decoded: {'sequence': [(t_ns, [outputs], analog0_V, analog1_V)], 'n_runs',
                              'start', ...}
    ps.last_stream_named()    same with marker names instead of output numbers
    ps.last_constant          last pulse sent with ``constant`` (decoded like above)

Example config:

    pulsestreamer:
        module.Class: 'swabian.pulse_streamer_mcas_dummy.PulseStreamerMcasDummy'
        options:
            analog_volt: 1.0
"""
import base64
import struct

from qudi.core.configoption import ConfigOption

from .pulse_streamer_mcas import PulseStreamerMcas

_PULSE = struct.Struct('>IBhh')  # same layout as PulseStreamerMcas.enc


def _decode_pulse(t, mask, a0, a1):
    outputs = [bit for bit in range(8) if mask & (1 << bit)]
    return (t, outputs, a0 / 0x7fff, a1 / 0x7fff)


class _DummyPulseStreamerDevice:
    def __init__(self):
        self.clock = None

    def setSquareWave125MHz(self, channels):
        self.clock = channels


class _DummyProxy:
    """Records the JSON-RPC calls the module makes."""

    def __init__(self):
        self.calls = []
        self.last_stream = None
        self.last_constant = None
        self.trigger_mode = None

    def stream(self, s, n_runs, initial, final, underflow, start):
        raw = base64.b64decode(s)
        if len(raw) % _PULSE.size:
            raise ValueError('Encoded sequence has {} bytes, not a multiple of {}'.format(len(raw), _PULSE.size))
        pulses = [_decode_pulse(*_PULSE.unpack_from(raw, i)) for i in range(0, len(raw), _PULSE.size)]
        self.last_stream = dict(sequence=pulses, n_runs=n_runs, start=start,
                                initial=_decode_pulse(*initial), final=_decode_pulse(*final),
                                underflow=_decode_pulse(*underflow))
        self.calls.append(('stream', (s, n_runs, initial, final, underflow, start)))

    def constant(self, pulse):
        self.last_constant = _decode_pulse(*pulse)
        self.calls.append(('constant', (pulse,)))

    def setTrigger(self, mode):
        self.trigger_mode = mode
        self.calls.append(('setTrigger', (mode,)))

    def getUnderflow(self):
        self.calls.append(('getUnderflow', ()))
        return False

    def __getattr__(self, name):
        # any other JSON-RPC method: record it (the real proxy would forward it to the device)
        if name.startswith('__'):
            raise AttributeError(name)

        def call(*args):
            self.calls.append((name, args))
            return 0
        return call


class PulseStreamerMcasDummy(PulseStreamerMcas):
    """PulseStreamer module without device. Use instead of ``swabian.pulse_streamer_mcas.PulseStreamerMcas``."""

    _ip = ConfigOption('ip', default='dummy', missing='nothing')  # not required for the dummy

    def _connect(self):
        return _DummyPulseStreamerDevice(), _DummyProxy()

    def on_activate(self):
        super().on_activate()
        self.log.warning('Dummy PulseStreamer active: no device is accessed.')

    @property
    def last_stream(self):
        return self.proxy.last_stream

    @property
    def last_constant(self):
        return self.proxy.last_constant

    def _names(self, outputs):
        names = {}
        for name, out in self.channel_map.items():
            names.setdefault(out, [])
            if name not in names[out]:
                names[out].append(name)
        return ['/'.join(names.get(o, ['out{}'.format(o)])) for o in outputs]

    def last_stream_named(self):
        """Last uploaded sequence with marker names: [(t_ns, [names], analog0_V, analog1_V), ...]."""
        stream = self.proxy.last_stream
        if stream is None:
            return None
        return [(t, self._names(outs), a0, a1) for t, outs, a0, a1 in stream['sequence']]
