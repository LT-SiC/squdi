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
                
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(_I_['state'], si_bath) #FIXME
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition) #FIXME


            # def electron rabi
            def cnot(amp, dur, freq):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur,1),
                    amplitudes=[amp],
                    frequencies=[freq],
                    mixer_deg=[-90]
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

        # Initialize electron
            
        # Start actual Sequence
            # Initialize weakly coupled
            mcas.start_new_segment('Init', loop_count=3)
            sna.electron_init(mcas, _I_['state'], _I_['init_time']/2, [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .04, newsegment=False)
            mcas.asc(length_mus=0.256, gateMW=True)
            
            bath_freq = [si_bath, c_bath]['C' in _I_['probe_spin']]
            coupling = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).detuning.iloc[0]
            probe_freq = bath_freq + coupling

            ddrf_tau = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_tau.iloc[0]
            ddrf_amp = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_amp.iloc[0]
            ddrf_phase_inc = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_phase_inc.iloc[0]
            ddrf_phase_init = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_phase_init.iloc[0]
            ddrf_phase_read = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_phase_read.iloc[0]
            n_rep_ddrf = int(tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).n_rep_ddrf.iloc[0])
            probe_amp = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).pi2_amp.iloc[0]
            probe_dur_pi2 = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).pi2_dur.iloc[0]
            
            target_freq1 = tt.register.get_spin(_I_['target_spin1'], _I_['state'].replace('+',''), _I_['ddrft']).detuning.iloc[0] + [si_bath, c_bath]['C' in _I_['target_spin1']]
            if _I_['target_spin2']=='si_bath':
                target_freq2 = si_bath
            else:
                target_freq2 = tt.register.get_spin(_I_['target_spin2'], _I_['state'].replace('+',''), _I_['ddrft']).detuning.iloc[0] + [si_bath, c_bath]['C' in _I_['target_spin2']]
            target_amp1 = tt.register.get_spin(_I_['target_spin1'], _I_['state'].replace('+',''), _I_['ddrft']).pi2_amp.iloc[0]
            target_amp2 = tt.register.get_spin(_I_['target_spin2'], _I_['state'].replace('+',''), _I_['ddrft']).pi2_amp.iloc[0]
            target_pi2_dur1 = tt.register.get_spin(_I_['target_spin1'], _I_['state'].replace('+',''), _I_['ddrft']).pi2_dur.iloc[0]
            target_pi2_dur2 = tt.register.get_spin(_I_['target_spin2'], _I_['state'].replace('+',''), _I_['ddrft']).pi2_dur.iloc[0]
            target_amp2 = _I_['target_amp']
            target_pi2_dur2 = _I_['target_dur']
            # Init Probe
            sna.ddrf(mcas,
                 np.pi/2, # global_mw_phase
                 np.pi/2, # second_mw_phase
                 ddrf_phase_inc, # rf_phase_increment
                 0.0, # rotation_axis
                 pi_dur, # pi electron
                 pi2_dur, # pi/2 electron
                 coupling,  # detuning
                 bath_freq,  # bath freq
                 ddrf_tau,  # tau
                 n_rep_ddrf,  # n_rep_ddrf
                 _I_['ddrft'],  # ddrft
                 trans[transition],  # mw freq
                 amp,  # mw amp
                 ddrf_amp,  # rf amp
                 )
            sna.ddrf(mcas,
                 0, # global_mw_phase
                 0, # second_mw_phase
                 ddrf_phase_inc, # rf_phase_increment
                 ddrf_phase_init, # rotation_axis
                 pi_dur, # pi electron
                 pi2_dur, # pi electron
                 coupling,  # detuning
                 bath_freq,  # bath freq
                 ddrf_tau,  # tau
                 n_rep_ddrf,  # n_rep_ddrf
                 _I_['ddrft'],  # ddrft
                 trans[transition],  # mw freq
                 amp,  # mw amp
                 ddrf_amp,  # rf amp
                 pi2_1 = False, # pi half before DDRF
                 pi2_2 = False # pi half after DDRF
                 )

            # Reinit electron
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .24, newsegment=True)
            shutter = 'open'
            total_tau1 = 1000000/tt.couplings.get_coupling(_I_['probe_spin'],_I_['target_spin1'])/4
            #total_tau1 = _I_['total_tau1']
            if  total_tau1 > 200000:
                shutter = 'opening'
            total_tau2 = _I_['total_tau']
            # SEDOR Probe - Target1
            
            mcas.start_new_segment('SEDOR', loop_count=1)
            sna.sedor(mcas,
                probe_pi2_dur = probe_dur_pi2, # probe decoupling
                n_rep_sedor = _I_['n_rep_sedor1'],
                sedort = _I_['sedort1'],
                total_tau = total_tau1,
                probe_freq = probe_freq,
                probe_amp = probe_amp,
                target_freq = target_freq1,
                target_amp = target_amp1, # target recoupling
                target_dur = target_pi2_dur1 * 2, # target recoupling, factor 2 to convert from pi/2 to pi
                shutter = 'closed',
                pi2_1=True,
                pi2_2=True,
                phi_1=np.pi/2,
                phi_2=0.,
                )
            # SEDOR Target1 - Target2
            sna.sedor(mcas,
                probe_pi2_dur = target_pi2_dur1,
                n_rep_sedor = _I_['n_rep_sedor2'],
                sedort = _I_['sedort2'],
                total_tau = total_tau2,
                probe_freq = target_freq1,
                probe_amp = target_amp1,
                target_freq = target_freq2 + _I_['target_freq2'],
                target_amp = target_amp2,
                target_dur = target_pi2_dur2 * 2,
                shutter = shutter,
                pi2_1=True,
                pi2_2=True,
                phi_1=0. + _I_['phase_2sedor'],
                phi_2=0. + _I_['phase_2sedor'],
                )
            # SEDOR Probe - Target1 excluding last pi/2 pulse, because DDRF reads out along X.
            sna.sedor(mcas,
                probe_pi2_dur = probe_dur_pi2, # probe decoupling
                n_rep_sedor = _I_['n_rep_sedor1'],
                sedort = _I_['sedort1'],
                total_tau = total_tau1,
                probe_freq = probe_freq,
                probe_amp = probe_amp,
                target_freq = target_freq1,
                target_amp = target_amp1, # target recoupling
                target_dur = target_pi2_dur1 * 2, # target recoupling, factor 2 to convert from pi/2 to pi
                shutter = 'open',
                pi2_1=True,
                pi2_2=False,
                phi_1=np.pi/2 + _I_['phase_2sedor'] + _I_['phase_3sedor'],
                phi_2=0 + _I_['phase_2sedor'] + _I_['phase_3sedor'],
                )
            # Read Probe
            mcas.asc(length_mus=0.256, gateMW=True)
            sna.ddrf(mcas,
                 np.pi/2, # global_mw_phase
                 np.pi/2, # second_mw_phase
                 ddrf_phase_inc, # rf_phase_increment
                 ddrf_phase_init + ddrf_phase_read + _I_['phase_2sedor'] + _I_['phase_3sedor'] + _I_['readout_phase'], # rotation_axis
                 pi_dur, # pi electron
                 pi2_dur, # pi electron
                 coupling,  # detuning
                 bath_freq,  # bath freq
                 ddrf_tau,  # tau
                 n_rep_ddrf,  # n_rep_ddrf
                 _I_['ddrft'],  # ddrft
                 trans[transition],  # mw freq
                 amp,  # mw amp
                 ddrf_amp,  # rf amp
                 )
        # Copy electron state to nuclear state
            rf_pulse(si1_freq)

        # Readout of nuclear spin via SSR
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read'],8),
                    length_mus_mw=pi_dur_read,
                    amplitudes=[L_amp_read, R_amp_read],
                    repetitions=int(_I_['n_ssr2'])
                    )
        # CRC.
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[500],
                    wait_dur=0.0,
                    robust=False,
                    nuc='charge_state',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=2,
                    )

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements, n_vals = _I_['n_vals'])
        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
        ['init', '<', 9, 0, 0, 1], #SSR1
        ['result', '>', 9, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        #['result', '>', 0, 6, 0, 2], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 6, 1, 0, 1],   #CRC

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
    nuclear.confocal_refocus_interval = 3000  # seconds
    nuclear.odmr_refocus_interval = 6000

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False
    
    tt  = nuclear.queue._transition_tracker
    tesla = (tt.mw_mixing_frequency_L+nuclear.queue._transition_tracker.mw_mixing_frequency_R)/(2*28031.6)
    c_bath = nuclear.queue._transition_tracker.c_bath
    si_bath = nuclear.queue._transition_tracker.si_bath

    step = 40000
    # Original list
    vals = np.arange(20000, 800000, step)
    # Apply ~10% random deviation
    taus = [20000]+[*(vals + step * np.random.uniform(0.01, .5, size=len(vals))).astype(int)]
    

    nuclear.parameters = OrderedDict(
        (
            # System parameters
            ('sweeps', range(20)),
            ('A2_power', [20]),
            ('n_vals', [400]),
            ('bfield', [tesla]),
            ('state', ['-3/2']),
            ('init_nuc_state', ['2']),
            ('t_read', [1.024 * 3]),
            ('n_ssr2', [2000]),
            ('n_ssr1', [2000]),
            ('init_time', [200]),
            ('ddrft', ['knillpi']), #fid, hahn, xy4, xy8, xy16, knillpi, kdd4, kdd8, kdd16
            ('probe_spin', ['Si5']),
            ('n_rep_sedor1', [1]),
            ('n_rep_sedor2', [1,2]),
            ('sedort1', ['hahn']), #fid, hahn, xy4, xy8, xy16, knillpi, kdd4, kdd8, kdd16
            ('sedort2', ['hahn']), #fid, hahn, xy4, xy8, xy16, knillpi, kdd4, kdd8, kdd16
            
            ('target_spin1', ['Si14']), # 
            ('target_spin2', ['Si25']), #
            ('phase_3sedor', [0., np.pi/4, np.pi/2]), # 
            ('total_tau', taus),
            ('phase_2sedor', [0.]), # 
            #('total_tau1', [7100,14200]),
            ('target_freq2', [0.]),
            ('readout_phase', [0.]),
            ('target_amp', [0.1/1.5]),
            ('target_dur', [1200*1.5]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 1


def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 20 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)