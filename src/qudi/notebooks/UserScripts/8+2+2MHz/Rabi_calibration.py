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

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        
        
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():
            freqs_all_L = np.unique(self.queue.tt.mfl({'29si2.2a': [-0.5,0.5]}, ms_trans='L'))
            freqs_all_C = np.unique(self.queue.tt.mfl({'29si2.2a': [-0.5,0.5]}, ms_trans='C'))
            freqs_all_R = np.unique(self.queue.tt.mfl({'29si2.2a': [-0.5,0.5]}, ms_trans='R'))
            
            ### REPUMP ###
            sna.repump(mcas, 10)
            
            ### INITIALIZATION ###
            state = {"L": "-0.5", "C": "-0.5", "R": "+0.5"}[_I_['trans']]
            sna.electron_init(mcas, state, _I_["init_time"], freqs_all_L, freqs_all_R)
            
            mcas.start_new_segment(name='sequence', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1))
            if _I_['trans'] == 'L':
                amp = self.queue.tt.rp('e_rabi_ou950deg-90-L', amp=_I_['amp']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-L', amp = _I_['amp']).pi)
                freq1,freq2 =freqs_all_L
            elif _I_['trans'] == 'C':
                amp = self.queue.tt.rp('e_rabi_ou950deg-90-C', amp=_I_['amp']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-R', amp = _I_['amp']).pi)
                freq1,freq2 =freqs_all_C
            else:
                amp = self.queue.tt.rp('e_rabi_ou950deg-90-R', amp=_I_['amp']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-R', amp = _I_['amp']).pi)
                freq1,freq2 =freqs_all_R
            
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True, name='gateMW')            
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(_I_['tau']),
                gateMW=True,
                amplitudes=[_I_['amp']],
                frequencies=[freq2], 
                mixer_deg=[-90]
            )
            if 'C' in _I_['trans']:
                amp_project = self.queue.tt.rp('e_rabi_ou950deg-90-R', amp = 0.45).amp
                #print(amp_project)
                pi_dur_project = self.queue.tt.rp('e_rabi_ou950deg-90-R', amp = 0.45).pi
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                    gateMW = True,
                    amplitudes=[amp_project, amp_project],
                    frequencies=freqs_all_R,
                    mixer_deg=[-90,-90]
                )

            if _I_['readout'] == 'A2':
                sna.ssr(mcas=mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                        nuc='ple_A2',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        step_idx=0,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'A1':
                sna.ssr(mcas=mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                        nuc='ple_A1',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        step_idx=0,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))

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
    nuclear.check_A2_power = False
    nuclear.do_repump = False

    nuclear.ple_refocus_interval = 600
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(10)),
            ('A2_power', [5]),
            ('init_time', [30]),
            ('t_read', [2]),
            #('nuc',[nuclear.queue._transition_tracker.si29_list[0]]),
            #('readout_proj', ['L1']),
            ('trans', ['L', 'C', 'R']),
            ('amp', [0.2, 0.4, 0.6, 0.8]),
            ('readout', ['A2']),
            ('tau', np.arange(0, 13.5, .256)),
        )
    )
    nuclear.number_of_simultaneous_measurements = len(nuclear.parameters['tau'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 40*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)