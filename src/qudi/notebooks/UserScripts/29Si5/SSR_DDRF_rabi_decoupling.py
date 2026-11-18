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
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]

        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ###
            trans_idx = _I_['init_nuc_state']
            if '-' in _I_['state']:
                transition = 'L'+trans_idx
                
            elif '+' in _I_['state']:
                transition = 'R'+trans_idx
                
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(_I_['state'], si_bath)
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition,fast=True)

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
                    pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [phase*180/np.pi],
                           "phase_offset_type": 'coherent'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)
           
        ### SEQUENCE STARTS HERE ###
        # Repump
            sna.repump(mcas, dur = 30)
        # Init nuclear via CNOT
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(trans_idx,weak=True)
            cnot([R_amp_read, L_amp_read]["L" in transition], pi_dur_read, trans[transition])
            rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)
        # Confirm initialized nuclear spin via SSR
            if trans_idx == '1':
                ssr_freqs=[trans['L2'], trans['R2']]
                read_idx = '2'
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                read_idx = '1'

            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(read_idx,weak=True)
            
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
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .14) #FIXME max_amp = 0.24
            
            i=_I_["file_index"]

            try:
                padding=_I_["comment"]=="padding"
            except:
                padding=None
            bath_freq = [si_bath, c_bath]['C' in _I_['probe_spin']]
            spin=tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft'],Tau_finder=_I_["Tau_finder_tau_from_file"],comment=_I_["comment"])
            print(spin)


            det_from_res=spin.detuning_from_resonance_freq.iloc[i]
            print("det from res",det_from_res)
            if det_from_res=="":
                det_from_res=0.
            else:
                det_from_res=float(det_from_res)

            coupling = spin.detuning.iloc[i] + det_from_res
            
            ddrf_tau = spin.ddrf_tau.iloc[i]/2
            ddrf_amp = spin.ddrf_amp.iloc[i]
            ddrf_phase_inc = spin.ddrf_phase_inc.iloc[i]

            ddrf_phase_inc-=ddrf_tau*det_from_res

            if _I_["init_phase"]=="file":
                ddrf_phase_init = spin.ddrf_phase_init.iloc[i]
            else:
                ddrf_phase_init=_I_['init_phase']

            if _I_["read_phase"]=="file":
                ddrf_phase_read = spin.ddrf_phase_read.iloc[i]
            else:
                ddrf_phase_read=_I_['read_phase']

            print("params=",bath_freq,coupling,ddrf_tau,ddrf_amp,ddrf_phase_inc,ddrf_phase_init,ddrf_phase_read)


            # ddrf_phase_inc =_I_['phase_inc']
            # if ddrf_phase_inc == 0.3:
            #     ddrf_amp = 0.445
            # elif ddrf_phase_inc == 3.38:
            #     ddrf_amp = 0.860
            # elif ddrf_phase_inc == 4.98:
            #     ddrf_amp = 0.435
            # elif ddrf_phase_inc == 5.96:
            #     ddrf_amp = 0.465

            n_rep_ddrf = int(spin.n_rep_ddrf.iloc[i])

            print(bath_freq,coupling,ddrf_tau,ddrf_amp,ddrf_phase_inc,n_rep_ddrf,det_from_res)

            #ddrf_phase_init = _I_['init_phase']
            #ddrf_phase_read = _I_['read_phase']
        # Start actual Sequence
            # Initialize weakly coupled
            mcas.start_new_segment('Seq', loop_count=1) #FIXME loop_count = 3
            mcas.asc(length_mus=0.256, gateMW=True, green = True)
            sna.ddrf(mcas,
                 np.pi/2, # global_mw_phase
                 np.pi/2+_I_["MW_pi2_2_added_phase"], # second_mw_phase
                 ddrf_phase_inc, # rf_phase_increment
                 0.0, # rotation_axis
                 pi_dur, # pi electron
                 pi2_dur, # pi electron
                 coupling,  # detuning
                 bath_freq,  # bath freq
                 ddrf_tau,  # tau
                 _I_['n_rep_ddrf'],  # n_rep_ddrf
                 _I_['ddrft'],  # ddrft
                 trans[transition],  # mw freq
                 amp,  # mw amp
                 ddrf_amp,  # rf amp
                 padding=padding,
                 constant_phase_offset=True,
                 )

            sna.ddrf(mcas,
                 0, # global_mw_phase
                 _I_["MW_pi2_2_added_phase"], # second_mw_phase
                 ddrf_phase_inc, # rf_phase_increment
                 1*_I_["ddrf_rep_increment"]+np.pi/2, #ddrf_phase_init, # rotation_axis
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
                 pi2_2 = False, # pi half after DDRF
                 padding=padding,
                 constant_phase_offset=True,
                 )
            
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .1, newsegment=False) #FIXME max_amp = 0.24
            
            # Nuclear Rabi
            mcas.start_new_segment(name='RF Rabi')
            if _I_['rf_dur_rabi']==-1:
                if "C" in _I_["probe_spin"]:
                    dur=400
                if "Si" in _I_["probe_spin"]:
                    dur=600
            else:
                dur = _I_['rf_dur_rabi']

            #rf_pulse(bath_freq + coupling, amp=_I_['rf_amp_rabi'], dur=dur, phase=ddrf_phase_init+ ddrf_phase_read)
            sna.ddrf(mcas,
                 np.pi/2, # global_mw_phase
                 np.pi/2 + _I_["MW_pi2_2_added_phase"], # second_mw_phase
                 ddrf_phase_inc, # rf_phase_increment
                 0, #ddrf_phase_init + ddrf_phase_read, # rotation_axis
                 pi_dur, # pi electron
                 pi2_dur, # pi electron
                 coupling,  # detuning
                 bath_freq,  # bath freq
                 ddrf_tau,  # tau
                 n_rep_ddrf,  # n_rep_ddrf
                 _I_['ddrft'],  # ddrft
                 trans[transition],  # mw freq
                 amp,  # mw amp
                 _I_['rf_amp_rabi'],  # rf amp
                 padding=padding,
                 constant_phase_offset=True,
                 pi2_1 = False,
                 pi2_2 = False,
                 conditional = False,
                 )
            
            # Measure
            mcas.asc(length_mus=0.256, gateMW=True)
            sna.ddrf(mcas,
                 np.pi/2, # global_mw_phase
                 np.pi/2 + _I_["MW_pi2_2_added_phase"], # second_mw_phase
                 ddrf_phase_inc, # rf_phase_increment
                 _I_["ddrf_rep_increment"], #ddrf_phase_init + ddrf_phase_read, # rotation_axis
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
                 padding=padding,
                 constant_phase_offset=True,
                 )
        # Copy electron state to nuclear state
            mcas.start_new_segment(name='Readout')
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
        ['init', '<', 8, 0, 0, 1], #SSR1
        ['result', '>', 8, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
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

    nuclear.ple_refocus_interval = 600
    nuclear.confocal_refocus_interval = 3000  # seconds
    nuclear.odmr_refocus_interval = 6000

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    tesla_z = nuclear.queue._transition_tracker.current_magnetic_field_vector[0]
    tesla_x = nuclear.queue._transition_tracker.current_magnetic_field_vector[1]
    tesla=np.sqrt(tesla_z**2+tesla_x**2) # Version 1: T = 0.2087028
    #tesla=(nuclear.queue._transition_tracker.mw_mixing_freq_L+69.8)/28024  # Version 2: T = 0.2087315
    #tesla=nuclear.queue._transition_tracker.current_magnetic_field # Version 3: T = 0.2086739
    tesla = (nuclear.queue._transition_tracker.mw_mixing_frequency_L+nuclear.queue._transition_tracker.mw_mixing_frequency_R)/(2*28031.6)
    c_bath = nuclear.queue._transition_tracker.c_bath
    si_bath = nuclear.queue._transition_tracker.si_bath
    
    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('A2_power', [20]),
            ('n_vals', [500]),
            ('bfield', [tesla]),
            ('t_read', [1.024 * 4]),
            ('state', ['-3/2']),
            ('init_time', [200]),
            ('n_ssr2', [3000]),
            ('n_ssr1', [3000]),
            ('init_nuc_state', ['1']),
            ('ddrft', ["xy4"]), #fid, hahn, xy4, xy8, xy16, knillpi, kdd4, kdd8, kdd16
            ('probe_spin', ["Si4"]),
            ("Tau_finder_tau_from_file",[1]),
            ("comment",["testig_new_ddrft"]), #"testig_new_ddrft"
            #('detuning', [0.]),
            #('init_phase', [*np.linspace(0,2*np.pi,10)]),
            #('init_phase', [0.5,3.4]),  #si9
            ('init_phase', ["file"]),#4.95
            #('read_phase', [*np.linspace(0,2*np.pi,7)]),
            ('ddrf_rep_increment', [*np.linspace(0,2*np.pi,9)]),
            #('ddrf_rep_increment', [4.037]),
            #('read_phase', [3.0]),  #si6
            #('read_phase', [0.,np.pi/4,np.pi/2]),
            #('read_phase',[3.854]), #Si5
            #('read_phase',[5.6]), #Si6
            ('read_phase',["file"]),
            ("file_index",[-1]),
            #("MW_pi2_2_added_phase", [*np.linspace(0,np.pi*2,10)]),
            ("MW_pi2_2_added_phase", [0.0]),
            #("rf_phase",[*np.linspace(0,2*np.pi,17)]),
            #("rf_phase",[*np.linspace(0,2*np.pi,17)]),
            #('rf_amp_rabi', [*np.linspace(0.3,0.99,4)]),
            #('rf_dur_rabi', [*np.linspace(200,1300,20)]),
            ('rf_dur_rabi',[-1]),
            ('n_rep_ddrf', [2,4,6,8]),
            ('rf_amp_rabi', list(np.linspace(0,1,11))),
        )
    )
    nuclear.number_of_simultaneous_measurements = 1


def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)