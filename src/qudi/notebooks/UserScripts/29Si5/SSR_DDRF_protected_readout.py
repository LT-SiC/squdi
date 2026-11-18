# coding=utf-8
import datetime
import numpy as np
import os
import importlib

print(os.getcwd())
print(os.getcwd())

import notebooks.UserScripts.helpers.sequence_creation_helpers as sch;

print(os.getcwd())

importlib.reload(sch)
print(os.getcwd())
import notebooks.UserScripts.helpers.shared as shared
from hardware.Keysight_AWG_M8190.pym8190a import MultiChSeq as MultiChSeq
import notebooks.UserScripts.helpers.snippets_awg as sna

print(os.getcwd())

importlib.reload(sna)
importlib.reload(shared)
# importlib.reload(MultiChSeq)
import notebooks.UserScripts.helpers.shared as ush;

importlib.reload(ush)
from logic.qudip_enhanced import *
import hardware.Keysight_AWG_M8190.elements as E
from collections import OrderedDict
from PyQt5 import QtTest
print(os.getcwd())

seq_name = os.path.basename(__file__).split('.')[0]
nuclear = sch.create_nuclear(__file__)
print("created_nuclear")
with open(os.path.abspath(__file__).split('.')[0] + ".py", 'r') as f:
    meas_code = f.read()

print("passed")

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
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition)

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
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .24)
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(si1_freq)
        # Confirm initialized nuclear spin via SSR
            if trans_idx == '1':
                ssr_freqs=[trans['L2'], trans['R2']]
                read_idx = '2'
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                read_idx = '1'
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(read_idx,weak=False)
            
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
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .24)

            
            bath_freq = [si_bath, c_bath]['C' in _I_['probe_spin']]
            coupling = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).detuning.iloc[0] + _I_['detuning']
            
            ddrf_tau = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_tau.iloc[0]
            ddrf_amp = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_amp.iloc[0]
            ddrf_phase_inc = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_phase_inc.iloc[0]
            #ddrf_phase_inc =_I_['phase_inc']
            #  if ddrf_phase_inc == 0.358:
            #       ddrf_amp = 0.355
            #  elif ddrf_phase_inc == 4.93:
            #       ddrf_amp = 0.4
            #  elif ddrf_phase_inc == 5.94:
            #       ddrf_amp = 0.463

            n_rep_ddrf = int(tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).n_rep_ddrf.iloc[0])
            ddrf_phase_init = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_phase_init.iloc[0]#_I_['init_phase']
            ddrf_phase_read = tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']).ddrf_phase_read.iloc[0]

            print(bath_freq,coupling,ddrf_tau,ddrf_amp,ddrf_phase_inc,n_rep_ddrf,ddrf_phase_init,ddrf_phase_read)

        # Start actual Sequence
            #Initialize weakly coupled
            mcas.start_new_segment('Seq', loop_count=3)
            mcas.asc(length_mus=0.256, gateMW=True, green = True)
            sna.ddrf(mcas,
                 np.pi/2, # global_mw_phase
                 np.pi/2, # second_mw_phase
                 ddrf_phase_inc, # rf_phase_increment
                 0.0, # rotation_axis
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
            sna.ddrf(mcas,
                 0., # global_mw_phase
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
            
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .24, newsegment=False)
            
            # Nuclear Rabi
            mcas.start_new_segment(name='readout perturbance')
            rf_pulse(bath_freq + coupling, amp=_I_["rf_amp_rabi"], dur=_I_['rf_dur_rabi'], phase=ddrf_phase_init) #pi/2 pulse #Hadcoded amp #0.216

            c_amps = _I_["central_amp"]
            c_dur = _I_["central_dur"] #E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-C', amp=).pi)*2

            amp1=_I_["central_amp"]
            amp2=_I_["central_amp"]
            pi_dur2=E.round_length_mus_to_x_multiple_ps(_I_["central_dur"])

            #amp1, pi_dur1, pi2_dur1=sna.get_hardcoded_e_values_for_control("C1")
            #amp2, pi_dur2, pi2_dur2=sna.get_hardcoded_e_values_for_control("C2")

            ssr_freqs_pert=ssr_freqs.copy()
            if _I_["Bright"]: #bright readout
                if "1" in read_idx:
                    ssr_freqs_pert=[trans['L2']+_I_["ssr_pert_detuning"], trans['R2']+_I_["ssr_pert_detuning"]]
                else:
                    ssr_freqs_pert=[trans['L1']+_I_["ssr_pert_detuning"], trans['R1']+_I_["ssr_pert_detuning"]]
                R_amp_read_pert, L_amp_read_pert, pi_dur_read_pert, pi2_dur_read_pert = sna.get_hardcoded_e_values_for_readout(["1","2"]["1"==read_idx],weak=False)

                A2=[False,True]["3" in _I_["state"]]

            else:
                ssr_freqs_pert=[ssr_freqs_pert[0]+_I_["ssr_pert_detuning"], ssr_freqs_pert[1]+_I_["ssr_pert_detuning"]]
                R_amp_read_pert, L_amp_read_pert, pi_dur_read_pert, pi2_dur_read_pert = sna.get_hardcoded_e_values_for_readout(read_idx,weak=False)

                A2=[False,True]["1" in _I_["state"]]

            A1= not A2

            MW_gate="gateMW" in _I_["protected_readout"]
            RF_gate="gateRF" in _I_["protected_readout"]
            A1=A1 if "laser" in _I_["protected_readout"] else False
            A2=A2 if "laser" in _I_["protected_readout"] else False
            pi_dur_read_pert = pi_dur_read_pert + _I_["ssr_added_time"]
            pi_dur2=pi_dur2 + _I_["central_ssr_added_time"]

            print(A1,A2,MW_gate,RF_gate)

            sna.wait(mcas,_I_['n_ssr1']*_I_['t_read'])

            repetitions=_I_["repetitions"]
            if _I_["protected_readout"]=="protected readout":
                sna.protected_ssr(mcas=mcas, queue=self.queue,
                        frequencies=[ssr_freqs_pert],
                        wait_dur=0.0,
                        robust=False,
                        nuc='29Si8_A2',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read'],8),
                        length_mus_mw=pi_dur_read_pert,
                        amplitudes=[L_amp_read_pert, R_amp_read_pert],
                        repetitions=repetitions,
                        central_frequencies=[trans["C1"]+_I_["central_detuning"],trans["C2"]+_I_["central_detuning"]],
                        central_amplitudes=[amp1,amp2],
                        central_length_mus=pi_dur2,
                        step_idx=1,
                        discard=False #this measurement will not be considered in the analysis of the trace
                        )
                
            elif _I_["protected_readout"]=="normal readout":
                sna.ssr(mcas=mcas, queue=self.queue,
                        frequencies=[ssr_freqs_pert],
                        wait_dur=0.0,
                        robust=False,
                        nuc='29Si8_A2',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read'],8),
                        length_mus_mw=pi_dur_read_pert,
                        amplitudes=[L_amp_read_pert, R_amp_read_pert],
                        repetitions=repetitions,#int(_I_['n_ssr2'])
                        step_idx=1,
                        discard=False
                        )

            elif False:# "gate" in _I_["protected_readout"] or  "laser" in _I_["protected_readout"]:
                segment_length=3
                loops, correction_mus = shared.calculate_loop_count(repetitions*_I_['t_read'], segment_length)
                # print("loops:", loops)
                if loops > 0:
                    mcas.start_new_segment(name='ssr_simulator', loop_count=repetitions)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(segment_length),A2=A2,A1=A1,gateMW=False, gateRF=False)
                    if _I_["gate_switching"]: #1µs off
                        #mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1),A2=False,A1=False,gateMW=MW_gate, gateRF=RF_gate)
                        pd2g1_L = {'frequencies': [ssr_freqs_pert[0]], 'type': 'sinehermite', 
                                    'amplitudes': [L_amp_read_pert*0], 'length_mus': pi_dur_read_pert}
                        mcas.asc(pd2g1=pd2g1_L, gateMW=True, name='MW') #Each pi pulse will be writte separately.
                        pd2g1_R = {'frequencies': [ssr_freqs_pert[1]], 'type': 'sinehermite', 
                                    'amplitudes': [R_amp_read_pert*0], 'length_mus': pi_dur_read_pert}
                        mcas.asc(pd2g1=pd2g1_R, gateMW=True, name='MW') #Each pi pulse will be writte separately.

                if correction_mus>0:
                    mcas.start_new_segment(name='ssr_simulator', loop_count=1)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus),A2=A2,A1=A1,gateMW=False, gateRF=False)
                    if _I_["gate_switching"]: #1µs off
                        #mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1),A2=False,A1=False,gateMW=MW_gate, gateRF=RF_gate)
                        pd2g1_L = {'frequencies': [ssr_freqs_pert[0]], 'type': 'sinehermite', 
                                    'amplitudes': [L_amp_read_pert*0], 'length_mus': pi_dur_read_pert}
                        mcas.asc(pd2g1=pd2g1_L, gateMW=True, name='MW') #Each pi pulse will be writte separately.
                        pd2g1_R = {'frequencies': [ssr_freqs_pert[1]], 'type': 'sinehermite', 
                                    'amplitudes': [R_amp_read_pert*0], 'length_mus': pi_dur_read_pert}
                        mcas.asc(pd2g1=pd2g1_R, gateMW=True, name='MW') #Each pi pulse will be writte separately.


            elif "gate" in _I_["protected_readout"] or  "laser" in _I_["protected_readout"]:
                mcas.start_new_segment(name='ssr_simulator', loop_count=repetitions)
                if _I_["save_simulated_measuremnt"]:
                    mcas.asc(name = 'triggerTrue_gate', length_mus=sna.__TT_TRIGGER_LENGTH__, gate=True, gateMW = True) # Gated counter

                if _I_["gate_switching"]:
                    if "protected" in _I_["protected_readout"]: #central transition flipping
                        pd2g1_C1 = {'frequencies': [trans["C1"]], 'type': 'sinehermite', 
                                'amplitudes': [amp1], 'length_mus': pi_dur2}
                        mcas.asc(pd2g1=pd2g1_C1, gateMW=True, name='MW') #Each pi pulse will be writte separately.
                        pd2g1_C2 = {'frequencies': [trans["C2"]], 'type': 'sinehermite', 
                                    'amplitudes': [amp2], 'length_mus': pi_dur2}
                        mcas.asc(pd2g1=pd2g1_C2, gateMW=True, name='MW') #Each pi pulse will be writte separately.
                    
                    pd2g1_L = {'frequencies': [ssr_freqs_pert[0]], 'type': 'sinehermite', 
                                'amplitudes': [L_amp_read_pert], 'length_mus': pi_dur_read_pert}
                    mcas.asc(pd2g1=pd2g1_L, gateMW=True, name='MW') #Each pi pulse will be writte separately.
                    pd2g1_R = {'frequencies': [ssr_freqs_pert[1]], 'type': 'sinehermite', 
                                'amplitudes': [R_amp_read_pert], 'length_mus': pi_dur_read_pert}
                    mcas.asc(pd2g1=pd2g1_R, gateMW=True, name='MW') #Each pi pulse will be writte separately.

                mcas.asc(name="Laser "+["A1","A2"][A2],length_mus=E.round_length_mus_to_x_multiple_ps(3),laser=True,A2=A2,A1=A1,gateMW=False, gateRF=False)

                if _I_["save_simulated_measuremnt"]:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0), name='Count')
                    mcas.asc(length_mus=sna.__TT_TRIGGER_LENGTH__, memory=True,name = 'triggerTrue2_memory')

                    ### gated counter stuff
                    stp_idx=1
                    nuclear.queue._gated_counter.trace.analyze_sequence[stp_idx][3] = repetitions * 1
                    nuclear.queue._gated_counter.trace.analyze_sequence[stp_idx][5] = 1
                    if nuclear.queue._gated_counter.trace.analyze_sequence[stp_idx][5] != 1 and nuclear.queue._gated_counter.trace.analyze_sequence[stp_idx][2] == 'auto':
                        nuclear.queue._gated_counter.trace.analyze_sequence[stp_idx][2] = 0

            else:
                sna.wait(mcas,E.round_length_mus_to_x_multiple_ps(repetitions*_I_['t_read']),20)
                #mcas.asc(name="Wait" ,length_mus=E.round_length_mus_to_x_multiple_ps(repetitions*_I_['t_read']))

            mcas.start_new_segment(name='ddrf_readout')

            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .24, newsegment=False)


            #rf_pulse(bath_freq + coupling, amp=0.216, dur=_I_['rf_dur_rabi'], phase=ddrf_phase_init) #pi/2 pulse #Hadcoded amp
            
            # Measure

            mcas.asc(length_mus=0.256, gateMW=True)
            
            #sna.wait(mcas,600)

            sna.ddrf(mcas,
                 np.pi/2, # global_mw_phase
                 np.pi/2, # second_mw_phase
                 ddrf_phase_inc, # rf_phase_increment
                 ddrf_phase_init + ddrf_phase_read+_I_["final_ddrf_phase"], # rotation_axis
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
            mcas.start_new_segment(name='Readout')
            rf_pulse(si1_freq)# , dur = _I_['duration_rabi'] )

            sna.wait(mcas,_I_["wait before last ssr"])

        # Readout of nuclear spin via SSR
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=2,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['3rd_t_read'],8),
                    length_mus_mw=pi_dur_read,
                    amplitudes=[L_amp_read, R_amp_read],
                    repetitions=int(_I_['n_ssr2']),
                    discard=False
                    )
        # CRC.
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[500],
                    wait_dur=0.0,
                    robust=False,
                    nuc='charge_state',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=3,
                    )

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements, n_vals = _I_['n_vals'])
        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
        ['init', '<', 3, 0, 0, 1], #SSR1
        ['init', '<', 1000, 0, 0, 1], # perturbative ssr
        ['result', '>', 6, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
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
    nuclear.do_ple_refocusA2 = True #

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    # confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = True #
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
    
    #in this measuremtn we try to get very close to what is happening in the real ssr with amp=0. 

    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('A2_power', [20]),
            ('n_vals', [500]),
            ('bfield', [tesla]),
            ('t_read', [1.024 * 3]),
            ('state', ['+3/2']),
            ('init_time', [200]),
            ('n_ssr2', [1000]),
            ('n_ssr1', [500]),
            ('init_nuc_state', ['2']),
            ('ddrft', ['knillpi']), #fid, hahn, xy4, xy8, xy16, knillpi, kdd4, kdd8, kdd16
            ('probe_spin', ['C1']),
            ('rf_dur_rabi', [259.]),
            ('detuning', [0.]),
            ('rf_amp_rabi', [0.4]),
            #('phase_inc', [0.32,3.44,6.01]),
            #('init_phase', [*np.linspace(0,2*np.pi,9)]),
            #('init_phase', [4.95]),
            #('read_phase', [*np.linspace(0,np.pi*2,15)]),
            #('read_phase', [2.889]),
            #('duration_rabi',[*np.linspace(10.,230,20)] ),

            #### Protected readout stuff
            ("save_simulated_measuremnt",[1]),
            ("gate_switching",[1]),
            ("wait before last ssr",[0]),
            ('central_dur', [0.458]), #hardcoded
            ("central_amp", [0.4777]), #hardcoded
            ("ssr_pert_detuning", [0]),
            ("central_detuning", [0]),
            ("protected_readout", ["protected gateMW and laser"]),#"normal readout","Laser","protected readout"
            ("repetitions", [10,100,200,400,600,800,1000]),#10,100,1000,2000
            ("Bright", [0,1]),
            ("3rd_t_read", [3*1.024]),
            ("central_ssr_added_time",[0]),
            ("ssr_added_time",[0]),
            ('final_ddrf_phase', [*np.linspace(0.,np.pi*2,9)]),#*np.linspace(0.,np.pi*2,9)
            #('duration_rabi',[1,60]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 1

print("before_run_fun")
def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    
    print(os.getcwd())
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)

print("went trough script")
