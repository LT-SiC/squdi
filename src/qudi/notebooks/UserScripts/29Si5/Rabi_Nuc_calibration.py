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
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.c13_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ###
            if 'm' in _I_['state']:
                transition = 'L2'
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi)
            elif 'p' in _I_['state']:
                transition = 'R2'
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).pi)
            
            rf_freq = {'m32': 8.99172,  'm12':4.16956, 'p12': 0.649641, 'p32': 5.465629}[_I_['state']]
            rf_dur = _I_['rf_dur']
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
                mixer_deg=[-90], 
                phase_offset_type = 'absolute'
                )

            def electron_init(st,t):
                state = st
                segment_length = 5
                loops, correction_mus = shared.calculate_loop_count(t,segment_length)
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

            def rf_pulse(freq,dur=None,laser_on="off"):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.01), name='RFSafetyWait1', gateRF = True)
                if dur is None:
                    dur = rf_dur
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    A1=( "32" in _I_["state"]) & (laser_on=="on"), #turn the laser on that is non resonant with the population state
                    A2=( "12" in _I_["state"]) & (laser_on=="on"), #turn the laser on that is non resonant with the population state
                    gateRF = True,
                    pd2g2 = {"type":"sine", "frequencies":[freq],"amplitudes":[_I_['rf_amp']], "phase_offset_type": 'absolute'}
                ) 
                #mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.0), name='RFSafetyWait2', gateRF = True)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2.0), name='RFSafetyWait2', gateRF = False)

            sna.repump(mcas, dur=20)
            electron_init(st=_I_['state'], t = _I_['init_time'])
            cnot(1.0, pi_dur*10, trans[transition])
            rf_pulse(rf_freq+_I_['rf_freq'], dur=rf_dur,laser_on="off")

            ### READOUT ###
            ampL = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp
            ampR = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi)


            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[[trans['L1'], trans['R1']]],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
                    repetitions=int(_I_['n_ssr1'])
                    )

            
            electron_init(st = _I_['state'], t = _I_['t_reset'])

            mcas.start_new_segment('n rabi', loop_count=1)
            rf_pulse(rf_freq+_I_['rf_freq'], dur=rf_dur,laser_on=_I_["laser"])
            
            # sna.ssr(mcas=mcas, queue=self.queue,
            #         frequencies=[[trans['L1'], trans['R1']], [trans['L2'], trans['R2']]],
            #         wait_dur=_I_['wait_dur'],
            #         robust=False,
            #         nuc='29Si8_A2',
            #         mixer_deg=-90,
            #         eom_ampl=0.0,
            #         step_idx=1,
            #         laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
            #         length_mus_mw=pi_durL,
            #         amplitudes=[ampL, ampR],
            #         repetitions=int(_I_['n_ssr2'])
            #         )
            freq1, freq2 = 'L' + str(_I_['read_freq']), 'R' + str(_I_['read_freq'])
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[[trans[freq1], trans[freq2]]],
                    #frequencies=[[trans['L1'], trans['R1']]],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
                    repetitions=int(_I_['n_ssr2'])
                    )

            
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[500],
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
        ['init', '<', 17, 0, 0, 1], #SSR1
        ['result', '>', 17, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 8, 1, 0, 1],   #CRC
        
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
    nuclear.do_confocal_A1A2_refocus = False
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.do_repump = False
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 30.0
    nuclear.confocal_refocus_interval = 30  # seconds
    nuclear.odmr_refocus_interval= 6000
    nuclear.follow_resonnance_by_counts=False

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(2)),
            ('A2_power',[5]),
            ('omega',[1.4]), # it was 1.7
            ('n_ssr1', [2000]),
            ('n_ssr2', [2000]),
            ('t_read', [1.024*4]),
            ('wait_dur', [0.0]),
            ('rf_amp', list(np.arange(0.6,0.8,0.1))),
            ('init_time', [50]),
            ('state', ['m12','m32','p32']),
            #('state', ['p32']),
            ('laser',["off"]),
            ('rf_dur', np.arange(0,200,5)),
            ('t_reset',[75]),
            ('rf_freq', [0]),
            ('read_freq', [2,1]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 2

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 30*1e6
    nuclear.pld.fit_function = 'cosine'
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)