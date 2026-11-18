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

trans = {'L1': 3834.935, 'L2': 3843.55, 'C1': 3904.476, 'C2': 3913.207, 'R1': 3974.368, 'R2': 3983.176}
trans = {'L1': 3834.21, 'L2': 3842.941, 'C1': 3904.034, 'C2': 3912.748, 'R1': 3973.858, 'R2': 3982.611}
trans = {'L1': 3835.833, 'L2': 3844.568, 'C1': 3905.372, 'C2': 3914.037, 'R1': 3975.264, 'R2': 3984.044}
trans = {'L1': 3834.773, 'L2': 3843.468, 'C1': 3904.489, 'C2': 3913.26, 'R1': 3974.429, 'R2': 3983.221}
trans = {'L1': 3835.978, 'L2': 3844.685, 'C1': 3905.698, 'C2': 3914.325, 'R1': 3975.332, 'R2': 3984.09}
trans = {'L1': 3836.91, 'L2': 3845.604, 'C1': 3906.599, 'C2': 3915.385, 'R1': 3976.514, 'R2': 3985.238}
trans = {'L1': 3836.828, 'L2': 3845.692, 'C1': 3906.55, 'C2': 3915.358, 'R1': 3976.546, 'R2': 3985.308}
trans = {'L1': 3836.942+0.207968+0.75, 'L2': 3845.638+0.207968+0.75, 'C1': 3906.764+0.090027+0.72, 'C2': 3915.412+0.090027+0.72, 'R1': 3976.602+0.029317+0.8, 'R2': 3985.282+0.029317+0.8}

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
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]
        
        sequence_name = 'Electron_rabi_test' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ###
            if 'm' in _I_['state']:
                transition = 'L' + str(_I_['read_freq'])
                amp = self.queue.tt.rp('e_rabi_ou750deg-90-L', period=_I_['period']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou750deg-90-L', period=_I_['period']).pi)
            elif 'p' in _I_['state']:
                transition = 'R' + str(_I_['read_freq'])
                amp = self.queue.tt.rp('e_rabi_ou750deg-90-R', period=_I_['period']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou750deg-90-R', period=_I_['period']).pi)
            
            rf_dict={'m32': 8.406, 'm12': 3.583, 'p12': 1.15, 'p32': 6.053}
            rf_freq = {'m32': 11.942, 'm12': 3.224, 'p12': 5.512, 'p32': 14.27}[_I_['state']]
            #rf_dur = {'m32': 19.586, 'm12': 63.055, 'p12': 38.512, 'p32': 17.986}[_I_['state']]
            rf_dur = {'m32': 41., 'm12': 63.055, 'p12': 28.5, 'p32': 41.6}[_I_['state']]
            
            # def electron rabi
            def cnot(amp, dur, freq):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True)
                sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                amplitudes=[amp],
                frequencies=[freq],
                mixer_deg=[-90]
                )

            def repump():
                mcas.start_new_segment('Repump', loop_count = 5)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10,64), repump=True, name='Repump')
                mcas.start_new_segment('Decay', loop_count = 1)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64), name='RepumpDecay')
            
            def electron_init():
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
                    pd2g1 = init_state_drive(state, [trans['L1'],trans['L2'],trans['R1'],trans['R2']]),
                    ) 
                mcas.start_new_segment(name='sequence', loop_count = 1)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name = 'Init Decay')  

            def rf_pulse(freq):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1')
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(rf_dur), 
                    name='nuc',
                    pd2g2 = {"type":"sine", "frequencies":[freq],"amplitudes":[_I_['rf_amp']], "phase_type_offset": 'absolute'}
                ) 
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5), name='RFSafetyWait2')

            repump()
            electron_init()
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(rf_dict[_I_['state']])

            ### READOUT ###
            ampL = self.queue.tt.rp('e_rabi_ou750deg-90-L', period=_I_['period']).amp
            ampR = self.queue.tt.rp('e_rabi_ou750deg-90-R', period=_I_['period']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou750deg-90-L', period=_I_['period']).pi)
            
            if _I_['readout']=='ssr':
                sna.ssr(mcas = mcas, queue=self.queue,
                        frequencies=[[trans['L'+_I_['ssr1_C']],trans['R'+_I_['ssr1_C']]]],
                        wait_dur=0.0,
                        robust=False,
                        nuc='13c5000_A2',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        step_idx=0,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read1']),
                        length_mus_mw = pi_durL,
                        amplitudes=[ampL,ampR],
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
                            frequencies=[[trans['L1'],trans['R1'],trans['L2'], trans['R2']]],
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
                    sna.ssr(mcas=mcas, queue=self.queue,
                            frequencies=[[trans['L1'], trans['R1']],[trans['L2'], trans['R2']]],
                            wait_dur=0.0,
                            robust=False,
                            nuc='13c5000_A2',
                            mixer_deg=-90,
                            eom_ampl=0.0,
                            step_idx=1,
                            laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read2']),
                            length_mus_mw=pi_durL,
                            amplitudes=[ampL, ampR],
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
            
            elif _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                   nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))

            
            #sna.ssr(mcas = mcas, queue=self.queue, frequencies=[trans['L1'],trans['R1']], wait_dur=0.0, robust=False,
             #       nuc='29Si8_A2', mixer_deg=-90, eom_ampl=0.0, 
              #      step_idx=1, laser_dur=_I_['t_read'], length_mus_mw = pi_dur1, amplitudes=[amp1,amp2], repetitions = int(_I_['n_ssr'])
              #      )

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['init', '<', 1, 0, 0, 1],
        ['result', '>', 4, 0, 0, 2], # Put "int(_I_['n_ssr']" as nlp_per_point?
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
            ('period',[2]),
            ('nuc',[nuclear.queue._transition_tracker.si29_list[0]]),
            ('t_read2', [1.024*2,1.024*3,1.024*4,1.024*5,1.024*6,1.024*7]),
            ('t_read1', [1.024*1,1.024*2,1.024*3,1.024*4,1.024*5,1.024*6,1.024*7]),
            ('wait_dur', [0.512]),
            ('rf_amp', [0.4]),
            ('rf_amp2', [0.4]),
            ('init_time', [100]),
            ('state', ['m32']),
            ('n_ssr2', [100,200,300,400,500,600]),
            ('n_ssr1', [100,200,300,400,500,600]),
            #('rf_freq', np.arange(-0.025,0.025,0.008)),
            ('readout', ['ssr']),
            ('single_side', [False]),
            ('read_freq',[2]),
            ('flip', [False]),
            ('ssr1_C', ['1','2']), #init by selecting not 1 or not 2. - non destructive.
        )
    )
    nuclear.number_of_simultaneous_measurements = 2

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 60*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)