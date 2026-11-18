# -*- coding: utf-8 -*-
"""
qudi hardware module for the Swabian PulseStreamer that acts as hardware-triggered slave of the M8190A.

Port of ``PulseStreamer`` + ``PulseStreamerPGProxy`` from the legacy ``hardware.py``. Pulses are described as
``(time_ns, ['A1', 'repump'], analog0_volt, analog1_volt)``.

Differences to the legacy classes:
  * The ip address is a config option. (The legacy constructor accepted ``ip`` but ignored it and always
    connected to 129.69.46.36.)
  * The marker-name -> output-number map is not read from the global settings. The MCAS logic hands it over with
    ``set_channel_map`` (derived from ``marker_alias``); alternatively give ``channel_map`` in the config.
  * The clock output channel(s) (legacy: ``setSquareWave125MHz([4])``) and the analog voltage are config options.
  * ``unwrap_sequence``/``missing_smpl`` moved to ``logic/mcas/sequence.py`` (they need the AWG sample granularity).

Example config:

    pulsestreamer:
        module.Class: 'swabian.pulse_streamer_mcas.PulseStreamerMcas'
        ip: '129.69.46.36'
        clock_channels: [4]
        analog_volt: 1.0
"""
import base64
import struct

from qudi.core.configoption import ConfigOption
from qudi.interface.mcas_pulsestreamer_interface import McasPulseStreamerInterface


class PulseStreamerMcas(McasPulseStreamerInterface):
    """Pulse streamer, controlled over the pulsestreamer package and its JSON-RPC interface."""

    _ip = ConfigOption('ip', missing='error')
    _clock_channels = ConfigOption('clock_channels', default=[4], missing='nothing')
    _analog_volt_cfg = ConfigOption('analog_volt', default=1, missing='nothing')  # e.g. A2 AOM voltage
    _channel_map_cfg = ConfigOption('channel_map', default=None, missing='nothing')
    _json_rpc_port = ConfigOption('json_rpc_port', default=8050, missing='nothing')

    def _connect(self):
        """Open the connection to the device. Returns (pulsestreamer.PulseStreamer, json-rpc proxy).
        Overridden by the dummy module; the imports are local so that the dummy works without these packages."""
        import pulsestreamer
        from tinyrpc import RPCClient
        from tinyrpc.protocols.jsonrpc import JSONRPCProtocol
        from tinyrpc.transports.http import HttpPostClientTransport

        ps = pulsestreamer.PulseStreamer(self._ip)
        if self._clock_channels:
            ps.setSquareWave125MHz(list(self._clock_channels))
        url = 'http://{}:{}/json-rpc'.format(self._ip, self._json_rpc_port)
        client = RPCClient(JSONRPCProtocol(), HttpPostClientTransport(url))
        return ps, client.get_proxy()

    def on_activate(self):
        self.ps, self.proxy = self._connect()
        self.channel_map = dict(self._channel_map_cfg) if self._channel_map_cfg else {}
        self.getUnderflow()

        self._loops = None
        self._triggered = None
        self._sequence = None
        self.t_prepolarize = None
        self.analog_volt = self._analog_volt_cfg

    def on_deactivate(self):
        try:
            self.Night()
        except Exception as err:
            self.log.warning('Could not switch pulse streamer off on deactivation: {}'.format(err))

    def set_channel_map(self, channel_map):
        self.channel_map = dict(channel_map)

    # --- low level (legacy PulseStreamer) --------------------------------------------------------------------------
    def stream(self, seq, n_runs=0, initial=(0, [], 0, 0), final=(0, [], 0, 0), underflow=(0, [], 0, 0), start='IMMEDIATE'):
        initial = (initial[0], initial[1], self.analog_volt, initial[3])
        final = (final[0], final[1], self.analog_volt, final[3])
        underflow = (underflow[0], underflow[1], self.analog_volt, underflow[3])

        initial = self.convert_pulse(initial)
        final = self.convert_pulse(final)
        underflow = self.convert_pulse(underflow)
        s = self.enc(seq).decode("utf-8")

        self.proxy.stream(s, n_runs, initial, final, underflow, start)

    def startNow(self):
        self.proxy.startNow()

    def constant(self, pulse=(0, [], 0, 0)):
        pulse = self.convert_pulse(pulse)
        self.proxy.constant(pulse)

    def enc(self, seq):
        """Convert a human readable python sequence to a base64 encoded string."""
        s = b''
        for pulse in seq:
            s += struct.pack('>IBhh', *self.convert_pulse(pulse))
        return base64.b64encode(s)

    def convert_pulse(self, pulse):
        t, chans, a0, a1 = pulse
        return (t, self.chans_to_mask(chans), int(0x7fff * a0), int(0x7fff * a1))

    def chans_to_mask(self, chans):
        mask = 0
        for chan in chans:
            mask |= 1 << self.channel_map[chan]
        return mask

    def getUnderflow(self):
        return self.proxy.getUnderflow()

    # --- sequence level (legacy PulseStreamerPGProxy) --------------------------------------------------------------
    def setSequence(self, sequence, loops=-1, triggered=False, padding=[], run=True):
        if run == True:
            start = 'IMMEDIATE'
        elif run == False:
            start = 'SOFTWARE'
        if triggered == True:
            start = 'HARDWARE'

        self._loops = loops
        self._triggered = triggered
        self._sequence = sequence

        self.stream(self.convert_sequence(sequence), loops, final=(100, [], 0, 0), start=start)

    def run(self, loops=-1, triggered=False):
        if loops != self._loops or triggered != self._triggered:
            if self._sequence is None:
                raise RuntimeError('Sequence not set.')
            else:
                self.setSequence(self._sequence, loops, triggered)
        else:
            self.startNow()

    def convert_sequence(self, sequence):
        """Convert a pg style sequence to ps style for wide field use (incl. ccd)."""
        return [(int(t), channels, self.analog_volt, 0) for channels, t in sequence]

    def setContinuous(self, channels=[]):
        self.constant(pulse=(0, channels, self.analog_volt, 0))

    def checkUnderflow(self):
        return self.getUnderflow()

    def Night(self):
        self.constant()

    def Light(self):
        self.constant(pulse=(0, ['repump'], self.analog_volt, 0))

    Sequence = setSequence
    High = setContinuous
    Continuous = setContinuous
