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

seq_name = os.path.basename(__file__).split('.')[0]
nuclear = sch.create_nuclear(__file__)
with open(os.path.abspath(__file__).split('.')[0] + ".py", 'r') as f:
    meas_code = f.read()

__TAU_HALF__ = 2 * 192 / 12e3
__SAMPLE_FREQUENCY__ = 12e3  # e.__SAMPLE_FREQUENCY__


def init_state_drive(state, freqs):
    '''
    State could be "p(m)3(1)2+(-,n)", example m32+, or p32-, p32n
    '''
    mw_init32L1 = 0
    mw_init32L2 = 0
    mw_init32R1 = 0
    mw_init32R2 = 0
    ## MW drive
    if 'p' in state:
        mw_init32L1 = 0.15
        mw_init32L2 = 0.15
    elif 'm' in state:
        mw_init32R1 = 0.1
        mw_init32R2 = 0.1
    pd2g1 = {
        'type': 'sine',
        'phases': [0],
        'amplitudes': [
            mw_init32L1,
            mw_init32L2,
            mw_init32R1,
            mw_init32R2],
        'frequencies': freqs
    }

    return pd2g1


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
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega_cnot']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega_cnot']).pi)
            elif 'p' in _I_['state']:
                transition = 'R2' # use R2, such that after init, system is in state 2 --> SSR1 (with L1+R1) is more likely to be dark --> Init successful
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega_cnot']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega_cnot']).pi)

            rf_freq = {'m32': 11.942, 'm12': 3.224, 'p12': 2.41112, 'p32': 3.699}[_I_['state']]
            rf_dur = {'m32': 19.586, 'm12': 63.055, 'p12': 66.66, 'p32': 49.09}[_I_['state']]

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

            def electron_init(st=None ,t=None):
                state = _I_['state'] if st is None else st
                segment_length = 5
                it = _I_['init_time'] if t is None else t
                loops, correction_mus = shared.calculate_loop_count(_I_['init_time'], segment_length)
                mcas.start_new_segment(name='init', loop_count=loops)
                mcas.asc(
                    A1='32' in state,
                    A2='12' in state,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(segment_length),
                    name='resonant_init',
                    pd2g1=init_state_drive(state, [trans['L1'], trans['L2'], trans['R1'], trans['R2']]),
                )
                mcas.start_new_segment(name='sequence', loop_count=1)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='Init Decay')

            def rf_pulse(freq, amp=None, dur=None, phase=0):
                amp = _I_['rf_amp'] if amp is None else amp
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

        # Nuclear Init
            sna.repump(mcas, dur=20)
            #sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'], trans['L2']], [trans['R1'], trans['R2']], max_amp = 0.15)
            electron_init()
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(rf_freq)

            ampL = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega_ssr']).amp
            ampR = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega_ssr']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(
                self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega_ssr']).pi)
        # SSR 1
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[[trans['L1'], trans['R1']]],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read1']),
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
                    repetitions=int(_I_['n_ssr1'])
                    )
        
        # Electron init
            electron_init(st = _I_['state'], t = _I_['init_time']) # Reinit the electon state.

            mcas.start_new_segment('ENDOR', loop_count=1)

        # Hadamard
            rf_pulse(rf_freq, dur=rf_dur / 2)  #

        # First Phase
            mcas.start_new_segment(name='FirstPhaseMeasurement', loop_count=1)
            cnot(amp, pi_dur, trans['R1'])
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']))
            cnot(amp, pi_dur, trans['R2'])
        # Bath flip
            rf_pulse(freq=_I_['rf_freq_bath'], amp = _I_['rf_amp_bath'], dur=_I_['rf_dur_bath'])
        # Second Phase
            mcas.start_new_segment(name='SecondPhaseMeasurement', loop_count=1)
            cnot(amp, pi_dur, trans['R1'])
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']))
            cnot(amp, pi_dur, trans['R2'])
        # Hadamard
            a = -2.22709 # for rf_dur_bath = 250 and variable tau
            o = 350.0859 # for rf_dur_bath = 250 and variable tau
            phase = a*E.round_length_mus_to_x_multiple_ps(_I_['tau'])+o
            #a = -2.5160110 # for tau = 18.1626 and variable correlation time
            #o = 117.3167832 # for tau = 18.1626 and variable correlation time
            
            #phase = a*E.round_length_mus_to_x_multiple_ps(_I_['rf_dur_bath'])+o
            #phase = 0
            #rf_pulse(rf_freq, dur=rf_dur / 2, phase=_I_['phase'] + _I_['readout_phase'])
            rf_pulse(rf_freq, dur=rf_dur / 2, phase= phase + _I_['phase'] + _I_['readout_phase'])

        # SSR 2
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[[trans['L1'], trans['R1']]],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read2']),
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
                    repetitions=int(_I_['n_ssr2'])
                    )
            # sna.ssr(mcas=mcas, queue=self.queue,
            #         frequencies=[[trans['L1'], trans['R1']],[trans['L2'], trans['R2']]],
            #         wait_dur=_I_['wait_dur'],
            #         robust=False,
            #         nuc='29Si8_A2',
            #         mixer_deg=-90,
            #         eom_ampl=0.0,
            #         step_idx=1,
            #         laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read2']),
            #         length_mus_mw=pi_durL,
            #         amplitudes=[ampL, ampR],
            #         repetitions=int(_I_['n_ssr2'])
            #         )
        # CRC
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
        ['init', '<', 4, 0, 0, 1], #SSR1
        ['result', '>', 12,0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
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
    nuclear.do_confocal_A1A2_refocus = True
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.do_repump = False
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 180 # 3 mins?
    nuclear.confocal_refocus_interval = 300  # seconds
    nuclear.odmr_refocus_interval = 6000

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    Tesla=0.2089
    c_bath = 10.705*Tesla
    si_bath = 8.46*Tesla
    #tau = []
    #for i in range(30):
    #    tau.append(np.random.random()*10)
    #plt.plot(np.sort(tau))
    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('A2_power', [20]),
            ('t_read1', [1.024*3]),
            ('t_read2', [1.024*3]),
            ('wait_dur', [0.512]),
            #('phase', np.arange(0,540,45)),
            ('phase', [0.0]), #222 for 30µs tau; 193 for 15µs tau.
            ('init_time', [75.]),
            ('n_ssr2', [750]),
            ('n_ssr1', [500]),
            ('omega_cnot', [0.8]),
            ('omega_ssr', [0.8]),
            ('tau', [2.4387]),
            ('state', ['p12']),
            ('rf_amp', [1.0]),
            ('rf_dur_bath', [209.0]),
            ('rf_amp_bath', [1.0]),
            #('rf_freq_bath', [1.51,1.521645]),
            ('rf_freq_bath', np.arange(1.5176,1.5275,0.0007)),
            ('readout_phase', [0.,180.])
        )
    )
    nuclear.number_of_simultaneous_measurements = 2

def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 15 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    nuclear.pld.fit_function='cosine'
    settings()
    print('run_fun started')
    nuclear.run(abort)
