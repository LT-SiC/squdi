# coding=utf-8
import numpy as np
import os
from importlib import reload

from qudi.logic.mcas.sequence import MultiChSeq as MultiChSeq
#from qudi.logic.qudip_enhanced import *
import qudi.logic.mcas.elements as E
import qudi.notebooks.UserScripts.helpers.sequence_creation_helpers as sch; reload(sch)
import qudi.notebooks.UserScripts.helpers.shared as shared; reload(shared)
import qudi.notebooks.UserScripts.helpers.snippets_awg as sna; reload(sna)
import qudi.notebooks.UserScripts.helpers.shared as ush; reload(ush)

from collections import OrderedDict

seq_name = os.path.basename(__file__).split('.')[0]
nuclear = sch.create_nuclear(__file__)
with open(os.path.abspath(__file__).split('.')[0] + ".py", 'r') as f:
    meas_code = f.read()

__TAU_HALF__ = 2*192/12e3
__SAMPLE_FREQUENCY__ = 12e3#e.__SAMPLE_FREQUENCY__

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):        
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        trans = {}
        for idx, _I_ in current_iterator_df.iterrows():
            for t in ['L','C','R']:
                for i in [1,2]:
                    trans[t+str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]:[-0.5,0.5]}, ms_trans=t)[i-1]
            if 'L' in _I_['trans']:
                state = 'm12'
            elif 'C' in _I_['trans']:
                state = 'm12'
            elif 'R' in _I_['trans']:
                state = 'p12'
            sna.repump(mcas, 10)
            sna.electron_init(mcas, state, _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = _I_['init_amp'])
            mcas.start_new_segment(name='sequence', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1))
            
            # if _I_['trans'] == 'L':
            #     amp = self.queue.tt.RP('e_rabi_ou350deg-90-L2', omega=_I_['omega']).amp
            #     pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-L2', omega=_I_['omega']).pi)
            # elif _I_['trans'] == 'C':
            #     amp = self.queue.tt.RP('e_rabi_ou350deg-90-L2', omega=_I_['omega']).amp
            #     pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-L2', omega=_I_['omega']).pi)
            # else:
            #     amp = self.queue.tt.RP('e_rabi_ou350deg-90-R2', omega=_I_['omega']).amp
            #     pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-R2', omega=_I_['omega']).pi)
                
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(_I_['trans']+'2')
            
            amp = amp / _I_['factor']
            pi_dur = pi_dur * _I_['factor']

            t = _I_['trans']
            freq1 =np.mean([trans[t+'1'], trans[t+'2']]) +_I_['mw_freq']
            #print(np.mean([trans[t+'1'], trans[t+'2']]), amp, pi_dur)
            
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
            mcas.asc(length_mus=10, gateMW = True, name='gateMW')
            #print(amp)
            sna.electron_rabi(
                mcas,
                new_segment=True,
                length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                gateMW = True,
                amplitudes=[amp],
                frequencies=[freq1],
                mixer_deg=[-90],
                pulseshape='sinehermite'
            )
            if 'C' in _I_['trans']:
                amp_project = self.queue.tt.RP('e_rabi_ou350deg-90-R2', omega=_I_['omega']).amp
                pi_dur_project = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-L2', omega=_I_['omega']).pi)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
                sna.electron_rabi(
                    mcas,
                    new_segment=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                    gateMW = True,
                    amplitudes=[amp_project,amp_project],
                    frequencies=[trans['L1'],trans['L2']],
                    mixer_deg=[-90,-90],
                    pulseshape='sinehermite'
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
    nuclear.save_smartly = False
    #PLE refocus
    nuclear.do_ple_refocusA1 = False #not used 
    nuclear.do_ple_refocusA2 = False

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    #confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = True
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.check_A2_power = False
    nuclear.do_repump = False

    nuclear.ple_refocus_interval = 200
    nuclear.confocal_refocus_interval = 200  # seconds
    nuclear.odmr_refocus_interval= 1800

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(10)),
            ('A2_power',[4]),
            ('omega',[.3]),
            ('t_read',[2.048]),
            ('readout', ['A2']),
            ('init_time', [50]),
            ('init_amp',[0.15]),
            ('factor',[1]),
            ('trans',['L', 'R']),
            ('mw_freq', np.arange(-20,20,0.25)),
        )
    )
    nuclear.number_of_simultaneous_measurements = 40 # len(nuclear.parameters['mw_freq']//4)

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 15*1e6
    nuclear.pld.fit_function='lorentz'
    nuclear.hashed = False
    nuclear.debug_mode = False
    #print("to calibrate, use Transition_calibration_Nuc_SSR_electron_rabi_or_ODMR instead")
    settings()

    print('run_fun started')
    nuclear.run(abort)

    ##### USE Transition_calibration_Nuc_SSR_electron_rabi_or_ODMR instead
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
    print('av counts selected')
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
    