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

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        sequence_name = 'Electron_rabi_test' if sequence_name is None else sequence_name
        #print(self, current_iterator_df)
        
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        mcas.start_new_segment('start_sequence')
    
    # Loop over all freqs
        for idx, _I_ in current_iterator_df.iterrows():

        ### Initalization ###    
        # Repump Before Each Frequency
            mcas.asc(name='Repump', length_mus=_I_['repumpBeforeFreq'], repump=True)
            if _I_['repumpBeforeFreq'] > 0:
                mcas.asc(name='RepumpDecay', length_mus=_I_['repumpBeforeFreq_decay'])
            
            init_freq = {'L': 185, 'C': 185, 'R': 45}[_I_['trans']]

        # Resonant Initialization
            mcas.asc(
                A1=_I_['init_laser']=='A1',
                A2 =_I_['init_laser']=='A2', 
                length_mus=_I_['init_dur'], 
                name='resonant_init',
                pd2g1 = {
                    'type':'sine',
                    'phases':[0],
                    'amplitudes':[_I_['init_amp']],
                    'frequencies':[init_freq]
                })
            if _I_['init_dur'] > 0:
                mcas.asc(name='InitDecay', length_mus=_I_['init_decay'])

        ### Pi Pulse ###
            #pi_dur = 0.96*4
            #amp = 0.02/4
            
            freq = {'L': 45., 'C':115., 'R': 185.}[_I_['trans']] +_I_['mw_freq']
            factor = 4
            pi_dur = {'L': 0.96*factor, 'C':0.96*factor, 'R': 1.28*factor}[_I_['trans']]
            amp = 0.02/factor
            
            
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus= pi_dur,
                amplitudes=[amp],
                frequencies=[freq],
                mixer_deg=[-90]
            )
            if _I_['trans'].startswith('C'):
                print("Im starting with C")
                mcas.asc(name='pi_decay', length_mus=_I_['pi_decay'])
                
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus= 0.64,
                    amplitudes=[0.04, 0.04],
                    frequencies=[184, 186.5],
                    mixer_deg=[-90,-90]
                )
                # sna.electron_rabi(
                #     mcas,
                #     new_segment=False,
                #     length_mus= 0.96,
                #     amplitudes=[0.02, 0.02],
                #     frequencies=[44.29, 46.33],
                #     mixer_deg=[-90,-90]
                # )
            else:
                print('Im not starting with C')
            mcas.asc(name='pi_decay', length_mus=_I_['pi_decay'])
            
        ### Readout ###
            freq = [30.0]
            if _I_['readout_laser'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=_I_['readout_dur'])
            elif _I_['readout_laser'] == 'A1':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=_I_['readout_dur'])
            mcas.asc(name='readout_decay', length_mus=_I_['readout_decay'])

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements) #how to get here the queue? readout duration/sequence length.

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['result', '>', 0, 1, 0, 1],
        #['result', '>', -1, 1, 0, 1],
        #['init', '>', -1, 1, 0, 1],
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
    # nuclear.analyze_type = 'consecutive'
    nuclear.analyze_type = 'average'

    # PLE refocus
    nuclear.do_ple_refocusA1 = False  # not used
    nuclear.do_ple_refocusA2 = True

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    # confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = True
    nuclear.do_confocal_A2MW_refocus = False

    nuclear.ple_refocus_interval = 600
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval = 600

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # Enter Measurement parameters here. All times in µs
    nuclear.parameters = OrderedDict(
        (
            # Repump Before Each Seq is to be tiped in by hand at begin of sequence. Standard is 0µs
            ('repumpBeforeFreq', [50.0]),  
            ('repumpBeforeFreq_decay', [10.]),

            ('init_laser', ['A2']),
            ('init_dur', [20]),
            ('init_amp', [0.2]), # between 0-1
            ('init_freq', [185]),
            ('init_decay', [1]),

            ('pi_omega', [1]),
            ('pi_decay', [0.01]),

            ('readout_dur', [1.5]),
            ('readout_decay', [0.5]),

            ('A2_power', [5]), #nW
            ('sweeps', range(150)),

            ('trans', ['L', 'C', 'R']),

            ('mw_freq', np.linspace(-3., 3.0 ,151)), # MHz
            ('readout_laser', ['A1', 'A2']),
        )
    )
    nuclear.number_of_simultaneous_measurements =  2*5#*len(nuclear.parameters['mw_freq'])

def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 15 * 1e6  # 1.4e4 #6e5 #10*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)