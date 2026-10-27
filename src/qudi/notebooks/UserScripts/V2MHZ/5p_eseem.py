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

def init_state_drive(state, freqs): # freqs is list of L12, L23, R12, R34
    '''
    State could be "p(m)3(1)2+(-,n)", example m32+, or p32-, p32n 
    '''
    mw_init32L1 = 0
    mw_init32L2 = 0
    mw_init32C1 = 0
    mw_init32C2 = 0
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
                    mw_init32C1,
                    mw_init32C2,
                    mw_init32R1,
                    mw_init32R2,
                    ],             
        'frequencies':freqs
    }
    return pd2g1

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        sequence_name = '5pulse' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        mcas.start_new_segment('start_sequence')
        mcas.asc(length_mus=5.0, repump=True, name='Repump')
        mcas.asc(length_mus=5.0)
        
        freqs = [2399,2401.1,1,1,2538.5,2540.7]

        for idx, _I_ in current_iterator_df.iterrows():
            state = {
                'L12':'m',
                'L34':'m',
                'C12':'m',
                'C34':'m',
                'R12':'p',
                'R34':'p',
                'R':'p'
                }[_I_['trans']]
            state +={
                'L12':'12',
                'L34':'12',
                'C12':'12',
                'C34':'12',
                'R12':'12',
                'R34':'12',
                'R':'12'
                }[_I_['trans']]
            
            loops = 100
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                length_mus=E.round_length_mus_full_sample(_I_['init_time']/(64*loops))*64, 
                name='resonant_init',
                pd2g1 = init_state_drive(state, freqs)
            )

            mcas.start_new_segment(name='sequence')
            mcas.asc(length_mus=0.5)
            ### PI/2 of electron ###

            if 'R' in _I_['trans']:
                freq = (freqs[4]+freqs[5])/2
                pi_2_dur = self.queue.tt.rp('e_rabi_ou350deg-90-R', amp=0.6).pi2
                pi_dur = self.queue.tt.rp('e_rabi_ou350deg-90-R', amp=0.6).pi
            else:
                freq = (freqs[0]+freqs[1])/2
                pi_2_dur = self.queue.tt.rp('e_rabi_ou350deg-90-L', amp=0.6).pi2
                pi_dur = self.queue.tt.rp('e_rabi_ou350deg-90-L', amp=0.6).pi

            
            def pi(phase = 0):
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_full_sample(pi_dur),
                    amplitudes=[0.6],
                    frequencies=[freq],
                    phases = [phase],
                    mixer_deg=[-90]
                )
            def pi2(phase = 0):
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_full_sample(pi_2_dur),
                    amplitudes=[0.6],
                    frequencies=[freq],
                    phases = [phase],
                    mixer_deg=[-90]
                )
            def __tau__(t):
                mcas.asc(length_mus = t, name = 'tau')

            ## Main sequence

            pi2(0)
            __tau__(_I_['tau'])
            pi(0)
            __tau__(_I_['tau'])
            pi2(90)
            
            __tau__(_I_['Tc'])

            pi2(0)
            __tau__(_I_['tau'])
            pi(0)
            __tau__(_I_['tau'])
            pi2(90+_I_['readout_phase'])


            mcas.asc(length_mus=0.25, name='sequence wait 1')

            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[freq], wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=0.5)
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=[freq], wait_dur=0.0, robust=False,
                   nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=0.5)
            
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

    nuclear.ple_refocus_interval = 300
    nuclear.confocal_refocus_interval = 300  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( # WHAT DOES ALL THIS MEAN ??? WHICH UNITS ??
        (
            ('sweeps', range(50)),
            ('init_time', [40.0]),
            ('A2_power',[5]),
            ('trans',['R']),
            ('readout', ['A2']), 
            ('Tc',E.round_length_mus_full_sample(np.arange(1.0,50.1,0.1))),
            ('tau',[0.15-0.058]), # want 150ns. pi_dur = 76ns --> 3/2 * pi_dur/2 has to be subtracted (half of a pi/2-pulse + half of pi-pulse)
            ('readout_phase', [0,180]),
        )
    )
    nuclear.number_of_simultaneous_measurements =  len(nuclear.parameters['readout_phase'])*4

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 5*1e6#1.4e4 #6e5 #10*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)