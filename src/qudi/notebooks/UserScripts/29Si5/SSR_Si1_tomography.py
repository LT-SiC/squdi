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

helper=sch.Tomography_helper()

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
            def cnot(amp, dur, freq=None,phase=0):
                if freq== None:
                    freq=trans[transition]
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur,1),
                    amplitudes=[amp],
                    frequencies=[freq],
                    mixer_deg=[-90],
                    phase=[phase*180/np.pi],
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

            def tomography(basis):
                sign,seq=helper.get_measurement_sequence(basis)
                print(basis)
                print(sign, seq)

                si1_freq_1, si1_amp_1, si1_pi_1, si1_pi2_1 = sna.get_hardcoded_si1_values(_I_['state'].replace("3","1"), si_bath)
                si1_freq_2, si1_amp_2, si1_pi_2, si1_pi2_2 = sna.get_hardcoded_si1_values(_I_['state'].replace("1","3"), si_bath)

                amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition,fast=True)
                R_amp_read_1, L_amp_read_1, pi_dur_read_1, pi2_dur_read_1 = sna.get_hardcoded_e_values_for_readout("1",weak=True)
                R_amp_read_2, L_amp_read_2, pi_dur_read_2, pi2_dur_read_2 = sna.get_hardcoded_e_values_for_readout("2",weak=True)

                for step in seq:
                    #cnot will be misused, here we go full power as the gate expects a full rotation
                    if step=="Rx90_1":
                        cnot(amp,pi2_dur,phase=0)
                    elif step=="Rxm90_1":
                        cnot(amp,pi2_dur,phase=np.pi)
                    elif step=="Rym90_1":
                        cnot(amp,pi2_dur,phase=np.pi/2)
                    elif step=="Rym90_1":
                        cnot(amp,pi2_dur,phase=-np.pi/2)

                    elif step=="Rx90_2":
                        rf_pulse(si1_freq_1,dur=si1_pi2_1,phase=0)
                        rf_pulse(si1_freq_2,dur=si1_pi2_2,phase=0)
                    elif step=="Rxm90_2":
                        rf_pulse(si1_freq_1,dur=si1_pi2_1,phase=np.pi)
                        rf_pulse(si1_freq_2,dur=si1_pi2_2,phase=np.pi)
                    elif step=="Ry90_2":
                        rf_pulse(si1_freq_1,dur=si1_pi2_1,phase=np.pi/2)
                        rf_pulse(si1_freq_2,dur=si1_pi2_2,phase=np.pi/2)
                    elif step=="Ry90_2":
                        rf_pulse(si1_freq_1,dur=si1_pi2_1,phase=-np.pi/2)
                        rf_pulse(si1_freq_2,dur=si1_pi2_2,phase=-np.pi/2)

                    elif step=="CNOT12":
                        cnot([R_amp_read_1,L_amp_read_1]["L" in trans],dur=pi_dur_read_1,phase=0)
                    elif step=="CNOT21":
                        rf_pulse(si1_freq_1,dur=si1_pi_1,phase=0)
                    
                    

                       
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
            
            
            mcas.start_new_segment(name='Entangle')
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)

            cnot(amp, pi2_dur, trans[transition]) #electron on equator
            rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi) #entangle

            #rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi2)
            #cnot([R_amp_read, L_amp_read]["L" in transition], pi_dur_read, trans[transition])

            mcas.start_new_segment(name='Tomography')
            tomography(_I_["RO_dir"])
            
            mcas.start_new_segment(name='RO')
        # Copy electron state to nuclear state
            #rf_pulse(si1_freq)

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
       # ['init', '>', 9, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['result', '>', 9, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
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
            ('sweeps', range(40)),
            ('A2_power', [20]),
            ('n_vals', [1000]),
            ('bfield', [tesla]),
            ('t_read', [1.024 * 4]),
            ('state', ['-3/2']),
            ('init_time', [200]),
            ('init_time_inter_ddrf', [200]),
            ('n_ssr2', [3000]),
            ('n_ssr1', [3000]),
            ('init_nuc_state', ['1']),
            ('RO_dir', ['XX','YY','ZZ','IX', 'IY', 'IZ', 'XI', 'XY', 'XZ', 'YI', 'YX','YZ', 'ZI', 'ZX', 'ZY']), 
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