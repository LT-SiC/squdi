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
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]
        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ### #for SSR
            ### ELECTRON RABI PARAMETERS ###
            trans_idx = _I_['init_nuc_state']
            if '-' in _I_['state']:
                transition = 'L'+trans_idx
            elif '+' in _I_['state']:
                transition = 'R'+trans_idx
                
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(_I_['state'],si_bath)
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition)
            
            freq = [trans[transition]]
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
                mcas.start_new_segment('rfPulse')
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur,1),
                    name='nuc',
                    gateRF = True,
                    pd2g2 = {"type": 'sinehermite_rf', "frequencies":[freq],"amplitudes":[amp], "phases":[np.rad2deg(phase)], "phase_type_offset": 'coherent'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)

        # Nuclear Init
            sna.repump(mcas, dur = 30) #made it longer so the PLE line is at a better position
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = _I_['init_amp'])
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)

            ### READOUT ###
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
            
            if _I_['target_spin'] == 'none':
                target_freq = 0 # far detuned
                target_amp = _I_['target_amp']
                target_pi2_dur = _I_['target_pi2_dur']
            elif _I_['target_spin'] == 'si_bath':
                target_freq = si_bath
                target_amp = _I_['target_amp']
                target_pi2_dur = _I_['target_pi2_dur']
            elif _I_['target_spin'] == 'c_bath':
                target_freq = c_bath
                target_amp = _I_['target_amp']
                target_pi2_dur = _I_['target_pi2_dur']
            else:
                target_bath_freq = [si_bath, c_bath]['C' in _I_['target_spin']]
                target_freq = tt.register.get_spin(_I_['target_spin'], _I_['state'].replace('+',''), 'knillpi').detuning.iloc[0] + target_bath_freq
                target_amp = tt.register.get_spin(_I_['target_spin'], _I_['state'].replace('+',''), 'knillpi').pi2_amp.iloc[0]
                target_pi2_dur = tt.register.get_spin(_I_['target_spin'], _I_['state'].replace('+',''), 'knillpi').pi2_dur.iloc[0]
                target_amp = _I_['target_amp']
                target_pi2_dur = _I_['target_pi2_dur']
            
            total_tau = _I_['total_tau']
            n_rep=_I_['n_rep']
            #total_tau = 1000000/tt.couplings.get_coupling('Si1',_I_['target_spin'])/2
            #n_rep = 1
            #if total_tau >= 400000:
            #    n_rep = 3
        # rabi
            mcas.start_new_segment('SEDOR', loop_count=1)
            sna.sedor(mcas,
                probe_pi2_dur = si1_pi2,
                n_rep_sedor = n_rep,
                sedort = _I_['sedort'],
                total_tau = total_tau,
                probe_freq = si1_freq,
                probe_amp = si1_amp,
                target_freq = target_freq + _I_['target_freq'],
                target_amp = target_amp,
                target_dur = target_pi2_dur*2,
                shutter = 'opening',
                pi2_2 = True,
                phi_2 = _I_['readout_phase'],
                )
        
        # SSR 2
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A1',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
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
            
        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements, n_vals = _I_['n_vals'])


        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
        ['init', '<', 9, 0, 0, 1],
        ['result', '>',9, 0, 0, 1], # Put "int(_I_['n_ssr']" as nlp_per_point?
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

    nuclear.ple_refocus_interval = 450
    nuclear.confocal_refocus_interval = 1200  # seconds
    nuclear.odmr_refocus_interval = 6000
    nuclear.follow_resonnance_by_counts=False

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    tesla = (nuclear.queue._transition_tracker.mw_mixing_frequency_L+nuclear.queue._transition_tracker.mw_mixing_frequency_R)/(2*28031.6)
    c_bath = nuclear.queue._transition_tracker.c_bath
    si_bath = nuclear.queue._transition_tracker.si_bath

    step = 25000
    # Original list
    vals = np.arange(20000, 1300000, step)
    # Apply ~10% random deviation
    taus = [20000]+[*(vals + step * np.random.uniform(0., .7, size=len(vals))).astype(int)]
    
    
    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('n_vals', [200]),
            ('t_read', [1.024*3]),
            ('n_ssr1', [2000]),
            ('n_ssr2', [2000]),
            ('init_nuc_state', ['2']),
            ('init_amp', [.15]),
            ('init_time', [200]),
            ('sedort', ['hahn']),
            ('n_rep', [1]),
            ('total_tau', [1e6/4.66/2]),
            ('target_spin', ['Si2']),
            ('state', ['+3/2']),
            ('target_pi2_dur', [*np.arange(200,2000,100)]),
            ('target_amp', [0.8]),
            #('target_freq', [*np.round(np.arange(-0.0007,0.0007, 0.0001),4)]),
            ('target_freq', [0.]),
            ('readout_phase', [0.]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 1

def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.hashed = False
    nuclear.debug_mode = False
    nuclear.pld.fit_function='lorentz'
    settings()
    print('run_fun started')
    nuclear.run(abort)