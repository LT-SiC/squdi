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
# trans = {'L1': 3834.38, 'L2': 3843.11, 'C1': 3903.826, 'C2': 3912.51, 'R1': 3974.02, 'R2': 3982.7} # SIL A Defect 6
trans = {'L1': 3834.35, 'L2': 3843.086, 'C1': 3904.039, 'C2': 3912.752, 'R1': 3973.928, 'R2': 3982.671} # SIL A Defect 5

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
            
            ### REPUMP ###
            mcas.start_new_segment('Repump',loop_count=5)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10.0,64), repump=True, name='Repump')
            mcas.start_new_segment('RepumpDecaz')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64))
            
            ### INITIALIZATION ###
            state = _I_['state']
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

            mcas.start_new_segment(name='sequence')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='InitDecay')

            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
            
            ampL = self.queue.tt.rp('e_rabi_ou500deg-90-L', period=_I_['period']).amp
            ampC = self.queue.tt.rp('e_rabi_ou500deg-90-C', period=_I_['period']).amp
            ampR = self.queue.tt.rp('e_rabi_ou500deg-90-R', period=_I_['period']).amp
            
            amp = {'L1': ampL, 'C1': ampC, 'R1': ampR}[_I_['trans']]

            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']),
                gateMW = True,
                amplitudes=[amp],
                frequencies=[trans[_I_['trans']]], 
                mixer_deg=[-90]
            )
            if _I_['trans'].startswith('C'):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.128), gateMW = True, name='gateMW')
                dur = self.queue.tt.rp('e_rabi_ou500deg-90-R', period=_I_['period']).pi
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    gateMW = True,
                    amplitudes=[ampR],
                    frequencies=[trans[_I_['readout_proj']]],
                    mixer_deg=[-90]
                )

            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
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
    nuclear.do_ple_refocusA2 = True

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    #confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = False
    nuclear.do_confocal_A2MW_refocus = False

    nuclear.ple_refocus_interval = 600
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(10)),
            ('A2_power',[5]),
            ('period',[1.024]),
            ('t_read',[.5]),
            ('init_time', [20,50,90]),
            ('readout_proj', ['R1']),
            ('state',['m32','m12','p12','p32']),
            ('trans',['L1','C1','R1']),
            ('readout', ['A2','A1']),
            ('tau', E.round_length_mus_to_x_multiple_ps(np.arange(0,2*1.024,0.128))),
        )
    )
    nuclear.number_of_simultaneous_measurements =  2*len(nuclear.parameters['tau'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 40*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)