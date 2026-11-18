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
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1))
                   
            
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
                pd2g1 = init_state_drive(state, [34.3, 39., 173.8, 178.3])
            ) 
            mcas.start_new_segment(name='init', loop_count = 1)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                length_mus=E.round_length_mus_to_x_multiple_ps(0.128), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [34.3, 39., 173.8, 178.3])
            ) 
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.512))
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(.256), gateMW = True)

            

            ### SEQUENCE ###
            
            ### PI/2 on fiveMHz ###
            sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus= _I_['fiveMHz_dur']/2,
                amplitudes=[_I_['fiveMHz_amp']],
                frequencies=[_I_['fiveMHz_trans']],
                mixer_deg=[-90]
            )
            
            ### Tau ###
            if _I_['tau'] <= .256:
                mcas.asc(length_mus=_I_['tau'], gateMW = True)
            else:
                mcas.asc(length_mus=_I_['tau']-0.256, gateMW = False)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(.256), gateMW = True)
            
            ### PI on fiveMHz and twoMHz###
            sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus= _I_['twoMHz_dur'],
                amplitudes=[_I_['fiveMHz_amp'],_I_['twoMHz_amp']],
                frequencies=[_I_['fiveMHz_trans'],_I_['twoMHz_trans']],
                mixer_deg=[-90,-90]
            )
            
            ### Tau ###
            if _I_['tau'] <= .256:
                mcas.asc(length_mus=_I_['tau'], gateMW = True)
            else:
                mcas.asc(length_mus=_I_['tau']-0.256, gateMW = False)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(.256), gateMW = True)
            
            ### PI/2 on fiveMHz ###
            sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus= _I_['fiveMHz_dur']/2,
                amplitudes=[_I_['fiveMHz_amp']],
                frequencies=[_I_['fiveMHz_trans']],
                mixer_deg=[-90]
            )
            
            pi_dur = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=_I_['omega']).pi
            amp = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=_I_['omega']).amp
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
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(0.5))
            elif _I_['readout'] == 'A1':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(0.5))
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

    nuclear.ple_refocus_interval = 500
    nuclear.confocal_refocus_interval = 500  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # creating lists with alternating longest and shortest entries. Two neighbouring
    # entries always have same combined duration --> same noise over whole measurement. 
    lst = np.linspace(0,200,400).tolist()
    lst1 = lst[0::2]
    lst2 = lst[1::2][::-1]
    ordered_list = []
    while len(lst2)>0:
        ordered_list.append(lst1.pop())
        ordered_list.append(lst2.pop())

    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(200)),
            ('A2_power', [4]),
            ('omega', [0.6]),  
            ('readout', ['A2']),
            ('state',['m32']),
            ('init_time', [150]),
            ('fiveMHz_trans', [8.257]),
            ('twoMHz_trans', [3.201]),
            ('fiveMHz_dur',E.round_length_mus_to_x_multiple_ps([6.15/2])), 
            ('twoMHz_dur',E.round_length_mus_to_x_multiple_ps([6.15/2])), 
            ('tau',E.round_length_mus_to_x_multiple_ps(ordered_list)), 
            ('fiveMHz_amp', [0.15]),
            ('cnot_freq',[38.56]),
            ('twoMHz_amp', [0.649,0]),
        )
    )
    nuclear.number_of_simultaneous_measurements =  4#len(nuclear.parameters['mw_freq'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 20*1e6 # --> nvalues.
    nuclear.pld.fit_function='lorentz'
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)
    #nuclear.thread.join() #experimental...
    # # ---------------------
   
    