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

            i_ddrf_1=0
            i_ddrf_2=0

            #increment_1=_I_["increment_1"]
            #increment_2=_I_["increment_2"]

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

            def get_params(spin,state,ddrft,index,comment=None):
                bath_freq = [si_bath, c_bath]['C' in spin]
                print(comment)

                spin_data=tt.register.get_spin(spin, state.replace('+',''), ddrft,Tau_finder=_I_["Tau_finder_tau_from_file"],comment=_I_["comment"])

                print(spin_data)

                coupling = spin_data.detuning.iloc[index]
                ddrf_tau = spin_data.ddrf_tau.iloc[index]/2
                ddrf_amp = spin_data.ddrf_amp.iloc[index]
                ddrf_phase_inc = spin_data.ddrf_phase_inc.iloc[index]
                n_rep_ddrf = int(spin_data.n_rep_ddrf.iloc[index])
                ddrf_phase_init =spin_data.ddrf_phase_init.iloc[index]
                ddrf_phase_read = spin_data.ddrf_phase_read.iloc[index]
                pi2_2_MW_phase = spin_data.pi2_2_MW_phase.iloc[index]
                reps_phase_inc = spin_data.reps_phase_inc.iloc[index]

                det_from_res=spin_data.detuning_from_resonance_freq.iloc[index]
                print("det from res",det_from_res)
                if det_from_res=="":
                    det_from_res=0.
                else:
                    det_from_res=float(det_from_res)

                
                ddrf_phase_inc-=float(tt.register.get_spin(spin, state.replace('+',''), "knillpi",Tau_finder=_I_["Tau_finder_tau_from_file"]).Azz.iloc[0])*det_from_res

                if _I_["rf_phase_increment"]!="None":
                    reps_phase_inc=_I_["rf_phase_increment"]

                print("MW phase ",pi2_2_MW_phase, ",end")
                if pi2_2_MW_phase =="":
                    pi2_2_MW_phase=0.
                elif pi2_2_MW_phase==np.nan:
                    pi2_2_MW_phase=0.
                elif pi2_2_MW_phase=="nan":
                    pi2_2_MW_phase=0.
                elif str(pi2_2_MW_phase)=="nan":
                    pi2_2_MW_phase=0.

                print(pi2_2_MW_phase)


                return bath_freq,coupling,ddrf_tau,ddrf_amp,ddrf_phase_inc,n_rep_ddrf,ddrf_phase_init,ddrf_phase_read,pi2_2_MW_phase,reps_phase_inc
            
            def ddrf_init(spin,state,ddrft,index,loops=3,electron_init=False,new_segment=False,electron_init_in_loop=False,individual_segments=False):
                spin_i=[1,0][spin==_I_["spin_1"]]
                print("spins",spin_i)
                bath_freq,coupling,ddrf_tau,ddrf_amp,ddrf_phase_inc,n_rep_ddrf,ddrf_phase_init,ddrf_phase_read,pi2_2_MW_phase,reps_phase_inc=get_params(spin,state,ddrft,index)
                coupling=coupling + _I_['detuning']

                print("electron_init=",electron_init,"new_segment=",new_segment,"electron_init_in_loop=", electron_init_in_loop, "individual_segments=",individual_segments )
                print("params=",bath_freq,coupling,ddrf_tau,ddrf_amp,ddrf_phase_inc,ddrf_phase_init,ddrf_phase_read,pi2_2_MW_phase)

            
                def function():
                        if electron_init and not electron_init_in_loop:
                            sna.electron_init(mcas, _I_['state'], _I_['init_time_inter_ddrf'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .1, newsegment=True) #FIXME max_amp = 0.24

                        if new_segment:
                            print("new segment")
                            mcas.start_new_segment(f'ddrf_init_{spin}', loop_count=loop) #FIXME loop_count = 3
                        
                        if electron_init and electron_init_in_loop:
                            sna.electron_init(mcas, _I_['state'], _I_['init_time_inter_ddrf'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .1, newsegment=False) #FIXME max_amp = 0.24

                        mcas.asc(length_mus=0.256, gateMW=True, green = True)
                        sna.ddrf(mcas,
                            np.pi/2, # global_mw_phase
                            np.pi/2+pi2_2_MW_phase, # second_mw_phase
                            ddrf_phase_inc, # rf_phase_increment
                            0.0*reps_phase_inc, #rotation axis
                            #[increment_1,increment_2][spin_i], # rotation_axis
                            pi_dur, # pi electron
                            pi2_dur, # pi electron
                            coupling,  # detuning
                            bath_freq,  # bath freq
                            ddrf_tau,  # tau
                            n_rep_ddrf,  # n_rep_ddrf
                            ddrft,  # ddrft
                            trans[transition],  # mw freq
                            amp,  # mw amp
                            ddrf_amp,  # rf amp
                            constant_phase_offset=True,
                            )
                        sna.ddrf(mcas,
                            0, # global_mw_phase
                            0+pi2_2_MW_phase, # second_mw_phase
                            ddrf_phase_inc, # rf_phase_increment
                            #1.0*[increment_1,increment_2][spin_i]+np.pi/2, # rotation_axis
                            1.0*reps_phase_inc-np.pi/2, # rotation_axis
                            pi_dur, # pi electron
                            pi2_dur, # pi electron
                            coupling,  # detuning
                            bath_freq,  # bath freq
                            ddrf_tau,  # tau
                            n_rep_ddrf,  # n_rep_ddrf
                            ddrft,  # ddrft
                            trans[transition],  # mw freq
                            amp,  # mw amp
                            ddrf_amp,  # rf amp
                            pi2_1 = False, # pi half before DDRF
                            pi2_2 = False, # pi half after DDRF
                            constant_phase_offset=True,
                            )

                if individual_segments:
                    loop=1
                    for i in range(loops):
                        function()
                else:
                    loop=loops
                    function()

            
            def prepare(): #we create entanglement in ZZ basis here
                mcas.start_new_segment(name='Entangle_'+_I_["spin_1"])
                #pi/2 on spin1
                
                #DDRF Cnot spin1
                mcas.asc(length_mus=0.256, gateMW=True)
                sna.ddrf(mcas,
                    0, # global_mw_phase #phase around X
                    np.pi/2, # second_mw_phase #phase around Y
                    ddrf_phase_inc_1, # rf_phase_increment
                    2.0*reps_phase_inc_1, #increment_1, # rotation_axis
                    pi_dur, # pi electron
                    pi2_dur, # pi electron
                    coupling_1,  # detuning
                    bath_freq_1,  # bath freq
                    ddrf_tau_1,  # tau
                    n_rep_ddrf_1,  # n_rep_ddrf
                    _I_['ddrft'],  # ddrft
                    trans[transition],  # mw freq
                    amp,  # mw amp
                    ddrf_amp_1,  # rf amp
                    pi2_2=False, #Fasle, True
                    constant_phase_offset=True,
                    )
                

                mcas.start_new_segment(name='Entangle_'+_I_["spin_2"])
                # # pi/2 on spin2

                # DDRF Cnot spin2
                mcas.asc(length_mus=0.256, gateMW=True)
                sna.ddrf(mcas,
                    0, # global_mw_phase #phase around X
                    np.pi/2, # second_mw_phase #phase around Y
                    ddrf_phase_inc_2, # rf_phase_increment
                    2.0*reps_phase_inc_2, #increment_2, # rotation_axis
                    pi_dur, # pi electron
                    pi2_dur, # pi electron
                    coupling_2,  # detuning
                    bath_freq_2,  # bath freq
                    ddrf_tau_2,  # tau
                    n_rep_ddrf_2,  # n_rep_ddrf
                    _I_['ddrft'],  # ddrft
                    trans[transition],  # mw freq
                    amp,  # mw amp
                    ddrf_amp_2,  # rf amp
                    pi2_1=False,
                    pi2_2=False,
                    constant_phase_offset=True,
                    )
                
                mcas.start_new_segment(name='disentangle_electron')

                #cnot on spin1
                mcas.asc(length_mus=0.256, gateMW=True)
                sna.ddrf(mcas,
                    0, # global_mw_phase #phase around X
                    np.pi, # second_mw_phase #phase around Y
                    ddrf_phase_inc_1, # rf_phase_increment
                    _I_["y_phase_disentangle"], # rotation_axis
                    pi_dur, # pi electron
                    pi2_dur, # pi electron
                    coupling_1,  # detuning
                    bath_freq_1,  # bath freq
                    ddrf_tau_1,  # tau
                    n_rep_ddrf_1,  # n_rep_ddrf
                    _I_['ddrft'],  # ddrft
                    trans[transition],  # mw freq
                    amp,  # mw amp
                    ddrf_amp_1,  # rf amp
                    constant_phase_offset=True,
                    )
                
                #Rx(pi/2) on Spin1 -pi/2: 00+11 -> 01+10
                #rf_pulse(bath_freq_1 + coupling_1, amp=amps1['pi/2'], dur=dur1, phase=_I_["rf_phase_Y1_rabi"]-np.pi/2)
                #Rx(pi/2) on Spin2 -pi/2: 00+11 -> 01+10
                #rf_pulse(bath_freq_2 + coupling_2, amp=amps2['pi/2'], dur=dur2, phase=_I_["rf_phase_Y2_rabi"]-np.pi/2)
                #rf_pulse(bath_freq_2 + coupling_2, amp=_I_["test_rf_amp"], dur=dur2, phase=_I_["rf_phase_Y2_rabi"]-np.pi/2)
                

            def Rotate(direction):
                mcas.start_new_segment(name='rotate')
                dir1,dir2=direction
                if dir1=="Z":
                    rf_pulse(bath_freq_1 + coupling_1, amp=amps1['pi/2'], dur=dur1, phase=4*reps_phase_inc_1)#_I_["rf_phase_Y1_rabi"])
                    dir1="X"
                if dir2=="Z":
                    rf_pulse(bath_freq_2 + coupling_2, amp=amps2['pi/2'], dur=dur2, phase=3*reps_phase_inc_2)#_I_["rf_phase_Y2_rabi"])
                    dir2="X"

                return dir1+dir2
            
            def RO_DDRF(axis):
                mcas.start_new_segment(name='DDRF_RO_'+axis)
                dir1,dir2=axis
                #we do the conditional gate around x
                add1=0
                add2=0
                if dir1=="X":
                    add1=1
                    sna.ddrf(mcas,
                        _I_["global_MW_pi2_added_phase"], # global_mw_phase
                        _I_["MW_pi2_2_added_phase"], # second_mw_phase
                        ddrf_phase_inc_1, # rf_phase_increment
                        #ddrf_phase_init_1 + ddrf_phase_read_1, # rotation_axis
                        4*reps_phase_inc_1, #4 reps because of disentangling
                        pi_dur, # pi electron
                        pi2_dur, # pi electron
                        coupling_1,  # detuning
                        bath_freq_1,  # bath freq
                        ddrf_tau_1,  # tau
                        n_rep_ddrf_1,  # n_rep_ddrf
                        _I_['ddrft'],  # ddrft
                        trans[transition],  # mw freq
                        amp,  # mw amp
                        ddrf_amp_1,  # rf amp
                        constant_phase_offset=True,
                        )
                #we do the conditional gate around y
                elif dir1=="Y":
                    sna.ddrf(mcas,
                        _I_["global_MW_pi2_added_phase"], # global_mw_phase
                        _I_["MW_pi2_2_added_phase"], # second_mw_phase
                        ddrf_phase_inc_1, # rf_phase_increment
                        #ddrf_phase_init_1 + ddrf_phase_read_1, # rotation_axis
                        (4+add1)*reps_phase_inc_1+np.pi/2,
                        pi_dur, # pi electron
                        pi2_dur, # pi electron
                        coupling_1,  # detuning
                        bath_freq_1,  # bath freq
                        ddrf_tau_1,  # tau
                        n_rep_ddrf_1,  # n_rep_ddrf
                        _I_['ddrft'],  # ddrft
                        trans[transition],  # mw freq
                        amp,  # mw amp
                        ddrf_amp_1,  # rf amp
                        constant_phase_offset=True,
                        )
                    
                if dir2=="X":
                    add2=1
                    sna.ddrf(mcas,
                        _I_["global_MW_pi2_added_phase"], # global_mw_phase
                        _I_["MW_pi2_2_added_phase"], # second_mw_phase
                        ddrf_phase_inc_2, # rf_phase_increment
                        #ddrf_phase_init_2 + ddrf_phase_read_2, # rotation_axis
                        3*reps_phase_inc_2,
                        pi_dur, # pi electron
                        pi2_dur, # pi electron
                        coupling_2,  # detuning
                        bath_freq_2,  # bath freq
                        ddrf_tau_2,  # tau
                        n_rep_ddrf_2,  # n_rep_ddrf
                        _I_['ddrft'],  # ddrft
                        trans[transition],  # mw freq
                        amp,  # mw amp
                        ddrf_amp_2,  # rf amp
                        constant_phase_offset=True,
                        )
                    
                elif dir2=="Y":
                    sna.ddrf(mcas,
                        _I_["global_MW_pi2_added_phase"], # global_mw_phase
                        _I_["MW_pi2_2_added_phase"], # second_mw_phase
                        ddrf_phase_inc_2, # rf_phase_increment
                        #ddrf_phase_init_2 + ddrf_phase_read_2, # rotation_axis
                        (3+add2)*reps_phase_inc_2 + np.pi/2,
                        pi_dur, # pi electron
                        pi2_dur, # pi electron
                        coupling_2,  # detuning
                        bath_freq_2,  # bath freq
                        ddrf_tau_2,  # tau
                        n_rep_ddrf_2,  # n_rep_ddrf
                        _I_['ddrft'],  # ddrft
                        trans[transition],  # mw freq
                        amp,  # mw amp
                        ddrf_amp_2,  # rf amp
                        constant_phase_offset=True,
                        )
                    



            bath_freq_1,coupling_1,ddrf_tau_1,ddrf_amp_1,ddrf_phase_inc_1,n_rep_ddrf_1,ddrf_phase_init_1,ddrf_phase_read_1,pi2_2_MW_phase_1,reps_phase_inc_1=get_params(_I_["spin_1"],_I_["state"],_I_["ddrft"],_I_["file_index_1"],comment=_I_["comment"])
            coupling_1=coupling_1 + _I_['detuning']

            bath_freq_2,coupling_2,ddrf_tau_2,ddrf_amp_2,ddrf_phase_inc_2,n_rep_ddrf_2,ddrf_phase_init_2,ddrf_phase_read_2,pi2_2_MW_phase_2,reps_phase_inc_2=get_params(_I_["spin_2"],_I_["state"],_I_["ddrft"],_I_["file_index_2"],comment=_I_["comment"])
            coupling_2=coupling_2 + _I_['detuning']

            pi2_2_MW_phase_1=np.pi/2

                       
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
            
            
            mcas.start_new_segment('Seq', loop_count=3) #FIXME loop_count = 3
            #mcas.asc(length_mus=0.256, gateMW=True, green = True)
            #sna.electron_init(mcas, _I_['state'], _I_['init_time_inter_ddrf'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .15, newsegment=False) #FIXME max_amp = 0.24
            ddrf_init(_I_["spin_1"],_I_["state"],_I_["ddrft"],_I_["file_index_1"],loops=3,electron_init=_I_["Electron_init"],new_segment=_I_["new_segment"],electron_init_in_loop=_I_["Electron_init_in_loop"],individual_segments=_I_["individual_new_segment"])
            sna.electron_init(mcas, _I_['state'], _I_['init_time_inter_ddrf'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .15, newsegment=False) #FIXME max_amp = 0.24
            ddrf_init(_I_["spin_2"],_I_["state"],_I_["ddrft"],_I_["file_index_2"],loops=3,electron_init=_I_["Electron_init"],new_segment=_I_["new_segment"],electron_init_in_loop=_I_["Electron_init_in_loop"],individual_segments=_I_["individual_new_segment"])
            sna.electron_init(mcas, _I_['state'], _I_['init_time_inter_ddrf'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .15, newsegment=False) #FIXME max_amp = 0.24
 

            mcas.start_new_segment(name='rabi')
            if _I_['rf_dur_rabi']==-1:
                if "C" in _I_["spin_1"]:
                    dur1=400
                if "Si" in _I_["spin_1"]:
                    dur1=600
            else:
                dur1 = _I_['rf_dur_rabi']

            if _I_['rf_dur_rabi']==-1:
                if "C" in _I_["spin_2"]:
                    dur2=400
                if "Si" in _I_["spin_2"]:
                    dur2=600
            else:
                dur2 = _I_['rf_dur_rabi']

            print("dur1,dur2",dur1,dur2)
            amp1=[0.424,0.53]["C" in _I_["spin_1"]]
            amp2=[0.424,0.53]["C" in _I_["spin_2"]]
            amps1=[{"pi/2":0.223,"pi":0.450,"3pi/2":0.674},{"pi/2":0.234,"pi":0.471,"3pi/2":0.744}]["C" in _I_["spin_1"]] 
            amps2=[{"pi/2":0.223,"pi":0.450,"3pi/2":0.674},{"pi/2":0.234,"pi":0.471,"3pi/2":0.744}]["C" in _I_["spin_2"]]


            prepare() #entangle 2 nuclear spins

            axis=Rotate(_I_["Measure_state"])

            RO_DDRF(axis)

            #rf_pulse(bath_freq_1 + coupling_1, amp=_I_['rf_amp_rabi'], dur=dur1, phase=_I_["rf_phase_rabi"])

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
            ('n_vals', [4000]),
            ('bfield', [tesla]),
            ('t_read', [1.024 * 4]),
            ('state', ['-3/2']),
            ('init_time', [200]),
            ('init_time_inter_ddrf', [200]),
            ('n_ssr2', [3000]),
            ('n_ssr1', [3000]),
            ('init_nuc_state', ['1']),
            ('comment', ['testig_new_ddrft']),
            #("prepared_state", ["Z","-Z","X","-X"]),

            ("Tau_finder_tau_from_file", [0]),
            ('ddrft', ['xy4',"knillpi"]), #fid, hahn, xy4, xy8, xy16, knillpi, kdd4, kdd8, kdd16
            ('spin_1', ['C1']),
            ('spin_2', ["Si3","Si4"]),
            ("file_index_1",[-1]),
            ("file_index_2",[-1]),
            ('detuning', [0.]),
            ('rf_dur_rabi', [-1]),
            #('rf_amp_rabi', [0.2]),
            ('MW_pi2_2_added_phase', [0]),
            ('global_MW_pi2_added_phase', [np.pi/2]), # in RO DDRF
            ('individual_new_segment', [0]),
            ('new_segment', [1]),
            ('Electron_init', [0]),
            ('Electron_init_in_loop', [0]),
            ('rf_amp_rabi', [0.234]),
            #('rf_phase_Y1_rabi', [0.,np.pi/4,np.pi/2,3*np.pi/4,np.pi]),
            #("rf_phase_Y2_rabi",[0.,np.pi/4,np.pi/2,3*np.pi/4,np.pi]),
            #("y_phase_disentangle", [4.171]),# this is for nuc 2
            ("y_phase_disentangle", [2.13]),# this is for nuc 1 1.33
            #("y_phase_disentangle", [*np.linspace(0,np.pi*2,15)]),# this is for nuc 1
            #("rf_phase_increment", [*np.linspace(0,np.pi*2,15)]),# this is for nuc 1
            ("rf_phase_increment", ["None"]),# this is for nuc 1

            #("increment_1", [-0.85,-2.69]),#
            #("increment_2", [2.57]),# 
            #('Measure_state', ['II', 'IX', 'IY', 'IZ', 'XI', 'XX', 'XY', 'XZ', 'YI', 'YX', 'YY', 'YZ', 'ZI', 'ZX', 'ZY', 'ZZ']), 
            ('Measure_state', ['II', 'IX', 'IY', 'IZ', 'XI', 'YI', 'ZI', 'XX', 'XY', 'XZ', 'YX', 'YY', 'YZ', 'ZX', 'ZY', 'ZZ']), 
            #('Measure_state', ["II"]), #makes a ddrf gate on second nuclear spin
            #('rf_phase_Y1_rabi', [*np.linspace(0,np.pi*2,10)]),
            #('rf_phase_Y1_rabi', [*np.linspace(0,np.pi*2,10)]),
            #("rf_phase_Y2_rabi",[*np.linspace(0,np.pi*2,10)]),
            #("rf_phase_Y2_rabi",[*np.linspace(0,np.pi*2,10)]),
            #('test_rf_amp', [*np.linspace(0,0.9,10)]),
            #('rf_phase_rabi', [*np.linspace(0,np.pi*2,7)]),
            #("ddrf_RO_phase",[0.66]), #*np.linspace(0,np.pi*2,7)
            

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

    #1.92, 0.66