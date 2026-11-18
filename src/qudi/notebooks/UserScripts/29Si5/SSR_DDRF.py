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
            
            freq = trans[transition]

            dd_rabi_period = 2 * pi_dur
            dd_amp = amp


            # def electron rabi
            def cnot(amp, dur, freq,phase=0):
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
                    pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
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
            print(R_amp_read,L_amp_read, pi_dur_read)
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
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .15)
            
        # Start actual Sequence
            # Initialize weakly coupled
            mcas.start_new_segment('Seq', loop_count=1)
            mcas.asc(length_mus=0.256, gateMW=True, green = True)

            i=_I_["file_index"]

            #print(i,_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft'],tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft']))

            spin=tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), _I_['ddrft'],Tau_finder=_I_["Tau_finder_tau_from_file"],comment=_I_["comment"])
            print(spin)
            coupling = float(spin.detuning.iloc[i]) + _I_['detuning']
            
            bath_freq=[si_bath,c_bath]["C" in _I_['probe_spin']]

            if _I_['rf_amp_ddrf']==-1:
                ddrf_amp = float(spin.ddrf_amp.iloc[i])
            else:
                ddrf_amp=_I_['rf_amp_ddrf']

            if _I_['rf_phase_increment']=="file":
                ddrf_phase_inc = float(spin.ddrf_phase_inc.iloc[i])
            else:
                ddrf_phase_inc =float(_I_['rf_phase_increment'])

            print(tt.register.get_spin(_I_['probe_spin'], _I_['state'].replace('+',''), "knillpi",comment=_I_["comment"]).Azz.iloc[0],)


            if _I_['n_rep_ddrf']==-1:
                n_rep_ddrf = int(spin.n_rep_ddrf.iloc[i])
            else:
                n_rep_ddrf = _I_['n_rep_ddrf']

            # if _I_["ddrft"]=="xy4":
            #     n_rep_ddrf=10
            #     #ddrf_amp/=4
            # elif _I_["ddrft"]=="xy8":
            #     n_rep_ddrf=5
            #     #ddrf_amp/=8
            # elif _I_["ddrft"]=="kdd4":
            #     n_rep_ddrf=2
            #     #ddrf_amp/=16
            # elif _I_["ddrft"]=="kdd8":
            #     n_rep_ddrf=1
            #     #ddrf_amp/=32

            if _I_['tau']==-1:
                ddrf_tau = float(spin.ddrf_tau.iloc[i])/2
            elif _I_['tau']=="finder":
                ddt_N={"knillpi":5}

                df=spin

                sol_disc,sol_raw=tt.register.optimizer.get_best_tau(_I_['probe_spin'],N=ddt_N[_I_['ddrft']]*n_rep_ddrf, wL=bath_freq, Azz=df.Azz.iloc[0],drive_freq= df.trans.iloc[i], solution_number=[_I_["finder_solution_number"]])

                ddrf_tau= sol_disc[0]["tau_raw"] #or tau_disc

            else:
                ddrf_tau = _I_['tau']

            #ddrf_phase_inc-=_I_['detuning']*ddrf_tau

            print(coupling,bath_freq,ddrf_amp,ddrf_phase_inc,n_rep_ddrf,ddrf_tau*2)

            #print(_I_['bath_freq',_I_['coupling']],_I_['rf_phase_increment'],_I_['rf_amp_ddrf'])
            print("ddrf_tau=",ddrf_tau, "n_rep_ddrf",n_rep_ddrf)


            rot_axis=_I_["rot_axis"]

            print("code_phase_inc ",ddrf_phase_inc)

            for i in range(_I_["reps"]):
                #mcas.asc(length_mus=0.256, gateMW=True)
                sna.ddrf(mcas,
                    0, # global_mw_phase
                    _I_['phase_pi2_2']*[0,1][i==(_I_["reps"]-1)]+_I_["phase_pi2_2_offset"], # second_mw_phase
                    ddrf_phase_inc, # rf_phase_increment
                    i*rot_axis, # rotation_axis
                    pi_dur+_I_["MW_dur_add"], # pi electron
                    pi2_dur, # pi electron
                    coupling,  # detuning
                    bath_freq,  # bath freq
                    ddrf_tau,  # tau
                    n_rep_ddrf,  # n_rep_ddrf
                    _I_['ddrft'],  # ddrft
                    trans[transition],  # mw freq
                    amp,  # mw amp
                    ddrf_amp+_I_["rf_amp_ddrf_add"],  # rf amp
                    MW_phase_increment=_I_["MW_phase_increment_1"],
                    padding=True,
                    
                    pi2_1 = True, # pi half before DDRF
                    pi2_2 = True, # pi half after DDRF
                    #include_pi_dur_in_tau=False,
                    #optimze_rf_usage=True,
                    #MW_open=_I_["MW_open"],
                    #rf_phase_offset=_I_["rf_phase_offset"],
                    constant_phase_offset=True,
                    #measurements=[_I_["rf_index"], _I_["fraction"], _I_['phase_pi2_2']]
                    )

            #sna.wait_no_new_segment(mcas,_I_["time"]/4)
            #cnot(amp, pi_dur,freq)
            #sna.wait_no_new_segment(mcas,_I_["time"]/2)
            #cnot(amp, pi_dur,freq)
            #sna.wait_no_new_segment(mcas,_I_["time"]/4)

            # sna.ddrf(mcas,
            #     0, # global_mw_phase
            #     _I_['phase_pi2_2']+_I_["phase_pi2_2_offset"], # second_mw_phase
            #     ddrf_phase_inc, # rf_phase_increment
            #     _I_["rot_axis"], # rotation_axis
            #     pi_dur+_I_["MW_dur_add"], # pi electron
            #     pi2_dur, # pi electron
            #     coupling,  # detuning
            #     bath_freq,  # bath freq
            #     ddrf_tau,  # tau
            #     n_rep_ddrf,  # n_rep_ddrf
            #     _I_['ddrft'],  # ddrft
            #     trans[transition],  # mw freq
            #     amp,  # mw amp
            #     ddrf_amp,  # rf amp
            #     MW_phase_increment=_I_["MW_phase_increment_1"],
            #     padding=True,
            #     #include_pi_dur_in_tau=True,
            #     #optimze_rf_usage=True,
            #     #MW_open=_I_["MW_open"]
            #     )
            
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
    nuclear.do_ple_refocusA2 =  True

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
            ('t_read', [1.024 * 4]),
            ('state', ['-3/2']),
            ('n_vals', [1000]),
            ('init_time', [300]),
            ('n_ssr2', [3000]),
            ('n_ssr1', [3000]),
            ("Bfield", [tesla_z]),
            ('bath_freq_c', [c_bath]),
            ('bath_freq_Si', [si_bath]),
            ('reps', [4,6]), #,4,6,8,10
            ('ddrft', ["knillpi","xy4"]), #fid, hahn, xy4, xy8, xy16, knillpi, kdd4, kdd8, kdd16
            ('probe_spin', ["Si3","Si4","C1"]),
            ('init_nuc_state', ['1']),
            ("Tau_finder_tau_from_file",[1]),
            ("comment",["testig_new_ddrft"]),#reserved_for_tau_finder
            ('n_rep_ddrf', [2]),#*range(2,21,2)
            #('coupling', [-0.03314,*np.round(np.arange(-0.02,0.013,0.0005),4)]),
            #("phase_pi2_2_offset",[*np.linspace(0,2*np.pi,10)]),
            ("phase_pi2_2_offset",[0.0]),
            ('phase_pi2_2', [0.,np.pi/2]),
            #('tau', [18.73]),
            #('tau', [41.2/2]),
            ('tau', [-1]),
            #('tau', [*np.linspace(15,30,15)]),
            #("MW_phase_increment_1", [*np.linspace(0+1,2*np.pi+1,20)]),
            ("MW_phase_increment_1", [0]),
            ("file_index",[-1]),
            #('rf_phase_increment', [0.1,1.7]), #si9
            #('rf_phase_increment', [0.]), #si6
            ('rf_phase_increment', ["file"]),# 0.42,3.24,4.99,5.91]),
            #('rf_phase_increment', [*np.linspace(0.,2,15)]),#*np.linspace(-np.pi,np.pi,30)
            #('rot_axis', [*np.linspace(-np.pi,np.pi,20)]),#
            #('rot_axis', [2.05]),#*np.linspace(-np.pi,np.pi,30)
            ('rot_axis', [2.67]),#*np.linspace(-np.pi,np.pi,30)#*np.linspace(-np.pi,np.pi,15)
            ("MW_dur_add", [0.]),#,*np.linspace(-0.005,0.005,6)]),
            #('MW_open', [*np.arange(0.05,0.2,0.02)]),#*np.linspace(-np.pi,np.pi,30)
            ('MW_open', [0.128]),#*np.linspace(-np.pi,np.pi,30)
            #('time', [0.,20.,100]),
            #('const_phase_offset', [False]), #follow the ddrf line = set to False
            #('rf_amp_ddrf', [0.66]),
            #('rf_amp_ddrf', [*np.linspace(0.1,1,10)]), #Si5
            #('n_rep_ddrf', [*range(2,20)]),
            ('rf_amp_ddrf', [-1]),
            #('rf_amp_ddrf', [*np.linspace(0,.9,10)]), 
            #('rf_amp_ddrf_add', [*np.linspace(-0.05,.05,5)]), 
            ('rf_amp_ddrf_add', [0.]), 
            #('detuning', [*np.linspace(-.05,0.05,50)]),
            ('init_power', [0.15]),
            ('detuning', [0.]),
            #('rf_phase_offset', [*np.linspace(0,np.pi*2,15)]),
            ('rf_phase_offset', [0]),
            #('phase_pi2_2', [*np.linspace(0,np.pi*2,10)]),
            #('rf_index', [*range(0,11)]),
            #('fraction', [*np.linspace(0,1,10)]),

            #('phase_pi2_2', [0.]),
            #('phase_pi2_2', [0.,np.pi]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 1


def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 7 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    #nuclear.pld.fit_function = 'lorentz'
    settings()
    print('run_fun started')
    nuclear.run(abort)