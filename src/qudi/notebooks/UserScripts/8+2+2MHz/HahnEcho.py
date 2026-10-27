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
            mcas.start_new_segment('Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10.0,64), repump=True, name='Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64))
            
            ### INITIALIZATION ###
            #state = _I_['state']
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
                pd2g1 = init_state_drive(state, [31.8, 39.87, 169.7, 179.2]),
                #pd2g2 = {"type":"sine", "frequencies":[1.14],"amplitudes":[0.4]}
            ) 
            mcas.start_new_segment(name='init_decay', loop_count = 1)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                length_mus=E.round_length_mus_to_x_multiple_ps(0.128), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [31.8, 39.87, 169.7, 179.2]),
                #pd2g2 = {"type":"sine", "frequencies":[1.14],"amplitudes":[0.4]}
            ) 
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1))       

            #=========================================#
            mcas.start_new_segment(name='sequence')

            ### PI / 2 ###
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(_I_['rf_dur']/2),
                gateMW = True,
                amplitudes=[_I_['rf_amp']],
                frequencies=[_I_['rf_freq']], 
                mixer_deg=[-90],
                phases=[0]
            )
            
            
            if _I_['tau_2'] > 100:
                loops = 5
            elif _I_['tau_2'] > 200:
                loops = 10
            else:
                loops = 2

            for i in range(_I_['n_pulses']):

                ### TAU / 2 ###
                if E.round_length_mus_to_x_multiple_ps(_I_['tau_2'])<=0.256:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau_2']),gateMW = True)
                else:
                    mcas.start_new_segment(name='init', loop_count = loops)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau_2']/10), gateMW = False)
                    mcas.start_new_segment(name='init', loop_count = 1)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True)

                ### PI ###
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(_I_['rf_dur']),
                    gateMW = True,
                    amplitudes=[_I_['rf_amp']],
                    frequencies=[_I_['rf_freq']], 
                    mixer_deg=[-90],
                    phases=[90*(i%2)] # change between X and Y pulse
                )
                
                ### TAU / 2 ###
                if E.round_length_mus_to_x_multiple_ps(_I_['tau_2'])<=0.256:
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau_2']),gateMW = True)
                else:
                    mcas.start_new_segment(name='init', loop_count = loops)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau_2']/10), gateMW = False)
                    mcas.start_new_segment(name='init', loop_count = 1)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True)

            ### PI / 2 ###
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(_I_['rf_dur']/2),
                gateMW = True,
                amplitudes=[_I_['rf_amp']],
                frequencies=[_I_['rf_freq']], 
                mixer_deg=[-90],
                phases=[_I_['phase']]
            )
              
            amp = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=_I_['omega']).amp
            pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=_I_['omega']).pi)

            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256)) # RF decay
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True)
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                gateMW = True,
                amplitudes=[amp],
                frequencies=[_I_['mw_freq']], 
                mixer_deg=[-90],
                phases=[0]
            )

            freq=[3000]
            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
                
            elif _I_['readout'] == 'A1':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
                
            elif _I_['readout'] == 'SSR':
                amp = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=1).amp
                amp2 = self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=1).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=1).pi)

                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[[39.87, 179.2]], wait_dur=0.0, robust=False,
                        nuc='29Si8_A2', mixer_deg=-90, eom_ampl=0.0, 
                        step_idx=0, laser_dur=5.0, length_mus_mw = pi_dur, amplitudes=[amp,amp2], repetitions = _I_['number_rep']
                        )
        
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
    nuclear.do_confocal_A1A2_refocus = True
    nuclear.do_confocal_A2MW_refocus = False

    nuclear.ple_refocus_interval = 500
    nuclear.confocal_refocus_interval = 500  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False


    lst = np.linspace(0,3000,50).tolist()
    lst1 = lst[0::2]
    lst2 = lst[1::2][::-1]
    ordered_list = []
    while len(lst2)>0:
        ordered_list.append(lst1.pop())
        ordered_list.append(lst2.pop())


    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(20)),
            ('A2_power',[5]),
            ('omega',[1]),
            ('t_read',[1.]),
            ('state',['m32']),
            ('rf_amp', [0.4]),
            ('init_time', [150]),
            ('mw_freq', [39.8]),
            ('rf_dur', [0.46]),
            ('rf_freq', [14.28]),
            ('readout', ['A2']),
            ('n_pulses', [1]),
            ('number_rep', [1]),
            ('phase', [0,180]),
            ('tau_2', ordered_list),
        )
    )
    nuclear.number_of_simultaneous_measurements =  4

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 40*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)