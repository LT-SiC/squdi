# -*- coding: utf-8 -*-

"""
Qudi interface of an analog output with a trigger (pixel clock) for an external counter.

The analog output can be set to a voltage (software timed, with an optional ramp) and it can play a waveform,
hardware timed: the i-th sample of the waveform is output with the i-th rising edge of a pixel clock. The pixel clock
is also made available at a trigger output (n_samples + 1 pulses, the first one outputs sample 0), so that an external
counter (e.g. the Time Tagger with CountBetweenMarkers) counts the photons between two edges, i.e. per pixel.
"""

from abc import abstractmethod
from qudi.core.module import Base


class TriggeredAnalogOutputConstraints:
    """ channel_names: names of the analog output channels, e.g. ['x', 'y', 'z']
        voltage_ranges: {channel name: (min V, max V)}
        max_sample_rate: maximum pixel clock frequency in Hz """

    def __init__(self, channel_names, voltage_ranges, max_sample_rate):
        self.channel_names = list(channel_names)
        self.voltage_ranges = {ch: (float(r[0]), float(r[1])) for ch, r in voltage_ranges.items()}
        self.max_sample_rate = float(max_sample_rate)


class TriggeredAnalogOutputInterface(Base):
    """ Analog output with pixel clock output. """

    @abstractmethod
    def get_constraints(self):
        """ @return TriggeredAnalogOutputConstraints """
        pass

    @abstractmethod
    def get_voltages(self):
        """ Voltages that the analog output channels are set to (the last written values).

        @return dict: {channel name: voltage}
        """
        pass

    @abstractmethod
    def set_voltages(self, voltages, ramp_time=0.0):
        """ Set channels to a voltage, software timed. Blocks until the voltages are reached.

        @param dict voltages: {channel name: voltage}, channels that are not given keep their voltage
        @param float ramp_time: duration in s of a linear ramp from the present to the new voltages (0: jump)
        """
        pass

    @abstractmethod
    def start_waveform(self, waveforms, sample_rate):
        """ Start the hardware timed output of waveforms and the pixel clock. Returns immediately.

        Sample i is output with rising edge i of the pixel clock. The pixel clock has len(waveform) + 1 pulses and is
        also output at the trigger terminal. Make sure that an external counter is armed before this is called.

        @param dict waveforms: {channel name: 1D array of voltages}, all of the same length; channels that are not
                               given keep their voltage
        @param float sample_rate: frequency of the pixel clock in Hz
        """
        pass

    @abstractmethod
    def is_waveform_running(self):
        """ @return bool: a waveform is being output """
        pass

    @abstractmethod
    def wait_until_waveform_done(self, timeout):
        """ Wait until the waveform and the pixel clock are finished and clean up.

        @param float timeout: seconds
        @return bool: True if it finished (or was stopped), False on timeout
        """
        pass

    @abstractmethod
    def stop_waveform(self):
        """ Abort a running waveform and clean up. The channels keep the last output voltage. """
        pass

    @abstractmethod
    def reset(self):
        """ Reset the hardware. """
        pass
