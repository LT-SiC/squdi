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
            mw_init32L1 = 0.05
            mw_init32L2 = 0.05
    elif 'm' in state:
            mw_init32R1 = 0.05
            mw_init32R2 = 0.05
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
            sequence_name = 'NuclearOps_ElectronDD'
        
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1,2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():

            ### REPUMP ###
            mcas.start_new_segment('start_sequence')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5.0), repump=True, name='Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2.0))
           
            ### INITIALIZATION ###
            state = {
                'L1': 'm',
                'L':'m',
                'C':'m',
                'R1': 'p',
                'R':'p'
                }[_I_['trans']]
            state +={
                'L':'12',
                'L1':'12',
                'C':'12',
                'R1':'12',
                'R':'12'
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
                pd2g1 = init_state_drive(state, [35.755, 38, 175.185, 177.355])
            ) 
            mcas.start_new_segment(name='init', loop_count = 1)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                length_mus=E.round_length_mus_to_x_multiple_ps(0.128), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [35.755, 38, 175.185, 177.355])
            ) 
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1))

            ### SEQUENCE ###
            freq = {
                'L1': 35.755,
                'L2': 38,
                'L': (35.755+38)/2,
                'C1': (35.755+175.185)/2,
                'C2': (38+177.355)/2,
                'C': (35.755+38+175.185+177.355)/4,
                'R1': 175.185,
                'R2': 177.355,
                'R': (175.185+177.355)/2,
                }[_I_['trans']]
        
            mcas.start_new_segment(name='sequence')
            pi_2_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi2)
            pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi)
            amp_dur_L = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi
            amp_dur_C = self.queue.tt.rp('e_rabi_ou350deg-90-C', omega=_I_['omega']).pi
            amp_dur_R = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).pi
            
            amp = {'L': amp_dur_L, 'C': amp_dur_C, 'R': amp_dur_R}[_I_['trans']]

            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256),gateMW = True)
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=pi_2_dur,
                gateMW = True,
                amplitudes=[amp],
                frequencies=[freq],
                phases = [0],
                mixer_deg=[-90]
            )

            for i in range(_I_['n_pulses']):
                if i < _I_['n_pulses']//2:
                    if i%2 == 0:
                        phase = 0
                    else:
                        phase = 90
                elif i >= _I_['n_pulses']//2:
                    if i%2 == 0:
                        phase = 90
                    else:
                        phase = 0
                ### First wait ###
                if E.round_length_mus_to_x_multiple_ps(_I_['tau_2']) < 0.256:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau_2']),gateMW = True)
                else:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau_2']-0.256),gateMW = False)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256),gateMW = True)

                # refocussing pulse
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=pi_dur,
                    gateMW = True,
                    amplitudes=[amp],
                    frequencies=[freq],
                    phases = [phase],
                    mixer_deg=[-90]
                )

                ### Second wait ###
                if E.round_length_mus_to_x_multiple_ps(_I_['tau_2']) < 0.256:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau_2']),gateMW = True)
                else:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau_2']-0.256),gateMW = False)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256),gateMW = True)

            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=pi_2_dur,
                gateMW = True,
                amplitudes=[amp],
                frequencies=[freq],
                phases = [_I_['phase_pi2_2']],
                mixer_deg=[-90]
            )
            if _I_['trans'].startswith("C"):
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).pi),
                    amplitudes=[self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).amp],
                    frequencies=[(175.185+177.355)/2],
                    phases = [0],
                    mixer_deg=[-90]
                )
            

            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, no_new_segment=True, queue=self.queue, frequencies=[freq], wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=_I_['t_read'])
            if _I_['readout'] == 'A1':
                sna.ssr(mcas = mcas, no_new_segment=True, queue=self.queue, frequencies=[freq], wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=_I_['t_read'])
        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements) 

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
    nuclear.do_ple_refocusA2 = True

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    #confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = True
    nuclear.do_confocal_A2MW_refocus = False

    # Resonant Laser power
    nuclear.checkA1LaserPower = False # Not yet implemented in powerstablogic
    nuclear.checkA2LaserPower = False
    nuclear.A1LaserPower = 1 #nW
    nuclear.A2LaserPower = 3 #nW

    nuclear.ple_refocus_interval = 600
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval= 3000

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(50)),
            ('A2_power', [5]),
            ('t_read', E.round_length_mus_to_x_multiple_ps([0.3])),
            ('init_time', [50]),
            ('omega', [1/0.256]),
            ('readout',['A2']),
            ('n_pulses', [1]),
            ('trans', ['L']), 
            ('tau_2', E.round_length_mus_to_x_multiple_ps(np.arange(0,5,0.032))),
            ('phase_pi2_2', [0,180]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 2#len(nuclear.parameters['tau_2'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 2e6
    nuclear.debug_mode = False
    nuclear.hashed = False
    settings()
    print('run_fun started')
    nuclear.run(abort)