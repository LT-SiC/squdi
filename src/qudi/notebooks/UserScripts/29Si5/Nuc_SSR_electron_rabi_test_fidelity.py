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
            
            init_nuc_state=_I_["init_nuc_state"]
            neg_init_nuc_state=["1","2"][_I_["init_nuc_state"]=="1"]
            state = {'L': 'm32', 'C': 'm12', 'R': 'p32'}[_I_['trans']]

            #nucear control parameters
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(state.replace("m","-").replace("p","+").replace("2","/2"), si_bath)

            ### ELECTRON RABI PARAMETERS ###
            transition= _I_["trans"] + _I_["init_nuc_state"]
            # amp = self.queue.tt.RP('e_rabi_ou350deg-90-'+transition, omega=_I_['omega']).amp
            # pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-'+transition, omega=_I_['omega']).pi,1)
            # pi2_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-'+transition, omega=_I_['omega']).pi2,1)

            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition,pulseshape=_I_["pulseshape"],fast=_I_["driving"]=="fast",middle=_I_["driving"]=="middle")
            print(transition,pi_dur,pi2_dur)


            # if _I_["use_hardcoded_values"]:
            #     #### if we want to check the hardcoded values _I_["omega"] is omited here
            #     amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition)


            if _I_["dur"]>0:
                dur=_I_["dur"]
            else:
                if _I_["N_pi2"]>0:
                    dur=pi2_dur
                    reps=_I_["N_pi2"]

                else: #assume the standard is to test pi pulses
                    dur=pi_dur
                    reps=_I_["N_pi"]

            if _I_["amp"]>0:
                amp=_I_["amp"]


            amp=max(0,min(1,amp+_I_["amp_offset"])) #coerce min and max amp
            #print(amp)

            print(amp,dur,transition)

            dur=dur+_I_["dur_offset"]

            print(amp,dur,transition)

            # def electron rabi
            def cnot(amp, dur, freq, phase=-90):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    amplitudes=[amp],
                    frequencies=[freq],
                    mixer_deg=[phase],
                    pulseshape= 'sinehermite'
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

        # Nuclear Init
            sna.repump(mcas, dur = 100) #made it longer so the PLE line is at a better position
            sna.electron_init(mcas, state, _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(si1_freq)

            #SSR stuff
            ampL = self.queue.tt.RP('e_rabi_ou350deg-90-L'+neg_init_nuc_state, omega=_I_['omega']).amp
            ampR = self.queue.tt.RP('e_rabi_ou350deg-90-R'+neg_init_nuc_state, omega=_I_['omega']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(
                self.queue.tt.RP('e_rabi_ou350deg-90-L'+neg_init_nuc_state, omega=_I_['omega']).pi,8)
            
            ampR, ampL, pi_durL, pi2_durL = sna.get_hardcoded_e_values_for_readout(_I_["init_nuc_state"],weak=True)
        
            if _I_["init_nuc_state"]=="1":
                print("ssr on 2 to init on 1 (dark)")
                ssr_freqs=[trans['L2'], trans['R2']]
            else:
                print("ssr on 1 to init on 2 (dark)")
                ssr_freqs=[trans['L1'], trans['R1']]

            print("freqs=",ssr_freqs)

        # SSR 1
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A1',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
                    repetitions=int(_I_['n_ssr1'])
                    )
        
        # Electron init
            sna.electron_init(mcas, state, _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
        
        # rabi
            
            #transition="C"+ _I_["init_nuc_state"] #HARDCODE FOR TESTINNG CAN BE DELETED
            t=transition#["L","R"]["p" in _I_["state"]]+["1","2"][_I_["init_nuc_state"]!="2"]
            driven_freq= trans[t]+_I_["freq"]
            driven_freq=driven_freq + _I_["hyp_error"]*[-1,1]["2" in t] # increase the splitting

            print("t=",t)

            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
            if type(reps)==type(1):# ie it is an int
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
                if reps!=0:
                    mcas.start_new_segment('Rabi_loop', loop_count=reps)
                    sna.electron_rabi(
                            mcas,
                            new_segment=False,
                            gateMW=True,
                            length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                            amplitudes=[amp],
                            frequencies=[driven_freq],
                            mixer_deg=[-90],
                            pulseshape= _I_["pulseshape"]
                        )
                

            else:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
                if int(reps)>0:
                    mcas.start_new_segment('Rabi_loop', loop_count=int(reps))
                    sna.electron_rabi(
                            mcas,
                            new_segment=False,
                            gateMW=True,
                            length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                            amplitudes=[amp],
                            frequencies=[driven_freq],
                            mixer_deg=[-90],
                            pulseshape= _I_["pulseshape"]
                        )
                    
                if E.round_length_mus_to_x_multiple_ps(dur*(reps-int(reps)))> 0:
                    mcas.start_new_segment('Rabi_loop_correction', loop_count=1)
                    sna.electron_rabi(
                            mcas,
                            new_segment=False,
                            gateMW=True,
                            length_mus=E.round_length_mus_to_x_multiple_ps(dur*(reps-int(reps))),
                            amplitudes=[amp],
                            frequencies=[driven_freq],
                            mixer_deg=[-90],
                            pulseshape= _I_["pulseshape"]
                        )
                    
            mcas.start_new_segment('readout', loop_count=1)
            if 'C' in transition:
                #amp_project = self.queue.tt.RP('e_rabi_ou350deg-90-R2', period=_I_['period']).amp
                #pi_dur_project = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-R', period=_I_['period']).pi)

                amp1, dur1, pi2_dur1 = sna.get_hardcoded_e_values_for_control("R1")
                amp2, dur2, pi2_dur2 = sna.get_hardcoded_e_values_for_control("R2")

                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
                sna.electron_rabi(
                    mcas,
                    #new_segment=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur1),
                    gateMW = True,
                    amplitudes=[amp1],
                    frequencies=[trans['R1']],
                    mixer_deg=[-90]
                )
                sna.electron_rabi(
                    mcas,
                    #new_segment=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur2),
                    gateMW = True,
                    amplitudes=[amp2],
                    frequencies=[trans['R2']],
                    mixer_deg=[-90]
                )

            #cnot(amp, pi_dur, trans[transition.replace("2","1")])
            #cnot(amp, pi_dur, trans[transition.replace("1","2")])
            
            rf_pulse(si1_freq,phase=_I_["readout_phase"])
        
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
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
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
        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)

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
    nuclear.do_confocal_A1A2_refocus = False
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.do_repump = False
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 60*60 # 3 mins?
    nuclear.confocal_refocus_interval = 3000  # seconds
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
            ('sweeps', range(1)),
            ('A2_power', [6]),
            ('n_ssr1', [2000]),
            ('n_ssr2', [2000]),
            ("init_nuc_state",['1', '2']),
            ("use_hardcoded_values",[0]),
            #('omega', [0.8,0.6,0.4,0.2]),#1.7
            ('omega', [0]),#1.7
            ('rf_amp', [0.24]),
            ("pulseshape", ["sinehermite"]),
            ("driving",["fast"]), #normal=use one freq with pi pulses tat mostly do not affect the other nuc spin transition, fast= to use for max amp on one transtion. middle= drive with max amp between the two nuc transitions. both = drive both 1 and 2 transitions at the same time with pulses that ry not to interfere with the other nuc transition
            ('amp', [-1]),#np.linspace(0.5,1,3)[::-1]
            ('trans', ["R"]),
            ('init_time', [200]),#np.linspace(20,301,7)
            ('t_read', [1.024*3]),
            ('dur', [-1]),#np.linspace(0,3,90)
            #("N_pi",[*np.linspace(0.5,3.5,30)]), #*range(1,8) #*np.linspace(0.5,2.5,50)
            ("N_pi",[*range(0,16,4)]),
            ("N_pi2",[-1]),
            ("freq",[0.]),#np.linspace(-8,8,200) #for ODMR
            #("hyp_error", [*np.linspace(-0.1,0.1,20)]),
            ("hyp_error", [0]),
            ("amp_offset",[0]), #for better calibration (especially for hardcoded)
            #("amp_offset",[*np.linspace(0,-0.05,10)]), #for better calibration (especially for hardcoded)
            #("dur_offset", [0]),
            ("dur_offset", [*np.linspace(-0.010,0.01,20)]), ##for better calibration (especially for hardcoded) #*np.linspace(-0.05,-0.01,5)[:-1],*np.linspace(-.01,.01,10),*np.linspace(.01,0.05,5)[1:]
            ('readout_phase', [0.])
        )
    )
    nuclear.number_of_simultaneous_measurements = 1

def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    nuclear.pld.fit_function='cosine'
    settings()
    print('run_fun started')
    nuclear.run(abort)