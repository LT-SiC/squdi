# coding=utf-8
import datetime
import numpy as np
import os
import importlib
import notebooks.UserScripts.helpers.sequence_creation_helpers as sch;

importlib.reload(sch)
import notebooks.UserScripts.helpers.shared as shared
from hardware.Keysight_AWG_M8190.pym8190a import MultiChSeq as MultiChSeq
import notebooks.UserScripts.helpers.snippets_awg as sna

importlib.reload(sna)
importlib.reload(shared)
# importlib.reload(MultiChSeq)
import notebooks.UserScripts.helpers.shared as ush;

importlib.reload(ush)
from logic.qudip_enhanced import *
import hardware.Keysight_AWG_M8190.elements as E
from collections import OrderedDict
from PyQt5 import QtTest

seq_name = os.path.basename(__file__).split('.')[0]
nuclear = sch.create_nuclear(__file__)
with open(os.path.abspath(__file__).split('.')[0] + ".py", 'r') as f:
    meas_code = f.read()

__TAU_HALF__ = 2 * 192 / 12e3
__SAMPLE_FREQUENCY__ = 12e3  # e.__SAMPLE_FREQUENCY__


def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name=None):
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]

        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ###
            if 'm' in _I_['state']:
                transition = 'L2'
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=1.4).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=1.4).pi)
            elif 'p' in _I_['state']:
                transition = 'R2' # use R2, such that after init, system is in state 2 --> SSR1 (with L1+R1) is more likely to be dark --> Init successful
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=1.4).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=1.4).pi)

            rf_freq = {'m32': 8.99166,  'm12':4.169582, 'p12': 0.649641, 'p32': 5.465889}[_I_['state']]
            rf_dur = self.queue.tt.rp('29si5 ms'+_I_['state'].replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5'), amp = _I_['rf_amp']).pi
            rf_amp = self.queue.tt.rp('29si5 ms'+_I_['state'].replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5'), amp = _I_['rf_amp']).amp
            
            # def electron rabi
            def cnot(amp, dur, freq):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    amplitudes=[amp],
                    frequencies=[freq],
                    mixer_deg=[-90]
                )

            def rf_pulse(freq, amp=None, dur=None, phase=0):
                amp = rf_amp if amp is None else amp
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1', gateRF = True)
                if dur is None:
                    dur = rf_dur
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    gateRF = True,
                    pd2g2={"type": "sine", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
                           "phase_type_offset": 'absolute'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)


            def erabi(freq, length, amp, phase=0.0):
                sna.electron_rabi(mcas,
                                  name='electron rabi',
                                  length_mus=length,
                                  amplitudes=[amp]*len(freq),
                                  frequencies=freq,
                                  phases=np.rad2deg(phase),
                                  new_segment=False,
                                  gateMW=True,
                                  mixer_deg=-90,
                                  )

            def waveform(seq):
                mcas.start_new_segment('waveform')
                #sna.polarize(mcas, new_segment=False)
                mw = seq.times_fields_aphi('mw')
                wait = seq.times_fields_aphi('wait')
                for step in seq.sequence_steps:
                    idx = int(step[1]) - 1
                    if step[0] == 'mw':
                        erabi(freq=freq,
                              length=mw[idx, 0],
                              amp=self.queue.tt.rp('e_rabi_ou350deg-90-R', period=1 / mw[idx, 1]).amp,
                              phase=mw[idx, 2])
                    # elif step[0] == 'wait':
                    #     mcas.asc(length_mus=wait[idx, 0])
                    elif step[0] == 'wait':
                        if wait[idx, 0] > 0.264:
                            mcas.asc(length_mus=wait[idx, 0]-0.256)
                            mcas.asc(length_mus=0.256, gateMW = True)
                        else:
                            mcas.asc(length_mus=wait[idx, 0], gateMW = True)


            #pi2_time=E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-R', period=_I_['period']).pi / 2)
            rabi_period = _I_['rabi_period']
            freq = [trans['R2']] #lets try only one peak, so that we have a better fidelity, since nuc spin is initialised ...########  # pi3d.tt.mfl({'14N': [+1]}, ms_trans=_I_['ms'])

            def dd():
                pi2x = sc.Rabi(t_rabi=0.25 * rabi_period, omega=1 / rabi_period, phase=0.0, control_field='mw')
                pi2_2 = sc.Rabi(t_rabi=0.25 * rabi_period, omega=1 / rabi_period, phase=_I_['phase_pi2_2'],
                                control_field='mw')

                dd = sc.DD(dd_type='{}_{}'.format(_I_['n_rep_dd'], _I_['ddt']), rabi_period=_I_['rabi_period'],
                           total_tau=_I_['total_tau'])
                seq = sc.Concatenated([pi2x, dd, pi2_2], controls=['mw', 'wait'])
                waveform(seq)

            # freqs = [freq]*2#[pi3d.tt.mfl({'14N': [+1]}, ms_trans=_I_['ms']),
            # pi3d.tt.mfl({'14N': [0]}, ms_trans=_I_['ms'])]

            sna.repump(mcas, dur = 10)
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(rf_freq)

            ### READOUT ###
            ampL = self.queue.tt.rp('e_rabi_ou350deg-90-L', period=_I_['period']).amp
            ampR = self.queue.tt.rp('e_rabi_ou350deg-90-R', period=_I_['period']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(
                self.queue.tt.rp('e_rabi_ou350deg-90-L', period=_I_['period']).pi)


            #SSR1 # init nuc
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[[trans['L1'], trans['R1']]],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
                    repetitions=int(_I_['n_ssr1'])
                    )


            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            

            mcas.start_new_segment('DDDDDDDDD', loop_count=1)
            mcas.asc(length_mus=0.256, gateMW=True)
            #if _I_['applied_voltage'] == 0:
            #    pass

            dd()

            mcas.asc(length_mus=5.024)
            # CNOT nuclear. #?
            rf_pulse(rf_freq)

            #double sided SSR2 of nuc.
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[[trans['L1'], trans['R1']]],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
                    repetitions=int(_I_['n_ssr2'])
                    )
            #CRC.
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[500],
                    wait_dur=0.0,
                    robust=False,
                    nuc='charge_state',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=2,
                    )

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)
        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
         ['init', '<', 6, 0, 0, 1], #SSR1
        ['result', '>', 6, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        #['result', '>', 0, 6, 0, 2], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 8, 1, 0, 1],   #CRC
        # ['init', '>', 5, 1, 0, 1],
    ]
    # what does each entry do?
    # ana_seq[0]: ? 'result' or 'init', init - for postselection
    # ana_seq[1]: ? > or <
    # ana_seq[2]: "threshold"
    # ana_seq[3]: "nlp_per_point", number of laser pulses per point. N of repetitions.
    # ana_seq[4]: set to 100 --> no counts measured; set to 7 --> counts can be measured; --> delta - exclusion zone. n > threshold +delta, or n< threhold - delta.
    # ana_seq[5]: "number of results" --> ssr = cnot1 + laser1 + cnot2 + laser2, -> n=2, etc.. laser2-laser1,  histograms are centered around 0,
    sch.settings(
        nuclear=nuclear,
        ret_mcas=ret_ret_mcas(pdc),
        analyze_sequence=ana_seq,
        pdc=pdc,
        meas_code=meas_code
    )

    nuclear.x_axis_title = 'Freq [MHz]'
    # nuclear.analyze_type = 'consecutive'
    nuclear.analyze_type = 'average'  # experimental feature for the fast
    nuclear.save_smartly = False
    # PLE refocus
    nuclear.do_ple_refocusA1 = False  # not used
    nuclear.do_ple_refocusA2 = True

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    # confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = False
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.do_repump = False
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 30
    nuclear.confocal_refocus_interval = 300  # seconds
    nuclear.odmr_refocus_interval = 6000

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    lst = np.logspace(1, 4, 10).tolist()
    # lst1 = lst[0::2]
    # lst2 = lst[1::2][::1]
    ordered_list = lst
    # while len(lst2)>0:
    #    ordered_list.append(lst1.pop())
    #   ordered_list.append(lst2.pop())
    nuclear.parameters = OrderedDict(
        (
            #('applied_voltage', np.arange(0,-29,-2)),
            # ('sweeps', range(2)),
            ('sweeps', range(20)),
            ('A2_power', [20]),
            ('period', [1.024]),
            ('rabi_period', [1/1.4]),
            ('t_read', [1.024 * 3]),
            ('init_time', [50]),
            ('state', ['p32']),
            ('rf_amp', [0.9]),
            ('init_time', [60]),
            ('n_ssr2', [1000]),
            ('n_ssr1', [1000]),
            ('n_rep_dd', [1]),
            #('n_rep_dd', [1, 4, 8, 16]),
            #('ddt', ['xy4','xy8','xy16']),
            ('ddt', ['fid', 'hahn', 'xy4', 'xy16', 'kdd4', 'kdd16']),
            # ('total_tau', np.hstack([[0.0], np.arange(0.016, 0.064,0.064)])),
            ('total_tau', np.hstack([[0.0], np.arange(0.016, 2000, 50)])),
            ('phase_pi2_2', [0.0, np.pi]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 2


def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 30 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)
    #curr_sweep = 1
    #while not hasattr(nuclear, '_state'):
    #    QtTest.QTest.qSleep(100)
    #while nuclear.state == 'run':
    #    print(curr_sweep)
 #
 #       QtTest.QTest.qSleep(1000)
 #       if nuclear.current_iterator_df['sweeps'][0] == curr_sweep%2:
 #           print("forced PLE refocus after Sweep")
 #           nuclear.ple_refocus_interval = 0
 #           curr_sweep += 1
 #           QtTest.QTest.qSleep(10000)
 #       else:
 #           nuclear.ple_refocus_interval = 300
        