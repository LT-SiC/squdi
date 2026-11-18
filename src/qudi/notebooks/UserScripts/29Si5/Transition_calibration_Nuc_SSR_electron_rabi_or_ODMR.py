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
from PyQt5 import QtTest

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
            state = {'L': '-1/2', 'C': '-1/2', 'R': '+3/2'}[_I_['trans']]
            ### ELECTRON RABI PARAMETERS ### #for SSR
            trans_idx = _I_['init_nuc_state']
            transition = _I_['trans'][0]+trans_idx
                
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(state, si_bath)
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition,fast=False)
            # def electron rabi
            def cnot(amp, dur, freq,phase=-90):
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
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    gateRF = True,
                    pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
                           "phase_type_offset": 'coherent'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)

        # Nuclear Init
            sna.repump(mcas, dur = 50)
            sna.electron_init(mcas, state, _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = _I_["init_amp"])
            cnot(amp, pi_dur, trans[transition])
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
            sna.electron_init(mcas, state, _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = _I_["init_amp"])
        
        # rabi
            mcas.start_new_segment('Rabi', loop_count=1)
            #print("t=",t)
            if _I_["dur"]<0:
                dur = pi_dur_read#self.queue.tt.RP('e_rabi_ou350deg-90-'+transition, period=_I_['period']).pi
            else:
                dur=_I_["dur"]

            if _I_["amp"]<0:
                amp=[L_amp_read,R_amp_read]["R" in transition]#self.queue.tt.RP('e_rabi_ou350deg-90-'+transition, period=_I_['period']).amp
            else:
                amp=_I_["amp"]

            print(dur,amp)


            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
            freq = trans[transition]+_I_["freq"]
            #freq = (trans['R1']+trans['R2'])/2+_I_["freq"]
            
            sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur*5),
                    amplitudes=[amp/5],
                    frequencies=[freq],
                    mixer_deg=[-90],
                    pulseshape=_I_['pulseshape']
                )
            
            
            if 'C' in _I_['trans']:
                #amp_project = self.queue.tt.RP('e_rabi_ou350deg-90-R'+trans_idx, period=_I_['period']).amp
                #pi_dur_project = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-R'+trans_idx, period=_I_['period']).pi)
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

            print(state)
            
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(state, si_bath) #state.replace("3","4").replace("1","3").replace("4","1") #_I_["RO_state"]

            rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)

            ### READOUT  ###
            if trans_idx == '2':
                ssr_freqs=[trans['L2'], trans['R2']]
                read_idx = '2'
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                read_idx = '1'
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(read_idx,weak=True)

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
        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements, n_vals = 500)

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
        ['init', '<', 10, 0, 0, 1],
        ['result', '>', 10, 0, 0, 1], # Put "int(_I_['n_ssr']" as nlp_per_point?
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

    nuclear.ple_refocus_interval = 300 # 3 mins?
    nuclear.confocal_refocus_interval = 1800  # seconds
    nuclear.odmr_refocus_interval = 6000
    nuclear.follow_resonnance_by_counts=False

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15○
    Tesla=0.2089
    c_bath = 10.705*Tesla
    si_bath = -8.465*Tesla
    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(1)),
            ('A2_power', [6]),
            ('t_read', [1.024*4]),
            ('n_ssr1', [2000]),
            ('n_ssr2', [2000]),
            ("init_amp", [0.1]),
            ("init_nuc_state",["2"]),
            ('period', [1.8]),#.78
            ('trans', ["L","C","R"]),
            #('amp', [0.95]),
            ('init_time', [50]),#np.linspace(20,301,7)
            ('pulseshape', ['sinehermite']),
            #('dur', [0.458]), #0.458
            ('amp', [-1]),#*np.linspace(0.1,1.,5)
            ('dur', [-1]),#*np.linspace(0,3,30)
            #('freq',np.linspace(-2.5,2.5,50)), #for ODMR
            #('freq',[*np.linspace(-2,2,20)]),#np.linspace(-8,8,70)), #for ODMR
            ('freq',[*np.arange(-2,2,0.2)]),#np.linspace(-8,8,70)), #for ODMR
            #("RO_state", ["-3/2","-1/2","+3/2"])
        )
    )
    #L 0.15=.230 µs
    #R 0.15=0.422
    nuclear.number_of_simultaneous_measurements = 1

def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 3 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    nuclear.pld.fit_function='lorentz'
    settings()
    print('run_fun started')
    nuclear.run(abort)

    
    while not hasattr(nuclear, '_state'):
        QtTest.QTest.qSleep(100)
    print('========\n Finished waiting for state\n ======')  # t
    while nuclear.state == 'run':
        QtTest.QTest.qSleep(100)
    print('========\n Finished waiting for run\n ======')  # t
    try:
        #todo - fit and set mw_mixing_frequency here!!!!
        nuclear.pld.x_axis_parameter_list.update_selected_value('freq')
        nuclear.pld.average_parameter_list.update_selected_data(['sweeps'])
        nuclear.pld.observation_list.update_selected_data(['result_0'])
        QtTest.QTest.qSleep(1000)
        print('result_0 selected')
        nuclear.pld.update_plot()  # (hit the plot button!)
        QtTest.QTest.qSleep(1000)
        nuclear.pld.update_plot_fit() # (hit the fit button!)
        QtTest.QTest.qSleep(1000)
        nuclear.center_positions = nuclear.pld.data_fit_results.df['center'] #save the center positions of lorentzian.
        print(' Nuclear finished!!!\n', nuclear.center_positions)
        #print("trans = {'L1': ", trans['L1']+nuclear.center_positions[0], ", 'L2': ", trans['L2']+nuclear.center_positions[0], ", 'C1': ", trans['C1']+nuclear.center_positions[1], ", 'C2': ", trans['C2']+nuclear.center_positions[1], ", 'R1': ", trans['R1']+nuclear.center_positions[2], ", 'R2': ", trans['R2']+nuclear.center_positions[2], "}")
        # peak fitting is done in order of alphabet, not order of parameters['trans']
        print(nuclear.queue.tt.mw_mixing_frequency_L,nuclear.queue.tt.mw_mixing_frequency_C,nuclear.queue.tt.mw_mixing_frequency_R)

        nuclear.queue.tt.mw_mixing_frequency_L += nuclear.center_positions[1]
        nuclear.queue.tt.mw_mixing_frequency_C += nuclear.center_positions[0]
        nuclear.queue.tt.mw_mixing_frequency_R += nuclear.center_positions[2]
    except Exception as e:
        print("well, it didn't work, better luck next time :)\nerror:",e)