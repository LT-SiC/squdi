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
            state = {'L': '-3/2', 'C': '-1/2', 'R': '+3/2'}[_I_['trans']]
            ### ELECTRON RABI PARAMETERS ### #for SSR
            trans_idx = _I_['init_nuc_state']
            transition = _I_['trans'][0]+trans_idx
                
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(state, si_bath)
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition,fast=True,middle=False)

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
                    pulseshape= 'sinehermite'
                )

            def rf_pulse(freq, amp=None, dur=None, phase=0):
                amp = si1_amp if amp is None else amp
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1', gateRF = True)
                if dur is None:
                    dur = si1_pi
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    gateRF = True,
                    pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
                           "phase_type_offset": 'coherent'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)

        # Nuclear Init
            sna.repump(mcas, dur = 50)
            sna.electron_init(mcas, state, _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(trans_idx,weak=True)
            cnot([R_amp_read, L_amp_read]["L" in transition], pi_dur_read, trans[transition])
            rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)

            

            ### READOUT ###
            if trans_idx == '1':
                ssr_freqs=[trans['L2'], trans['R2']]
                read_idx = '2'
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                read_idx = '1'

            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(read_idx,weak=True)

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
                    length_mus_mw=pi_dur_read,
                    amplitudes=[L_amp_read, R_amp_read],
                    repetitions=int(_I_['n_ssr1'])
                    )
        
        # Electron init
            sna.electron_init(mcas, state, _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .2)

            #if abs(_I_["freq"])>2.5: # to see both peaks
            #    rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)

            #sna.electron_init(mcas, state, _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .2)

        # rabi
            mcas.start_new_segment('Rabi', loop_count=_I_["rabi_loops"])
            print("t=",t)
            if _I_["dur"]<0:
                if _I_["pulse"]=="pi":
                    dur = pi_dur
                elif _I_["pulse"]=="pi2":
                    dur =pi2_dur
            else:
                dur=_I_["dur"]

            if _I_["amp"]<0:
                amp=amp
            else:
                amp=_I_["amp"]

            print("dur for amp",dur,amp)

            if _I_["driving"]=="both":
                freq1 = trans[transition.replace("2","1")]
                freq2 = trans[transition.replace("1","2")]
            elif _I_["driving"]=="middle":
                freq=(trans[transition.replace("1","2")]+trans[transition.replace("2","1")])/2+_I_["freq"]
            else:
                freq = trans[transition]+_I_["freq"]

            #print(freq)

            #amp=[R_amp_read, L_amp_read]["L" in transition]
            #dur=pi_dur_read
            #if abs(_I_["freq"])>2.5:
            #freq = trans[transition.replace("1","3").replace("2","1").replace("3","2")]+_I_["freq"]

            #print(freq)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_["mw_open"]), gateMW=True)
            for i in range(_I_["for_rabi_loops"]):
                mw_close=_I_["mw_close"]
                mw_open=_I_["mw_open"]#dur+_I_["rabi_add"]+0.202 #+20ns

                #mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(mw_close), gateMW=False)
                #mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(mw_open), gateMW=True)

                if _I_["driving"]=="both":
                    sna.electron_rabi(
                            mcas,
                            new_segment=False,
                            gateMW=False,
                            length_mus=E.round_length_mus_to_x_multiple_ps(dur+_I_["rabi_add"]),
                            amplitudes=[amp/2,amp/2],
                            frequencies=[freq1,freq2],
                            mixer_deg=[-90,-90],
                            pulseshape=_I_['pulseshape']
                        )
                else:
                    sna.electron_rabi(
                            mcas,
                            new_segment=False,
                            gateMW=True,
                            length_mus=E.round_length_mus_to_x_multiple_ps(dur+_I_["rabi_add"]),
                            amplitudes=[amp],
                            frequencies=[freq],
                            mixer_deg=[-90],
                            pulseshape=_I_['pulseshape']
                        )

            #print(_I_["add_dur"],pi_dur,pi2_dur)

            # if _I_["stepped_index"]>=1:
            #     sna.electron_rabi(
            #         mcas,
            #         new_segment=False,
            #         gateMW=True,
            #         length_mus=E.round_length_mus_to_x_multiple_ps(pi2_dur+_I_["add_dur"],1),
            #         amplitudes=[amp],
            #         frequencies=[freq],
            #         mixer_deg=[-90],
            #         pulseshape=_I_['pulseshape']
            #     )

            # if _I_["stepped_index"]>=2:
            #     sna.electron_rabi(
            #         mcas,
            #         new_segment=False,
            #         gateMW=True,
            #         length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur,1),
            #         amplitudes=[amp],
            #         frequencies=[freq],
            #         mixer_deg=[-90],
            #         pulseshape=_I_['pulseshape']
            #     )

            # if _I_["stepped_index"]>=3:
            #     sna.electron_rabi(
            #         mcas,
            #         new_segment=False,
            #         gateMW=True,
            #         length_mus=E.round_length_mus_to_x_multiple_ps(pi2_dur,1),
            #         amplitudes=[amp],
            #         frequencies=[freq],
            #         mixer_deg=[-90],
            #         pulseshape=_I_['pulseshape']
            #     )

            mcas.start_new_segment('RO', loop_count=1)
            if 'C' in _I_['trans']:
                #amp_project, pi_dur_project, pi2_dur = sna.get_hardcoded_e_values_for_control("L1")
                #amp_project2, pi_dur_project, pi2_dur = sna.get_hardcoded_e_values_for_control("L2")

                amp_project, pi_dur_project, pi2_dur = sna.get_hardcoded_e_values_for_control("R"+trans_idx)

                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
                sna.electron_rabi(
                    mcas,
                    new_segment=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                    gateMW = True,
                    amplitudes=[amp_project/2,amp_project/2],
                    frequencies=[trans['R1'],trans['R2']],
                    mixer_deg=[-90,-90]
                )
            
            # if abs(_I_["freq"])>2.5: # revert back
            #     rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)

            
            rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)
        
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
        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements, n_vals = 1000)

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
        ['init', '<', 9, 0, 0, 1],
        ['result', '>', 9, 0, 0, 1], # Put "int(_I_['n_ssr']" as nlp_per_point?
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

    nuclear.ple_refocus_interval = 300 # 3 mins?
    nuclear.confocal_refocus_interval = 1800  # seconds
    nuclear.odmr_refocus_interval = 6000
    nuclear.follow_resonnance_by_counts=False

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    Tesla=0.2089
    c_bath = 10.705*Tesla
    si_bath = -8.465*Tesla
    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('A2_power', [6]),
            ('t_read', [1.024*3]),
            ('n_ssr1', [3000]),
            ('n_ssr2', [3000]),
            ('period', [1.5]),#.78 #not used
            ("driving",["fast"]),
            ("init_nuc_state",["1"]),
            ('trans', ["L","R"]),
            #('amp', [0.95]),
            ('init_time', [500]),#np.linspace(20,301,7)
            ('pulseshape', ['sinehermite']),
            #('amp', [0.215]),#*np.linspace(0.1,1.,5)
            ('dur', [-1]), #0.458
            #('rabi_loops', [5,10,15,20,25,30]), #0.458
            #('rabi_loops', [*range(1,40,4)]), #0.458
            ('rabi_loops', [1]), #0.458
            ('for_rabi_loops', [1]), #0.458
            ('mw_close', [0.]), #0.458
            ('mw_open', [0.128]), #0.458

            ("stepped_index",[2]),
            #("add_dur", E.round_length_mus_to_x_multiple_ps(np.arange(-0.005,0.006,0.001),1)),#np.arange(-0.004,0.005,0.001)
            #('amp', [*np.linspace(0.1,1.,35)]),
            #('amp', [0.,*np.arange(0.08,.2,0.01)]),
            ('amp', [1.]),#*np.linspace(0.1,1.,5) *np.linspace(0.10,0.4,20)
            #('dur', [0.,*np.linspace(0.140,0.160,11)]),#*np.linspace(0,3,30)
            ('pulse', ["pi2"]),#*np.linspace(0,3,30) ,"pi2"
            ('dur', [*np.arange(0.,0.265*1,0.015)]),#*np.linspace(0,3,30)
            #('dur', [*np.arange(0.070,0.10,0.002)]),#*np.linspace(0,3,30)
            #('dur', [0.1]),#*np.linspace(0,3,30)

            #('rabi_correction', np.linspace(-0.005,0.005,11)),#*np.linspace(0,3,30)
            #('rabi_add', [*np.linspace(-0.008,-0.002,7)]),#*np.linspace(0,3,30)
            ('rabi_add', [0.]),#*np.linspace(0,3,30)
            #('dur', [0.126]),#*np.linspace(0,3,30)
            #('freq',np.linspace(-10.,10,50)), #for ODMR
            #('freq',[-4.81,0.,4.81]),#np.linspace(-8,8,70)), -4.81,0,4.81 #for ODMR
            ('freq',[0.]),#np.linspace(-8,8,70)), -4.81,0,4.81 #for ODMR
        )
    )
    nuclear.number_of_simultaneous_measurements = 1

def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 5 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    nuclear.pld.fit_function='cosine'
    settings()
    print('run_fun started')
    nuclear.run(abort)