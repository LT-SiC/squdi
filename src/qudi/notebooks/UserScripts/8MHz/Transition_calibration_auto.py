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

#trans = {'L1': 3834.098, 'L2': 3842.675, 'C1': 3903.826, 'C2': 3912.51, 'R1': 3973.492, 'R2': 3982.335} # 8 MHz of GSLAC paper
trans = {'L1': 3834.409, 'L2': 3843.08, 'C1': 3903.957, 'C2': 3912.488, 'R1': 3973.964, 'R2': 3982.699} # SIL A Defect 6
trans = {'L1': 3835.833, 'L2': 3844.568, 'C1': 3905.372, 'C2': 3914.037, 'R1': 3975.264, 'R2': 3984.044} # SIL A Defect 5
trans = {'L1': 3835.833, 'L2': 3844.568, 'C1': 3905.372, 'C2': 3914.037, 'R1': 3975.264, 'R2': 3984.044}
trans = {'L1': 3834.773, 'L2': 3843.468, 'C1': 3904.489, 'C2': 3913.26, 'R1': 3974.429, 'R2': 3983.221}
trans = {'L1': 3835.978, 'L2': 3844.685, 'C1': 3905.698, 'C2': 3914.325, 'R1': 3975.332, 'R2': 3984.09}
trans = {'L1': 3835.733, 'L2': 3844.494, 'C1': 3905.549, 'C2': 3914.286, 'R1': 3975.344, 'R2': 3984.029}
trans = {'L1': 3835.72, 'L2': 3844.432, 'C1': 3905.586, 'C2': 3914.26, 'R1': 3975.354, 'R2': 3984.004}
trans = {'L1': 3837.161, 'L2': 3845.878, 'C1': 3906.769, 'C2': 3915.373, 'R1': 3976.478, 'R2': 3985.249}
trans = {'L1': 3837.161, 'L2': 3845.878, 'C1': 3906.769, 'C2': 3915.373, 'R1': 3976.478, 'R2': 3985.249}
trans = {'L1': 3836.91, 'L2': 3845.604, 'C1': 3906.599, 'C2': 3915.385, 'R1': 3976.514, 'R2': 3985.238}
trans = {'L1': 3836.828, 'L2': 3845.692, 'C1': 3906.55, 'C2': 3915.358, 'R1': 3976.546, 'R2': 3985.308}
trans = {'L1': 3836.91, 'L2': 3845.604, 'C1': 3906.599, 'C2': 3915.385, 'R1': 3976.514, 'R2': 3985.238}
trans = {'L1': 3836.828, 'L2': 3845.692, 'C1': 3906.55, 'C2': 3915.358, 'R1': 3976.546, 'R2': 3985.308}
trans = {'L1': 3836.942, 'L2': 3845.638, 'C1': 3906.764, 'C2': 3915.412, 'R1': 3976.602, 'R2': 3985.282}
trans = {'L1': 3837.874445, 'L2': 3846.570445, 'C1': 3907.766205, 'C2': 3916.414205, 'R1': 3977.480326, 'R2': 3986.160326}



def init_state_drive(state, freqs):
    '''
    State could be "p(m)3(1)2+(-,n)", example m32+, or p32-, p32n 
    '''
    mw_init32L1 = 0
    mw_init32L2 = 0
    mw_init32R1 = 0
    mw_init32R2 = 0
    ## MW drive
    if 'p' in state:
            mw_init32L1 = 0.1
            mw_init32L2 = 0.1
    elif 'm' in state:
            mw_init32R1 = 0.1
            mw_init32R2 = 0.1
    pd2g1 = {
        'type':'sine',
        'phases':[0],
        'amplitudes':[
                    mw_init32L1,
                    mw_init32L2,
                    mw_init32R1,
                    mw_init32R2],        
        'frequencies':freqs
    }
    
    return pd2g1


def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        
        sequence_name = 'Electron_rabi_test' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():
            for t in ['L','C','R']:
                for i in [1,2]:
                    trans[t+str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]:[-0.5,0.5]}, ms_trans=t)[i-1]
    
            ### REPUMP ###
            mcas.start_new_segment('Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10.0,64), repump=True, name='Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64))
            
            ### INITIALIZATION ###
            state = {"L": "m12", "C": "p12", "R": "p12"}[_I_['trans']]
            segment_length = 10
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [trans['L1'],trans['L2'],trans['R1'],trans['R2']]),
                
            ) 
            mcas.start_new_segment(name='sequence', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1))
            amp = 0.47
            if _I_['trans'] == 'L':
                #amp = self.queue.tt.rp('e_rabi_ou500deg-90-L', amp=amp).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou750deg-90-L', amp = amp).pi)
            elif _I_['trans'] == 'C':
                #amp = self.queue.tt.rp('e_rabi_ou500deg-90-C', amp=0.4).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou750deg-90-R', amp=amp).pi)
            else:
                amp = self.queue.tt.rp('e_rabi_ou750deg-90-R', amp=amp).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou750deg-90-R', amp=amp).pi)
            t = _I_['trans']
            freq1,freq2 =np.array([trans[t+'1'], trans[t+'2']]) +_I_['mw_freq']
            #, "C": (trans['C1']+trans['C2'])/2, "R": (trans['R1']+trans['R2'])/2}[_I_['trans']]+_I_['mw_freq']

            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
            #print(amp)
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                gateMW = True,
                amplitudes=[amp,amp],
                frequencies=[freq1,freq2],
                mixer_deg=[-90,-90]
            )
            if 'C' in _I_['trans']:
                amp_project = self.queue.tt.rp('e_rabi_ou750deg-90-L', amp=amp).amp
                #print(amp_project)
                pi_dur_project = self.queue.tt.rp('e_rabi_ou750deg-90-L', amp=amp).pi
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                    gateMW = True,
                    amplitudes=[amp_project, amp_project],
                    frequencies=[trans['L1']+_I_['mw_freq'], trans['L2']+_I_['mw_freq']],
                    mixer_deg=[-90,-90]
                )

            freq=[3000]
            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                   nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))

            # amp = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=0.7).amp
            # amp2 = self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=0.7).amp
            # pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=0.7).pi)

            # sna.ssr(mcas = mcas, queue=self.queue, frequencies=[[3546.65, 5686.14]], wait_dur=0.0, robust=False,
            #         nuc='29Si8_A2', mixer_deg=-90, eom_ampl=0.0, 
            #         step_idx=0, laser_dur=5.0, length_mus_mw = pi_dur, amplitudes=[amp,amp2], repetitions = 4
            #         )
        
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
    nuclear.do_ple_refocusA2 = True

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    #confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = True
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.check_A2_power = True
    nuclear.do_repump = False

    nuclear.ple_refocus_interval = 500
    nuclear.confocal_refocus_interval = 1800  # seconds
    nuclear.odmr_refocus_interval= 1800

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(10)),
            ('A2_power',[5]),
            ('nuc',[nuclear.queue._transition_tracker.si29_list[0]]),
            ('omega',[0.5]),
            ('t_read',[15.]),
            ('readout', ['A2']),
            ('init_time', [500]),
            ('trans',['L','C','R']),
            ('mw_freq', np.arange(-1.5,1.5,0.2)),
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
    print('av counts selected')
    nuclear.pld.update_plot()  # (hit the plot button!)
    QtTest.QTest.qSleep(1000)
    nuclear.pld.update_plot_fit() # (hit the fit button!)
    QtTest.QTest.qSleep(1000)
    nuclear.center_positions = nuclear.pld.data_fit_results.df['center'] #save the center positions of lorentzian.
    print(' Nuclear finished!!!\n', nuclear.center_positions)
    print("trans = {'L1': ", trans['L1']+nuclear.center_positions[0], ", 'L2': ", trans['L2']+nuclear.center_positions[0], ", 'C1': ", trans['C1']+nuclear.center_positions[1], ", 'C2': ", trans['C2']+nuclear.center_positions[1], ", 'R1': ", trans['R1']+nuclear.center_positions[2], ", 'R2': ", trans['R2']+nuclear.center_positions[2], "}")
    nuclear.queue.tt.mw_mixing_frequency_L += nuclear.center_positions[0]
    nuclear.queue.tt.mw_mixing_frequency_C += nuclear.center_positions[1]
    nuclear.queue.tt.mw_mixing_frequency_R += nuclear.center_positions[2]