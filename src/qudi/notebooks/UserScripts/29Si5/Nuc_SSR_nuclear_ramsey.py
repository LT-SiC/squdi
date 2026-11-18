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

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        tt = self.queue.tt
        tesla = (tt.mw_mixing_frequency_L+tt.mw_mixing_frequency_R)/(2*28031.6)
        c_bath = tt.c_bath
        si_bath = tt.si_bath
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = tt.mfl(td={tt.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]

        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ###
            trans_idx = _I_['init_nuc_state']
            if '-' in _I_['state']:
                transition = 'L'+trans_idx
                
            elif '+' in _I_['state']:
                transition = 'R'+trans_idx
                
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(_I_['state']) #FIXME
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition) #FIXME

            # def electron rabi
            def cnot(amp, dur, freq,phase=-90):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur,1),
                    amplitudes=[amp],
                    frequencies=[freq],
                    mixer_deg=[phase],
                    pulseshape='sinehermite'
                )

            def rf_pulse(freq, amp=None, dur=None, phase=0):
                amp = si1_amp if amp is None else amp
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1', gateRF = True)
                if dur is None:
                    dur = si1_pi
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur,1),
                    name='nuc',
                    gateRF = True,
                    pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
                           "phase_offset_type": 'coherent'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)

        ### SEQUENCE STARTS HERE ###
        # Repump
            sna.repump(mcas, dur = 30)
        # Init nuclear via CNOT
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .04)
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(si1_freq)
        # Confirm initialized nuclear spin via SSR
            if trans_idx == '1':
                ssr_freqs=[trans['L2'], trans['R2']]
                read_idx = '2'
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                read_idx = '1'
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(read_idx)
            
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read'],8),
                    length_mus_mw=pi_dur_read,
                    amplitudes=[L_amp_read, R_amp_read],
                    repetitions=int(_I_['n_ssr1'])
                    )

        # Electron init
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = _I_['init_amp'])
        
        # Pi/2
            mcas.start_new_segment('Rabi', loop_count=1)
            rf_pulse(si1_freq+_I_['freq'], amp = si1_amp, dur=si1_pi2)
        # FID
            segment_length = E.round_length_mus_to_x_multiple_ps(500, 64)
            lc, correction_mus = shared.calculate_loop_count(_I_['tau_ramsey'], segment_length)
            #lc = np.around((_I_['tau_ramsey'] / segment_length)).astype(int)
            A1_val1 = False
            A2_val1 = False
            A1_val2 = False
            A2_val2 = False
            laser = False
            if _I_['laser'] == 'dark':
                if '32' in _I_['state']:
                    A1_val1 = True
                    A1_val2 = True
                else:
                    A2_val1 = True
                    A2_val2 = True
            if _I_['laser'] == 'bright':
                if '32' in _I_['state']:
                    A2_val1 = True
                    A1_val2 = True
                else:
                    A1_val1 = True
                    A2_val2 = True
            if A1_val1 or A1_val2 or A2_val1 or A2_val2:
                laser = True
            segment_length= 2*_I_['t_read']+ 2*pi_dur
            loops, correction_mus = shared.calculate_loop_count(_I_['tau_ramsey']-20, segment_length) # remove 20 µs which are added at the end, to have at least a few µs of init in case of bright state
            if loops != 0:
                mcas.start_new_segment(name='tau_ramsey', loop_count=loops)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['t_read']), A1 = A1_val1, A2 = A2_val1, laser = laser,
                         pd2g1={"type": "sine", "frequencies": [trans['C2']], "amplitudes": [.5], "phases": [0],
                           "phase_offset_type": 'coherent'})
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                         pd2g1={"type": "sine", "frequencies": [trans['C2']], "amplitudes": [.5], "phases": [0],
                           "phase_offset_type": 'coherent'})
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['t_read']), A1 = A1_val2, A2 = A2_val2, laser = laser,
                         pd2g1={"type": "sine", "frequencies": [trans['C2']], "amplitudes": [.5], "phases": [0],
                           "phase_offset_type": 'coherent'})
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                         pd2g1={"type": "sine", "frequencies": [trans['C2']], "amplitudes": [.5], "phases": [0],
                           "phase_offset_type": 'coherent'})
            
            mcas.start_new_segment(name='tau_ramsey', loop_count=1)
            if _I_['laser'] == 'bright' and '12' in _I_['state']:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus+20), A1 = True, laser = True)
            elif _I_['laser'] == 'bright' and '32' in _I_['state']:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus+20), A2 = True, laser = True)
            else:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus+20))

        # Pi/2 (phi)
            rf_pulse(si1_freq+_I_['freq'], amp = si1_amp, dur=si1_pi2, phase=_I_['readout_phase'])
        
        # SSR 2
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A1',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read'],8),
                    length_mus_mw=pi_dur_read,
                    amplitudes=[L_amp_read, R_amp_read],
                    repetitions=int(_I_['n_ssr2'])
                    )
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
        
        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements, n_vals = 200)
        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
        ['init', '<', 11, 0, 0, 1],
        ['result', '>',15, 0, 0, 1], # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 6, 1, 0, 1],
        # ['init', '<', 4, 0, 0, 1], #SSR1
        # ['result', '>', 12, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        # #['result', '>', 0, 6, 0, 2], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        # ['init', '>', 8, 1, 0, 1],   #CRC
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

    nuclear.ple_refocus_interval = 300
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval = 6000
    nuclear.follow_resonnance_by_counts=False

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    Tesla=0.2089
    c_bath = 10.705*Tesla
    si_bath = 8.46*Tesla
    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('A2_power', [6]),
            ('n_ssr1', [2000]),
            ('n_ssr2', [2000]),
            ('init_nuc_state', ['2']),
            ('t_read', [1.024*3]),
            ('state', ['-1/2']),
            ('init_amp', [.1]),#np.linspace(20,301,7)
            ('init_time', [200]),#np.linspace(20,301,7)
            ('freq', [0.0005]), #detuning
            ('tau_ramsey', [*np.arange(21, 10000, 150)]),#*np.linspace(0,3,90) #for rabi
            ('laser', ['dark']),
            ('include_C', [0,1]),
            ('readout_phase', [0., 180])
        )
    )
    nuclear.number_of_simultaneous_measurements = 2

def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    #nuclear.pld.fit_function='cosine'
    nuclear.pld.fit_function='lorentz'
    settings()
    print('run_fun started')
    nuclear.run(abort)