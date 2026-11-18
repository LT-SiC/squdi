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
freqs_all = {'R2':177.25,'R1':175.1, 'C1':105.1,'C2':107.25,'L1':35.6,'L2':38.05,'RFp12':3.4,'RFm12':6.47}
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
            mw_init32L1 = 0.2
            #mw_init32L2 = 0.1
    elif 'm' in state:
            mw_init32R1 = 0.4
            #mw_init32R2 = 0.2
    pd2g1 = {
        'type':'sine',
        'phases':[0],
        'amplitudes':[
                    mw_init32L1,
                    #mw_init32L2,
                    mw_init32R1,
                    #mw_init32R2
                    ],        
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
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5.0,64), repump=True, name='Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2.0,64))
            
            ### INITIALIZATION ###
            state = {'L':'m12', 'C':'m12' ,'R':'p12'}[_I_['trans']]
            segment_length = 1
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [3549, 3689-0.4])
            ) 
            mcas.start_new_segment(name='init_decay', loop_count = 1)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                length_mus=E.round_length_mus_to_x_multiple_ps(0.128), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [3549, 3689-0.4])
            ) 
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1))

            #=========================================
            ###ODMR
            freq = {'L': 3549, 'C':3619-0.226, 'R': 3689-.43}[_I_['trans']]
            
            if 'R' in _I_['trans']:
                pi_dur = self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=_I_['omega']).pi
                amp = self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=_I_['omega']).amp
            elif 'L' in _I_['trans']:
                pi_dur = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=_I_['omega']).pi
                amp = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=_I_['omega']).amp
            elif 'C' in _I_['trans']:
                pi_dur = self.queue.tt.rp('e_rabi_ou500deg-90-C', omega=_I_['omega']).pi
                amp = self.queue.tt.rp('e_rabi_ou500deg-90-C', omega=_I_['omega']).amp

            mcas.start_new_segment('FID')
            ### PI/2 ###
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), name='sequence_wait',gateMW =True)
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur/2),
                gateMW = True,
                amplitudes=[amp],
                frequencies=[freq],
                mixer_deg=[-90],
                phases = [0]
            )
            
            ### TAU ###
            if E.round_length_mus_to_x_multiple_ps(_I_['tau'])<=0.256:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']),gateMW = True)
            else:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']-0.256), gateMW = False)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True)

            ### PI ###
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                gateMW = True,
                amplitudes=[amp],
                frequencies=[freq],
                mixer_deg=[-90],
                phases = [90]
            )

            ### TAU ###
            if E.round_length_mus_to_x_multiple_ps(_I_['tau'])<=0.256:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']),gateMW = True)
            else:
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']-0.256), gateMW = False)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True)
            
            ### PI/2 ###
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur/2),
                gateMW = True,
                amplitudes=[amp],
                frequencies=[freq],
                mixer_deg=[-90],
                phases = [_I_['readout_phase']]
            )
            
            #project with right trans
            if 'C' in _I_['trans']:
                amp_project = self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=1).amp
                pi_dur_project = self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=1).pi
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                    gateMW = True,
                    amplitudes=[amp_project],
                    frequencies=[3689-0.42],
                    mixer_deg=[-90]
                )

            freq=[30]
            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                   nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'ssr':
                amp = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=0.7).amp
                amp2 = self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=0.7).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=0.7).pi)

                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[[3546.65, 5686.14]], wait_dur=0.0, robust=False,
                        nuc='29Si8_A2', mixer_deg=-90, eom_ampl=0.0, 
                        step_idx=0, laser_dur=5.0, length_mus_mw = pi_dur, amplitudes=[amp,amp2], repetitions = 10
                        )
            mcas.asc(length_mus=0.512, name='sequence wait 2')

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

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # creating lists with alternating longest and shortest entries. Two neighbouring
    # entries always have same combined duration --> same noise over whole measurement. 
    lst = np.linspace(0,100,400).tolist()
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
            ('t_read',[1.]),
            ('init_time', [80.]),
            ('readout', ['A2']),
            ('omega',[2.]),
            ('trans',['C']),
            ('tau', E.round_length_mus_to_x_multiple_ps(ordered_list)),
            ('readout_phase', [0, 180])
        )
    )
    nuclear.number_of_simultaneous_measurements =  4#len(nuclear.parameters['tau'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 5*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    nuclear.pld.fit_function = 'lorentz'
    settings()
    print('run_fun started')
    nuclear.run(abort)