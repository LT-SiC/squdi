# coding=utf-8
import datetime
import numpy as np
import os
import importlib
import notebooks.UserScripts.helpers.sequence_creation_helpers as sch; importlib.reload(sch)
import notebooks.UserScripts.helpers.shared as shared
from hardware.Keysight_AWG_M8190.pym8190a import MultiChSeq as MultiChSeq
import notebooks.UserScripts.helpers.snippets_awg as sna
importlib.reload(sna)
importlib.reload(shared)
#importlib.reload(MultiChSeq)
import notebooks.UserScripts.helpers.shared as ush;importlib.reload(ush)
from logic.qudip_enhanced import *
import hardware.Keysight_AWG_M8190.elements as E
from collections import OrderedDict
from PyQt5 import QtTest


seq_name = os.path.basename(__file__).split('.')[0]
nuclear = sch.create_nuclear(__file__)
with open(os.path.abspath(__file__).split('.')[0] + ".py", 'r') as f:
    meas_code = f.read()

__TAU_HALF__ = 2*192/12e3
__SAMPLE_FREQUENCY__ = 12e3#e.__SAMPLE_FREQUENCY__

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        
        sequence_name = 'Transition_calibration' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():
            if _I_['trans'] == 'L':
                amp = self.queue.tt.rp('e_rabi_ou1800deg-90-L', omega=_I_['omega']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou1800deg-90-L', omega = _I_['omega']).pi)
                #freq = 98.32 + _I_['mw_freq']
                freq = self.queue.tt.mw_mixing_frequency_L + _I_['mw_freq']
            elif _I_['trans'] == 'C': # UNFUG! Wrong files, change L to R
                amp = self.queue.tt.rp('e_rabi_ou1800deg-90-L', omega=_I_['omega']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou1800deg-90-L', omega = _I_['omega']).pi)
                #freq = 98.32+139/2 + _I_['mw_freq']
                freq = self.queue.tt.mw_mixing_frequency_C + _I_['mw_freq']
            else:
                amp = self.queue.tt.rp('e_rabi_ou1800deg-90-L', omega=_I_['omega']).amp # UNFUG! Wrong files, change L to R
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou1800deg-90-L', omega = _I_['omega']).pi)
                #freq = 98.32+139 + _I_['mw_freq']
                freq = self.queue.tt.mw_mixing_frequency_R + _I_['mw_freq']
            
            sna.repump(mcas, 50)

            init_state = {'L': '-0.5', 'C': '-0.5', 'R': '+0.5', }[_I_['trans']]
            mi = {'n':[-0.5,0.5], '-':[-0.5], '+':[0.5]}

            td = {}
            nucs = []
            for ii, nuci in enumerate(nucs):
                td[nuci] = mi[init_state[ii]]

            ### INITIALIZATION ###
            #sna.electron_init(mcas, init_state, _I_["init_time"], [98.32], [98.32+139])
            sna.electron_init(mcas, init_state, _I_["init_time"], [self.queue.tt.mw_mixing_frequency_L], [self.queue.tt.mw_mixing_frequency_R])

            t = _I_['trans']
            #, "C": (trans['C1']+trans['C2'])/2, "R": (trans['R1']+trans['R2'])/2}[_I_['trans']]+_I_['mw_freq']

            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                gateMW = True,
                amplitudes=[amp],
                frequencies=[freq],
                mixer_deg=[-90]
            )

            if 'C' in _I_['trans']:
                amp_project = self.queue.tt.rp('e_rabi_ou1800deg-90-L', omega = _I_['omega']).amp
                #print(amp_project)
                pi_dur_project = self.queue.tt.rp('e_rabi_ou1800deg-90-L', omega = _I_['omega']).pi
                #freq = 98.32 + _I_['mw_freq']
                #freq = np.unique(self.queue.tt.mfl({}, ms_trans='L')) + _I_['mw_freq']
                freq = self.queue.tt.mw_mixing_frequency_L + _I_['mw_freq']
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                    gateMW = True,
                    amplitudes=[amp_project],
                    frequencies=[freq],
                    mixer_deg=[-90]
                )

            freq=[3000]
            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                   nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
        
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.512), name='sequence wait 2')

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['result', '>', 1, 1, 0, 1],
        # ['init', '>', 1, 1, 0, 1],
        # ['init', '>', 5, 1, 0, 1],
    ]
        #what does each entry do?
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
    #nuclear.analyze_type = 'consecutive'
    nuclear.analyze_type = 'average' #experimental feature for the fast 
    nuclear.save_smartly = True
    #PLE refocus
    nuclear.do_ple_refocusA1 = False #not used 
    nuclear.do_ple_refocusA2 = False

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    #confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = False
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.check_A2_power = False
    nuclear.do_repump = False

    nuclear.ple_refocus_interval = 500
    nuclear.confocal_refocus_interval = 1800  # seconds
    nuclear.odmr_refocus_interval= 1800

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(5)),
            ('A2_power',[5]),
            #('nuc',[nuclear.queue._transition_tracker.si29_list[0]]),
            ('t_read',[5.]),
            ('readout', ['A2']),
            ('omega', [0.2]),
            ('init_time', [20]),
            ('trans',['L', 'C', 'R']),
            ('mw_freq', np.arange(-0.5,0.5,0.05)),
        )
    )
    nuclear.number_of_simultaneous_measurements = len(nuclear.parameters['mw_freq'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10*1e6
    nuclear.pld.fit_function='lorentz'
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()

    print('run_fun started')
    nuclear.run(abort)

    while not hasattr(nuclear, '_state'):
        QtTest.QTest.qSleep(100)
    print('========\n Finished waiting for state\n ======')  # t
    while nuclear.state == 'run':
        QtTest.QTest.qSleep(100)
    print('========\n Finished waiting for run\n ======')  # t
    
    #todo - fit and set mw_mixing_frequency here!!!!
    nuclear.pld.x_axis_parameter_list.update_selected_value('mw_freq')
    nuclear.pld.average_parameter_list.update_selected_data(['sweeps'])
    nuclear.pld.observation_list.update_selected_data(['average_counts'])
    QtTest.QTest.qSleep(1000)
    print('counts selected')
    nuclear.pld.update_plot()  # (hit the plot button!)
    QtTest.QTest.qSleep(1000)
    nuclear.pld.update_plot_fit() # (hit the fit button!)
    QtTest.QTest.qSleep(1000)
    nuclear.center_positions = nuclear.pld.data_fit_results.df['center'] #save the center positions of lorentzian.
    print(' Nuclear finished!!!\n', nuclear.center_positions)
    #print("trans = {'L3': ", trans['L3']+nuclear.center_positions[0], ", 'L6': ", trans['L6']+nuclear.center_positions[0], ", 'C3': ", trans['C3']+nuclear.center_positions[1], ", 'C6': ", trans['C6']+nuclear.center_positions[1], ", 'R3': ", trans['R3']+nuclear.center_positions[2], ", 'R6': ", trans['R6']+nuclear.center_positions[2], "}")
    nuclear.queue.tt.mw_mixing_frequency_L += nuclear.center_positions[0]
    nuclear.queue.tt.mw_mixing_frequency_C += nuclear.center_positions[1]
    nuclear.queue.tt.mw_mixing_frequency_R += nuclear.center_positions[2]