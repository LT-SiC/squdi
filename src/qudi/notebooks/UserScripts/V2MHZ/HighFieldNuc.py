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
            mw_init32L1 = 0.15
            mw_init32L2 = 0.15
            mw_init32R2 = 0.15
    elif 'm' in state:
            mw_init32R1 = 0.15
            mw_init32R2 = 0.15
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
            mcas.start_new_segment('start_sequence',loop_count=3)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(15.0), repump=True, name='Repump')
            mcas.start_new_segment('start_sequence_decay')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0))  #Decay from metastables.
            
            ### INITIALIZATION ###
            # Decide on init state for rabi calibration.
            state = _I_['init_state']
            segment_length = 7
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [2539.78, 2548.59, 2679.54,2688.05])
            ) 
            mcas.start_new_segment(name='init_corr', loop_count = 1)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True, 
                length_mus=E.round_length_mus_to_x_multiple_ps(0.128), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [2539.78, 2548.59, 2679.54,2688.05])
            ) 
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='InitDecay')
            
            mcas.start_new_segment(name='sequence', loop_count = 1)
            ### SEQUENCE ###
            pi_dur = 0.63
            amp = 0.2
            # pi_dur = 0.001*self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=_I_['omega']).pi
            # amp = self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=_I_['omega']).amp
            
            def cnot():
                sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                amplitudes=[amp],
                frequencies=[2688.05], ###2688.05, 2679.54
                mixer_deg=[-90]
                )


            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
            Nuc = False
            if Nuc:
                ### p12 to p32
                cnot()
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(4.0)) #RF safety.
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW') # PS stuff.
                #mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), gateMW = True, name='MW safety')
                ### Nuc Freq scan
                # sna.nuclear_rabi(
                #     mcas,
                #     new_segment=False,
                #     gateMW = True,
                #     length_mus=40,
                #     amplitudes=[_I_['amp']],
                #     frequencies=[_I_['freq']],
                #     mixer_deg=[-90]
                # )
                mcas.asc(name='RF', length_mus=200.0, gateMW=True, pd2g2 = {"type":"sine", "frequencies":[_I_['freq']],"amplitudes":[_I_['amp']]})

                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(4.0)) #RF safety.
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW') # PS stuff.
                ### p32 to p12
                cnot()
            else:

                mcas.asc(name='RF', length_mus=_I_['tau_rf'], 
                         gateMW=True, 
                         pd2g2 = {"type":"sine", "frequencies":[_I_['freq']],"amplitudes":[_I_['amp']]},
                        )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(4.0), gateMW = False) #RF safety.
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True) #RF safety.

                mcas.asc(name='CNOT', length_mus=0.60, 
                         gateMW=True, 
                         pd2g1 = {"type":"sine", "frequencies":[_I_['freq_mw']],"amplitudes":[0.2]})
 
            #


            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[30], wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=_I_['t_read'])
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=[30], wait_dur=0.0, robust=False,
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

    nuclear.ple_refocus_interval = 500
    nuclear.confocal_refocus_interval = 500  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(10)),
            ('A2_power',[5]),
            ('init_state',['p12']),
            ('omega', [2]),
            ('t_read',[0.75]),
            ('amp',[0.12*4]),
            ('init_time', [500]),
            #('freq_mw', np.linspace(2679.54-3, 2679.54+11.0, 50)),
            #('tau_rf',E.round_length_mus_to_x_multiple_ps(np.linspace(0.256, 30.256,30))),
            ('tau_rf',E.round_length_mus_to_x_multiple_ps([12.0])),
            #('freq', [5.12]),
            ('freq', np.linspace(4.7, 5.4, 200)),            
            ('freq_mw', [2679.5, 2688.5]),
            #('freq_mw', np.linspace(2679.54-3, 2679.54+11.0, 50)),
            ('readout', ['A1']),
        )
    )
    nuclear.number_of_simultaneous_measurements =  2#len(nuclear.parameters['tau'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)