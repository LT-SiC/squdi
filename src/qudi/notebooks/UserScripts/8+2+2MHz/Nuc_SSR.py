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
        trans = {}
        for t in ['L','C','R']:
            for i in range(0,8):
                trans[t+str(i+1)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]:[-0.5,0.5],
                                                        self.queue._transition_tracker.si29_list[1]:[-0.5,0.5],
                                                        self.queue._transition_tracker.si29_list[2]:[-0.5,0.5]}, ms_trans=t)[i]
                
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ###
            if 'm' in _I_['state']:
                if _I_['read_freq'] == 1:
                    freqs = [trans['L1'], trans['L2'], trans['L4']]
                else:
                    freqs = [trans['L5'], trans['L6'], trans['L8']]
                transition = 'L' + str(_I_['read_freq'])
                amp = self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['mw_omega']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['mw_omega']).pi)
            elif 'p' in _I_['state']:
                if _I_['read_freq'] == 1:
                    freqs = [trans['R1'], trans['R2'], trans['R4']]
                else:
                    freqs = [trans['R5'], trans['R6'], trans['R8']]
                transition = 'R' + str(_I_['read_freq'])
                amp = self.queue.tt.rp('e_rabi_ou950deg-90-R', omega=_I_['mw_omega']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-R', omega=_I_['mw_omega']).pi)
            
            rf_dict_swap = {'m12': 11.623-0.042, 'm32': 3.101, 'p32': 5.394, 'p12': 13.991-0.072}
            rf_dict = {'m32': 11.623-0.042, 'm12': 3.101, 'p12': 5.394, 'p32': 13.991-0.072}

            rf_freq_swap = rf_dict_swap[_I_['state']]
            rf_freq = rf_dict[_I_['state']]
            
            rf_dur_swap = {'m12': 15, 'm32': 50, 'p32': 25, 'p12': 15}[_I_['state']]
            rf_dur = {'m32': 15, 'm12': 50, 'p12': 25, 'p32': 15}[_I_['state']]
            
            rf_amp = 0.6

            # def electron rabi
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

            def repump():
                mcas.start_new_segment('Repump', loop_count = 5)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10,64), repump=True, name='Repump')
                mcas.start_new_segment('Decay', loop_count = 1)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64), name='RepumpDecay')
            
            def electron_init(st,t):
                state = st
                segment_length = 10
                loops, correction_mus = shared.calculate_loop_count(t,segment_length)
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

            def rf_pulse(amp, dur, freq):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1')
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    pd2g2 = {"type":"sine", "frequencies":[freq],"amplitudes":[amp], "phase_type_offset": 'absolute'}
                ) 
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5), name='RFSafetyWait2')

            repump()
            electron_init(st=_I_['state'], t = _I_['init_time'])
            cnot(amp, pi_dur, freqs)
            rf_pulse(rf_amp, rf_dur_swap, rf_freq_swap)

            ### READOUT ###
            ampL = self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['mw_omega']).amp
            ampR = self.queue.tt.rp('e_rabi_ou950deg-90-R', omega=_I_['mw_omega']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['mw_omega']).pi)

            if _I_['readout']=='ssr':
                
                # Conditional init on 29si8, unconditional on 2.2.
                freqs_L = self.queue.tt.mfl({'29si8': [-0.5],'29si2.2a': [-0.5, .5],'29si2.2b': [-0.5, .5]}, ms_trans='L')
                freqs_R = self.queue.tt.mfl({'29si8': [-0.5],'29si2.2a': [-0.5, .5],'29si2.2b': [-0.5, .5]}, ms_trans='R')
                freqs = np.unique(np.append(freqs_L,freqs_R)) # to remove double occurence of 2.2 up + 2.2 down transition
                amps = [ampL]*len(freqs_L)
                amps.extend([ampR]*len(freqs_R))
                sna.ssr(mcas = mcas, queue=self.queue,
                        frequencies=[freqs],
                        wait_dur=0.0,
                        robust=False,
                        nuc='13c5000_A2',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        step_idx=0,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read1']),
                        length_mus_mw = pi_durL,
                        amplitudes=amps,
                        repetitions = int(_I_['n_ssr1']) 
                        )
                if _I_['single_side']:

                    if _I_['flip']:

                        def rf_pulse2(freq1, freq2, dur=None):
                            mcas.start_new_segment('RF pi')
                            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1')
                            if dur is None:
                                dur = rf_dur
                            mcas.asc(
                                length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                                name='nuc',
                                pd2g2={"type": "sine", "frequencies": [freq1], "amplitudes": [_I_['rf_amp']],
                                       "phase_type_offset": 'absolute'}
                            )
                            mcas.asc(
                                length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                                name='nuc',
                                pd2g2={"type": "sine", "frequencies": [freq2], "amplitudes": [_I_['rf_amp2']],
                                       "phase_type_offset": 'absolute'}
                            )
                            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5), name='RFSafetyWait2')

                        rf_pulse2(freq1=3.224, freq2=5.512, dur=63.055)

                    sna.ssr(mcas = mcas, queue=self.queue,
                            frequencies=[[trans['L1'], trans['R1'], trans['L2'], trans['R2']]],
                            wait_dur=0.0,
                            robust=False,
                            nuc='13c5000_A2',
                            mixer_deg=-90,
                            eom_ampl=0.0,
                            step_idx=1,
                            laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read2']),
                            length_mus_mw = pi_durL,
                            amplitudes=[ampL,ampR,0,0],
                            repetitions = int(_I_['n_ssr2'])
                            )


                else:
                    freqs_L_down = self.queue.tt.mfl({'29si8': [-0.5],'29si2.2a': [-0.5, 0.5],'29si2.2b': [-.5, 0.5]}, ms_trans='L')
                    freqs_R_down = self.queue.tt.mfl({'29si8': [-0.5],'29si2.2a': [-0.5, 0.5],'29si2.2b': [-0.5, 0.5]}, ms_trans='R')
                    freqs_down = np.unique(np.append(freqs_L_down,freqs_R_down)) # to remove double occurence of 2.2 up + 2.2 down transition
                    freqs_L_up = self.queue.tt.mfl({'29si8': [0.5],'29si2.2a': [.5, 0.5],'29si2.2b': [.5, 0.5]}, ms_trans='L')
                    freqs_R_up = self.queue.tt.mfl({'29si8': [0.5],'29si2.2a': [.5, 0.5],'29si2.2b': [.5, 0.5]}, ms_trans='R')
                    freqs_up = np.unique(np.append(freqs_L_up,freqs_R_up)) # to remove double occurence of 2.2 up + 2.2 down transition        
                    amps = [ampL]*len(freqs_L_down)
                    amps.extend([ampR]*len(freqs_R_down))
                
                    sna.ssr(mcas = mcas, queue=self.queue,
                            frequencies=[freqs_down, freqs_up],
                            wait_dur=0.0,
                            robust=False,
                            nuc='13c5000_A2',
                            mixer_deg=-90,
                            eom_ampl=0.0,
                            step_idx=1,
                            laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read2']),
                            length_mus_mw=pi_durL,
                            amplitudes=amps,
                            repetitions=int(_I_['n_ssr2'])
                            )
                sna.ssr(mcas=mcas, queue=self.queue,
                        frequencies=[1000],
                        wait_dur=0.0,
                        robust=False,
                        nuc='charge_state',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        step_idx=2,
                        )

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['init', '<', 1, 0, 0, 1],
        ['result', '>', 0, 3, 0, 2], # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 5, 1, 0, 1],
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
    nuclear.save_smartly = False
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

    nuclear.ple_refocus_interval = 180
    nuclear.confocal_refocus_interval = 1  # seconds
    nuclear.odmr_refocus_interval= 6000

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(20)),
            ('A2_power',[5]),
            ('mw_omega',[0.2]),
            ('nuc',[nuclear.queue._transition_tracker.si29_list[0]]),
            ('t_read2', [1.024*4, 1.024*5, 1.024*6]),
            ('t_read1', [1.024*1, 1.024*2, 1.024*3, 1.024*4, 1.024*5]),
            ('wait_dur', [0.512]),
            ('rf_amp', [0.4]),
            ('rf_amp2', [0.4]),
            ('init_time', [100]),
            ('state', ['m32']),
            ('n_ssr2', [50,100,150,200,250,300,400]),
            ('n_ssr1', [50,100,150,200,250,300,400,500,600]),
            ('readout', ['ssr']),
            ('single_side', [False]),
            ('read_freq',[2]),
            ('flip', [False]),
            ('ssr1_C', [-0.5]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 1

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 60*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)