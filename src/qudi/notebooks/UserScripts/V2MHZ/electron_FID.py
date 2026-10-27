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

ael = 1.0


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
    def ret_mcas(self, current_iterator_df,sequence_name = None):
        if sequence_name is None:
            sequence_name = 'Electron_test'
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1,2], 'ps': [1]})

        for idx, _I_ in current_iterator_df.iterrows():
            ### REPUMP ###
            mcas.start_new_segment('start_sequence')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10.0), repump=True, name='Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0))

            ### INITIALIZATION ###
            state = {
                'L':'m',
                'L1':'m',
                'C':'m',
                'R':'p',
                'R1':'p'
                }[_I_['trans']]
            state +={
                'L':'12',
                'L1':'12',
                'C':'12',
                'R':'12',
                'R1':'12'
                }[_I_['trans']]
            
            segment_length = 1
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [2537.12 ,  2539.34, 2676.68 ,  2678.87])
            ) 
            mcas.start_new_segment(name='init', loop_count = 1)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                length_mus=E.round_length_mus_to_16_multiple_ps(0.128), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [2537.12 ,  2539.34, 2676.68 ,  2678.87])
            ) 

            freq = {
                #'L1': 35.755,
                #'L2': 38,
                'L': [2537.12],
                'L1': [2536.9],
                #'C1': (35.755+175.185)/2,
                #'C2': (38+177.355)/2,
                'C': (35.755+38+175.185+177.355)/4,
                #'R1': 175.185,
                #'R2': 177.355,
                'R': [2677.77],
                'R1': [2676.68]
                }[_I_['trans']]
            
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1))
            
            ### SEQUENCE ###
            mcas.start_new_segment('Sequence')
            pi_dur = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi
            amp_dur_L = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp
            #amp_dur_C = self.queue.tt.rp('e_rabi_ou350deg-90-C', omega=_I_['omega']).amp
            amp_dur_R = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).amp
            
            amp = {'L': amp_dur_L,'L1': amp_dur_L,'L12': amp_dur_L, 'R1': amp_dur_R, 'R': amp_dur_R}[_I_['trans']]
            #amp = {'L': amp_dur_L, 'C': amp_dur_C, 'R': amp_dur_R}[_I_['trans']]
            
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256),gateMW = True)
            if _I_['trans'] == 'L12':
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW = True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur/2),
                    amplitudes=[amp, amp],
                    frequencies=freq,
                    phases = [0,0],
                    mixer_deg=[-90,-90]
                )
                if E.round_length_mus_to_x_multiple_ps(_I_['tau']) <=0.256:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']),gateMW = True)
                else:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']-0.256),gateMW = False)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256),gateMW = True)
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW = True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur/2),
                    amplitudes=[amp,amp],
                    frequencies=freq,
                    phases = [_I_['phase_pi2_2'],_I_['phase_pi2_2']],
                    mixer_deg=[-90,-90]
                )
            else:
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW = True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur/2),
                    amplitudes=[amp],
                    frequencies=freq,
                    phases = [0],
                    mixer_deg=[-90]
                )
                if E.round_length_mus_to_x_multiple_ps(_I_['tau']) <=0.256:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']),gateMW = True)
                else:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']-0.256),gateMW = False)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256),gateMW = True)
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW = True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur/2),
                    amplitudes=[amp],
                    frequencies=freq,
                    phases = [_I_['phase_pi2_2']],
                    mixer_deg=[-90]
                )
            if _I_['trans'].startswith("C"):
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                    amplitudes=[amp],
                    frequencies=[(175.1+177.25)/2],
                    phases = [0],
                    mixer_deg=[-90]
                )
            
            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[33.0], wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=_I_['t_read'])
            elif _I_['readout'] == 'A1':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[33.0], wait_dur=0.0, robust=False,
                    nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=_I_['t_read'])
            
        self.queue._gated_counter.set_n_values(mcas,
        self.number_of_simultaneous_measurements) #how to get here the queue? readout duration/sequence length) #how to get here the queue?

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['result', '>', 1, 1, 0, 1],
        # ['init', '>', 1, 1, 0, 1],
        # ['init', '>', 5, 1, 0, 1],
    ]
    sch.settings(
        nuclear=nuclear,
        ret_mcas=ret_ret_mcas(pdc),
        analyze_sequence=ana_seq,
        pdc=pdc,
        meas_code=meas_code
    )

    nuclear.x_axis_title = 'Index'
    #nuclear.analyze_type = 'consecutive'
    # nuclear.analyze_type = 'standard'
    nuclear.analyze_type = 'average' #experimental feature for the fast 
    #nuclear.analyze_type = None
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

    # Resonant Laser power
    nuclear.checkA1LaserPower = False # Not yet implemented in powerstablogic
    nuclear.checkA2LaserPower = False
    nuclear.A1LaserPower = 1 #nW
    nuclear.A2LaserPower = 3 #nW

    nuclear.ple_refocus_interval = 300
    nuclear.confocal_refocus_interval = 300  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False


    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(50)),
            ('t_read', E.round_length_mus_to_x_multiple_ps([0.3])),
            ('A2_power', [3]),
            ('init_time', [75]),
            ('omega', [1/0.254]),
            ('readout',['A2']),
            ('trans', ['R', 'R1','L', 'L1']),
            ('phase_pi2_2', [0, 180]),
            ('tau', np.unique(E.round_length_mus_to_x_multiple_ps(np.arange(0.0, 5, 0.016)))),
        )
    )
    nuclear.number_of_simultaneous_measurements =  len(nuclear.parameters['tau']
        )

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 150e6
    nuclear.debug_mode = False
    nuclear.hashed = False
    settings()
    print('run_fun started')
    nuclear.run(abort)