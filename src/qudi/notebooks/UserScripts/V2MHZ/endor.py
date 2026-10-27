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

freqs = {
    'L12': 44.23,
    'L34': 46.43,
    'L1': 43.896,
    'L2': 44.444,
    'L3': 46.142,
    'L4': 46.622,
    'R1': 183.296,
    'R2': 183.741,
    'R3': 185.418,
    'R4': 185.910
    }


def init_state_drive(state):
    '''
    State could be "p(m)3(1)2+(-,n)", example m32+, or p32-, p32n
    '''
    mw_init32R2 = 0
    mw_init32R1 = 0
    mw_init32m = 0
    RF_init12p = 0
    RF_init12m = 0
    ## MW drive
    if 'p' in state:
        if '+' in state:
            RF_init12m = 0.1
            #RF_init12p = 0.1
            mw_init32R2 = 0.08
            mw_init32m = 0.4
        elif '-' in state:
            RF_init12m = 0.1
            #RF_init12p = 0.1
            mw_init32R1 = 0.08
            mw_init32m = 0.0
    elif 'm' in state:
        mw_init32R2 = 0.04
        mw_init32R1 = 0.04

    pd2g1 = {
        'type': 'sine',
        'phases': [0],
        'amplitudes': [
            mw_init32R2,
            mw_init32R1,
            mw_init32m,
            mw_init32m,
            RF_init12p,
            RF_init12m],
        # 'frequencies':[30.5,38.5],
        'frequencies': [183.48, 185.66, 44.29, 46.33, 3.4, 1.026]
    }

    return pd2g1

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        sequence_name = 'Electron_rabi_test' if sequence_name is None else sequence_name
        #print(self, current_iterator_df)
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        mcas.start_new_segment('start_sequence')
        for idx, _I_ in current_iterator_df.iterrows():
            ###
            ## Repump
            ###
            mcas.asc(length_mus=5.0, repump=True, name='Repump')
            mcas.asc(length_mus=10.0)  #Decay from metastables.
            

            ###
            ## Initialization
            ###

            ## Decide on init state for rabi calibration.

            #state = {'L1':'m','L2':'m', 'C1':'m','C2':'m','R1':'p','R2':'p'}[_I_['trans']]
            #state +={'L1':'32-','L2':'m12+', 'C1':'12+','C2':'32-','R1':'32+','R2':'12-'}[_I_['trans']]
            state = _I_['init_state']
            print('Initialising to',state)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state, 
                length_mus=_I_['init_time'], 
                name='resonant_init',
                pd2g1 = init_state_drive(state)
            ) 
            
            def pi(dur, amp, freq):
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_full_sample(dur),
                    amplitudes=[amp],
                    frequencies=[freq],
                    mixer_deg=[-90]
                )
            def ppi(dur, amps, freqs):
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_full_sample(dur),
                    amplitudes=amps,
                    frequencies=freqs,
                    mixer_deg=[-90,-90]
                )
            def pi2(dur, amp, freq, phase=0):
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_full_sample(dur),
                    amplitudes=[amp],
                    frequencies=[freq],
                    phases = [phase],
                    mixer_deg=[-90]
                )
            def __tau__(t):
                mcas.asc(length_mus = t, name = 'tau')

            ## Main sequence

            pi2(dur = 1.50, amp = 0.1, freq = 3.181)           # Hadamard on nuclear spin
            pi(dur = 1.025, amp = 0.02, freq = freqs['L12'])    # CNOT on electron spin (controlled by nuc up)
            __tau__(_I_['tau'])                            # Accumulate phase on entangled sensor-memory state
            ppi(dur = 1.025, amps = [0.02,0.02], freqs = [freqs['L12'],freqs['L34']])    # CNOT on electron spin (controlled by nuc up)
            __tau__(_I_['tau'])                            # Accumulate phase on entangled sensor-memory state
            pi(dur = 1.025, amp = 0.02, freq = freqs['L12'])    # CNOT on electron spin (controlled by nuc down)
            pi2(dur = 1.50, amp = 0.1, freq = 3.181)   # Hadamard on nuclear spin
            
            #__tau__(_I_['T_c'])                                 # Correlation time
            
            #pi(dur = 1.025, amp = 0.02, freq = freqs['L34'])    # CNOT on electron spin (controlled by nuc down)
            #__tau__(_I_['tau']*1.08)                            # Accumulate phase on entangled sensor-memory state
            #pi(dur = 1.025, amp = 0.02, freq = freqs['L12'])    # CNOT on electron spin (controlled by nuc up)
            
            #pi2(dur = 3.225, amp = 0.1, freq = 1.026, phase =360*_I_['T_c']*2/10+_I_['readout_phase'])   # Hadamard on nuclear spin

            ## Readout
            mcas.asc(length_mus=0.1, name='sequence wait 1')

            freq = [30]
            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=_I_['t_read'])
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                   nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=_I_['t_read'])
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

    nuclear.x_axis_title = 'tau [mus]'
    #nuclear.analyze_type = 'consecutive'
    nuclear.analyze_type = 'average'

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

    nuclear.ple_refocus_interval = 1000
    nuclear.confocal_refocus_interval = 1000  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(50)),
            ('init_time', [100.0]),
            ('readout', ['A2']),
            ('t_read',[1.0]),
            ('A2_power',[5]),
            ('init_state',['m32']),
            #('T_c',E.round_length_mus_full_sample(np.linspace(0.0, 10, 41))),
            ('tau',E.round_length_mus_full_sample(np.linspace(0.0, 15, 3*81))),
            ('readout', ['A1', 'A2']),
         #   ('readout_phase', [0, 180]),
        )
    )
    nuclear.number_of_simultaneous_measurements =  2#*len(nuclear.parameters['tau'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 20*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)