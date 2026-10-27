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
from qtpy import QtCore


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
    mw_init32L4 = 0
    mw_init32L5 = 0
    mw_init32L6 = 0
    mw_init32L8 = 0
    mw_init32R1 = 0
    mw_init32R2 = 0
    mw_init32R4 = 0
    mw_init32R5 = 0
    mw_init32R6 = 0
    mw_init32R8 = 0
    ## MW drive
    if 'p' in state:
        mw_init32L1 = 0.1
        mw_init32L2 = 0.1
        mw_init32L4 = 0.1
        mw_init32L5 = 0.1
        mw_init32L6 = 0.1
        mw_init32L8 = 0.1
    elif 'm' in state:
        mw_init32R1 = 0.1
        mw_init32R2 = 0.1
        mw_init32R4 = 0.1
        mw_init32R5 = 0.1
        mw_init32R6 = 0.1
        mw_init32R8 = 0.1
    pd2g1 = {
        'type':'sine',
        'phases':[0],
        'amplitudes':[
                    mw_init32L1,
                    mw_init32L2,
                    mw_init32L4,
                    mw_init32L5,
                    mw_init32L6,
                    mw_init32L8,
                    mw_init32R1,
                    mw_init32R2,
                    mw_init32R4,
                    mw_init32R5,
                    mw_init32R6,
                    mw_init32R8],        
        'frequencies':freqs
    }
    
    return pd2g1

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        sequence_name = 'Electron_rabi_test' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        trans = {}
        for t in ['L','C','R']:
            for i in range(0,8):
                trans[t+str(i+1)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]:[-0.5,0.5],
                                                        self.queue._transition_tracker.si29_list[1]:[-0.5,0.5],
                                                        self.queue._transition_tracker.si29_list[2]:[-0.5,0.5]}, ms_trans=t)[i]
            
            

        for idx, _I_ in current_iterator_df.iterrows():

            ### DEF ELECTRON RABI ###
            def cnot(amp, dur, freqs):
                sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                amplitudes=np.ones_like(freqs)*amp,
                frequencies=freqs,
                mixer_deg=np.ones_like(freqs)*(-90)
                )

            ### REPUMP ###
            mcas.start_new_segment('Repump', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10.0,64), repump=True, name='Repump')
            mcas.start_new_segment('Decay', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64), name='RepumpDecay')
            
            ### INITIALIZATION ###
            state = _I_['state']
            segment_length = 20
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [trans['L1'],trans['L2'],trans['L4'],trans['L5'],trans['L6'],trans['L8'],
                                                trans['R1'],trans['R2'],trans['R4'],trans['R5'],trans['R6'],trans['R8']])
                ) 
            
            mcas.start_new_segment(name='sequence', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name = 'Init Decay')  

            # Conditional flip of electron
            if 'm' in _I_['state']:
                if _I_['read_freq'] == 1:
                    freqs = [trans['L1'], trans['L2'], trans['L4']]
                else:
                    freqs = [trans['L5'], trans['L6'], trans['L8']]
                transition = 'L' + str(_I_['read_freq'])
                amp = self.queue.tt.rp('e_rabi_ou950deg-90-L', amp=_I_['mw_amp']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-L', amp=_I_['mw_amp']).pi)
            elif 'p' in _I_['state']:
                if _I_['read_freq'] == 1:
                    freqs = [trans['R1'], trans['R2'], trans['R4']]
                else:
                    freqs = [trans['R5'], trans['R6'], trans['R8']]
                transition = 'R' + str(_I_['read_freq'])
                amp = self.queue.tt.rp('e_rabi_ou950deg-90-R', amp=_I_['mw_amp']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-R', amp=_I_['mw_amp']).pi)
            
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True)
            cnot(amp, pi_dur, freqs)

            # Nuclear flip
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1')
            
            #freq = {'m32': 9.05-0.644, 'm12': 4-0.417, 'p12': 1.15, 'p32': 6.053}[_I_['state']]+_I_['rf_freq'] #for the 5 MHz guy of SIL A
            freq = {'m32': 12.0-0.056, 'm12': 3.10415, 'p12': 5.39195, 'p32': 14.3+0.012-0.04}[_I_['state']] # 8 MHz SIL A (In-plane lattice position)
            #freq = {'m32': 10.84-0.0574108886327515, 'm12': 2.83, 'p12': 5.18-0.04215792882722061, 'p32': 13.19-0.0686239800356216}[_I_['state']]+_I_['rf_freq'] 
            #freq = {'m32': 10.9-0.1, 'm12': 2.8, 'p12': 5.17, 'p32': 13.2-0.1}[_I_['state']] #the 8 MHz in sil F
            
            mcas.asc(
                length_mus=E.round_length_mus_to_x_multiple_ps(_I_['rf_dur']), 
                name='nuc',
                pd2g2 = {"type":"sine", "frequencies":[freq],"amplitudes":[_I_['rf_amp']], "phase_type_offset": 'absolute'}
            ) 
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5), name='RFSafetyWait2')

            # flip electron back
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
            cnot(amp, pi_dur, freqs)

            ampL = self.queue.tt.rp('e_rabi_ou950deg-90-L', amp=_I_['mw_amp']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-L', amp=_I_['mw_amp']).pi)
                
            ampR = self.queue.tt.rp('e_rabi_ou950deg-90-R', amp=_I_['mw_amp']).amp
            pi_durR = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-R', amp=_I_['mw_amp']).pi)
            if _I_['readout']=='ssr':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[[trans['R' + str(_I_['read_freq'])],trans['L' + str(_I_['read_freq'])]]], wait_dur=0.0, robust=False,
                        nuc='29Si8_A2', mixer_deg=-90, eom_ampl=0.0, 
                        step_idx=0, laser_dur=_I_['t_read'], length_mus_mw = pi_dur, amplitudes=[ampR,ampL], repetitions = int(_I_['n_ssr'])
                        )
            elif '12' in _I_['state']:
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif '32' in _I_['state']:
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                   nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
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
    nuclear.do_repump = False
    nuclear.check_A2_power = True

    nuclear.ple_refocus_interval = 500
    nuclear.confocal_refocus_interval = 500  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False
    
    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(20)),
            ('A2_power',[5]),
            ('mw_amp',[0.2]),
            ('t_read',[3.]),
            ('rf_amp', [0.2, 0.4, 0.6]),
            ('init_time', [50]),
            #('nuc',[nuclear.queue._transition_tracker.si29_list[0]]),
            #('rf_dur', np.arange(10,71,10)),
            ('state', ['m12', 'p12']),
            ('rf_dur', np.arange(0,100,2)),
            #('n_ssr', [2]),
            ('readout', ['A2']),
            ('read_freq', [1,2]),
        )
    )
    nuclear.number_of_simultaneous_measurements =  2

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 5*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    #sig=QtCore.Signal(object, QtCore.Qt.QueuedConnection)
    #sig.connect(nuclear.run)
    #sig.emit(abort)
    nuclear.run(abort)