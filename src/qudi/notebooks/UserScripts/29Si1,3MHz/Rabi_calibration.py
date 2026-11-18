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


seq_name = os.path.basename(__file__).split('.')[0]
nuclear = sch.create_nuclear(__file__)
with open(os.path.abspath(__file__).split('.')[0] + ".py", 'r') as f:
    meas_code = f.read()

__TAU_HALF__ = 2*192/12e3
__SAMPLE_FREQUENCY__ = 12e3#e.__SAMPLE_FREQUENCY__

#trans = {'L1': 3834.098, 'L2': 3842.675, 'C1': 3903.826, 'C2': 3912.51, 'R1': 3973.492, 'R2': 3982.335} # 8 MHz of GSLAC paper
#trans = {'L1': 3834.384, 'L2': 3843.127, 'C1': 3904.018, 'C2': 3912.766, 'R1': 3974.043, 'R2': 3982.709} # SIL A Defect 6
#trans = {'L1': 3835.833, 'L2': 3844.568, 'C1': 3905.372, 'C2': 3914.037, 'R1': 3975.264, 'R2': 3984.044} # SIL A Defect 5
#trans = {'L1': 3836.91, 'L2': 3845.604, 'C1': 3906.599, 'C2': 3915.385, 'R1': 3976.514, 'R2': 3985.238}
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
        'type': 'sine',
        'phases': [0],
        'amplitudes': [
                    mw_init32L1,
                    mw_init32L2,
                    mw_init32R1,
                    mw_init32R2],        
        'frequencies':freqs
    }
    
    return pd2g1


def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]
        print(trans)
        sequence_name = 'Electron_rabi_test' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():
            
            ### REPUMP ###
            mcas.start_new_segment('Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10.0,64), repump=True, name='Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64))
            
            ### INITIALIZATION ###
            state = {"L1": "m12", "L2": "m12", "L": "m12", "C1": "m12", "C2": "m12", "C": "m12", "R1": "p12", "R2": "p12", "R": "p12"}[_I_['trans']]
            segment_length = 5
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [trans['L1'], trans['L2'], trans['R1'], trans['R2']]),
            ) 

            mcas.start_new_segment(name='sequence')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1)) 

            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True, name='gateMW')
            
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']),
                gateMW=True,
                amplitudes=[_I_['amp']],
                frequencies=[trans[_I_['trans']]], 
                mixer_deg=[-90]
            )
            if 'C' in _I_['trans']:
                amp_project = 0.18
                pi_dur_project = 1.5
                #print(amp_project)
                #amp_project = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp
                #pi_dur_project = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                    gateMW = True,
                    amplitudes=[amp_project, amp_project],
                    frequencies=[trans['L1'], trans['L2']],
                    mixer_deg=[-90,-90]
                )


            

            if _I_['readout'] == 'A2':
                sna.ssr(mcas=mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                        nuc='ple_A2',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        step_idx=0,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'A1':
                sna.ssr(mcas=mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                        nuc='ple_A1',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        step_idx=0,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))

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
    nuclear.do_confocal_A1A2_refocus = False
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.check_A2_power = False
    nuclear.do_repump = False

    nuclear.ple_refocus_interval = 20
    nuclear.confocal_refocus_interval = 60  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(10)),
            ('A2_power', [4]),
            ('init_time', [30]),
            ('t_read', [1.024*3]),
            ('trans', ['L1', 'R1']),
            ('amp', [0.1,0.2,0.3,0.4]),
            ('readout', ['A2']),
            ('tau', np.arange(0., 8., .064)),
        )
    )
    nuclear.number_of_simultaneous_measurements = len(nuclear.parameters['tau'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 20*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)