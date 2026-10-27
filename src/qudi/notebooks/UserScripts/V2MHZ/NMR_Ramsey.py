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
            mw_init32L1 = 0.08
            mw_init32L2 = 0.08
    elif 'm' in state:
            mw_init32R1 = 0.08
            mw_init32R2 = 0.08
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
        sequence_name = 'Nuclear_NMR_trans' if sequence_name is None else sequence_name
        #print(self, current_iterator_df)
        
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():

            ### REPUMP ###
            mcas.start_new_segment('start_sequence')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10.0), repump=True, name='Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.512))
                   
            
            ### INITIALIZATION ###
            state = _I_['state']
            segment_length = 1
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [35.2,  39.83, 173.63, 179.03])
            ) 
            mcas.start_new_segment(name='init', loop_count = 1)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                length_mus=E.round_length_mus_to_x_multiple_ps(0.128), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [35.2,  39.83, 173.63, 179.03])
            ) 
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.512))

            ### SEQUENCE ###
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(.256), gateMW = True)
            sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus= _I_['tau_rabi'],
                amplitudes=[_I_['RF_amp']],
                frequencies=[_I_['mw_freq']],
                mixer_deg=[-90]
            )

            # Main Waiting time is covered by loops of segment_length = 1µs.
            # During this time gateMW is turned off to reduce noise.
            loops, correction_mus = shared.calculate_loop_count(_I_['wait'],segment_length)      
            mcas.start_new_segment(name='wait', loop_count = loops)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(segment_length),gateMW = False)
                 
            # To correct for rounding errors a non-looped segment is used.
            # For the last 256ns gateMW is turned on again.
            mcas.start_new_segment(name='wait_correction', loop_count = 1)
            if E.round_length_mus_to_x_multiple_ps(correction_mus)<=0.256:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus),gateMW = False)
            else:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus-0.256),gateMW = False)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256),gateMW = True)
            
            sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus= _I_['tau_rabi'],
                amplitudes=[_I_['RF_amp']],
                frequencies=[_I_['mw_freq']],
                phases = [_I_['phase_pi2_2']],
                mixer_deg=[-90]
            )
            
            pi_dur = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi
            amp = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp
            sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus= E.round_length_mus_to_x_multiple_ps(pi_dur),
                amplitudes=[amp],
                frequencies=[_I_['cnot_freq']],
                mixer_deg=[-90]
            )
            
            freq = [30.0]
            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(0.3))
            elif _I_['readout'] == 'A1':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(0.3))
            mcas.asc(length_mus=0.5, name='sequence wait 2')

        
        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements) #how to get here the queue? readout duration/sequence length.

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['result', '>', 0, 1, 0, 1],
        
    ]
        # etc.. laser2-laser1,  histograms are centered around 0, 
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
    nuclear.do_confocal_A2MW_refocus = False ## Not implemented with the AWG markerings.

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

    nuclear.parameters = OrderedDict( # WHAT DOES ALL THIS MEAN ??? WHICH UNITS ??
        (
            ('sweeps', range(200)),
            ('A2_power', [4]), # Is not yet implemented...
            ('omega', [0.8]),  
            ('readout', ['A2']),
            ('state',['m32']),
            ('init_time', [200]),
            ('RF_amp', [0.1]),
            ('mw_freq', [8.257-0.03]),
            ('cnot_freq',[36.34]),
            ('tau_rabi',E.round_length_mus_to_x_multiple_ps([4.678/4])), 
            ('phase_pi2_2',[0, 180]),
            ('wait',E.round_length_mus_to_x_multiple_ps(np.arange(2,300,3))), 
        )
    )
    nuclear.number_of_simultaneous_measurements =  len(nuclear.parameters['wait'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 100*1e6 # --> nvalues.
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)
    #nuclear.thread.join() #experimental...
    # # ---------------------
   
    