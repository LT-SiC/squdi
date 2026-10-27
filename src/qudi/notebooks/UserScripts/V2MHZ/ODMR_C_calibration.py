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
    if 'p' in state:
            mw_init32L1 = 0.4
            mw_init32L2 = 0.4
    elif 'm' in state:
            mw_init32R1 = 0.4
            mw_init32R2 = 0.4
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
        sequence_name = 'NuclearOPs_C_Calibration' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        
        for idx, _I_ in current_iterator_df.iterrows():
            ### REPUMP ###
            mcas.start_new_segment('start_sequence', loop_count=3)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(15.0), repump=True, name='Repump')
            mcas.start_new_segment('start_sequence_decay', loop_count=3)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10.0))  #Decay from metastables.
            
            ### INITIALIZATION ###
            # Decide on init state for rabi calibration.
            # state = {
            #     'L':'m',
            #     'C':'p',
            #     'R': 'p',
            #     }[_I_['trans']]
            # state +={
            #     'L':'12',
            #     'C':'12',
            #     'R':'12',
            #     }[_I_['trans']]

            if _I_['readout'] == 'A2':
                state = 'm12'
            elif _I_['readout'] == 'A1':
                state = 'm32'
            segment_length = 7
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [31.2, 39.24, 168.93, 178.35])
            ) 
            mcas.start_new_segment(name='init', loop_count = 1)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [31.2, 39.24, 168.93, 178.35])
            )

            
            ### SEQUENCE ###
            freq = {'L': 35, 'C':2609, 'R': 2681}[_I_['trans']] +_I_['mw_freq']
            
            if 'R' in _I_['trans']:
                pi_dur = 1.135/2
                amp = 0.2
            elif 'L' in _I_['trans']:
                pi_dur = 0.64
                amp = 0.8826
                # pi_dur = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi
                # amp = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp
            elif 'C' in _I_['trans']:
                pi_dur = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp 

            #mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
            sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                amplitudes=[amp],
                frequencies=[freq],
                mixer_deg=[-90]
            )
            
            #project with left trans
            if _I_['trans'].startswith('C'):
                amp_project = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega = 0.5).amp
                pi_dur_project = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega = 0.5).pi
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW = True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                    amplitudes=[amp_project, amp_project],
                    frequencies=[2537.12, 2539.34],
                    mixer_deg=[-90, -90]
                )

            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[30], wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=[30], wait_dur=0.0, robust=False,
                   nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            mcas.asc(length_mus=0.5, name='sequence wait 2')

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements) #how to get here the queue? readout duration/sequence length.

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

    nuclear.checkA2LaserPower = False

    nuclear.ple_refocus_interval = 500
    nuclear.confocal_refocus_interval = 500  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(200)),
            ('A2_power',[10]), #manually adjusted the laserpower to 10nW each
            ('omega', [2]),
            ('t_read',[1.024]),
            ('trans',['L']),
            ('init_time', [10, 20, 30, 50, 75, 100, 150]),
            ('mw_freq', np.linspace(-6 , 6, 100)),
            ('readout', ['A2','A1']),
            #('init_state',['m12','m32']),
        )
    )
    nuclear.number_of_simultaneous_measurements =  2*10#len(nuclear.parameters['mw_freq'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 20*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)