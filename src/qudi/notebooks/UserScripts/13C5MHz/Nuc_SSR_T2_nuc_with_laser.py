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
                transition = 'R2' # use R2, such that after init, system is in state 2 --> SSR1 (with L1+R1) is more likely to be dark --> Init successful
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).pi)

            rf_freq = {'m32': 8.99166,  'm12':4.169582, 'p12': 0.649641, 'p32': 5.465889}[_I_['state']]
            rf_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('13c5 ms'+_I_['state'].replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5'), amp=0.5).pi)
            rf_amp = self.queue.tt.rp('13c5 ms'+_I_['state'].replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5'), amp=0.5).amp

            # def electron rabi
            def cnot(amp, dur, freq):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    amplitudes=[amp],
                    frequencies=[freq],
                    mixer_deg=[-90]
                )

            def rf_pulse(freq, amp=None, dur=None, phase=0):
                amp = rf_amp if amp is None else amp
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1', gateRF = True)
                if dur is None:
                    dur = rf_dur
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    gateRF = True,
                    pd2g2={"type": "sine", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
                           "phase_type_offset": 'absolute'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)

            sna.repump(mcas, 10)
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(rf_freq)

            ### READOUT ###
            ampL = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp
            ampR = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi)
            
            sna.ssr(mcas = mcas, queue=self.queue,
                    frequencies=[[trans['L1'], trans['R1']]],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
                    length_mus_mw = pi_durL,
                    amplitudes=[ampL,ampR],
                    repetitions = int(_I_['n_ssr1']) 
                    )
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            
            A1_val = _I_['laser'] == 'A1'
            A2_val = _I_['laser'] == 'A2'

            mcas.asc(length_mus=_I_['wait'], name='wait')
            segment_length = E.round_length_mus_to_x_multiple_ps(500, 64)
            lc, correction_mus = shared.calculate_loop_count(_I_['tau'], segment_length)
            print(lc, 'loop')
            #Here T2 of the nuc spin...

            ##### HE sequence of the Nuc in -3/2.

            ### PI /2 ###
            rf_pulse(rf_freq, dur=rf_dur/ 2.0)

            ### TAU ###
            
            if lc > 0:
                mcas.start_new_segment(name='tau', loop_count=int(lc))
                mcas.asc(length_mus=segment_length, name='tau', A1 = A1_val, A2= A2_val)
                mcas.start_new_segment(name='tau', loop_count=1)
                mcas.asc(length_mus=correction_mus, name='tau', A1 = A1_val, A2= A2_val)
            else:
                mcas.start_new_segment(name='tau', loop_count=1)
                mcas.asc(length_mus=_I_['tau'], name='tau', A1 = A1_val, A2= A2_val)
            
            ### PI ###
            rf_pulse(rf_freq, dur=rf_dur)
            ### TAU ###
            
            if lc > 0:
                mcas.start_new_segment(name='tau', loop_count=int(lc))
                mcas.asc(length_mus=segment_length, name='tau', A1 = A1_val, A2= A2_val)
                mcas.start_new_segment(name='tau', loop_count=1)
                mcas.asc(length_mus=correction_mus, name='tau', A1 = A1_val, A2= A2_val)
            else:
                mcas.start_new_segment(name='tau', loop_count=1)
                mcas.asc(length_mus=_I_['tau'], name='tau', A1 = A1_val, A2= A2_val)

            if lc > 0:
                mcas.start_new_segment(name='tau', loop_count=int(lc))
                mcas.asc(length_mus=segment_length, name='tau', A1 = A1_val, A2= A2_val)
                mcas.start_new_segment(name='tau', loop_count=1)
                mcas.asc(length_mus=correction_mus, name='tau', A1 = A1_val, A2= A2_val)
            else:
                mcas.start_new_segment(name='tau', loop_count=1)
                mcas.asc(length_mus=_I_['tau'], name='tau', A1 = A1_val, A2= A2_val)
            
            ### PI ###
            rf_pulse(rf_freq, dur=rf_dur)
            ### TAU ###
            
            if lc > 0:
                mcas.start_new_segment(name='tau', loop_count=int(lc))
                mcas.asc(length_mus=segment_length, name='tau', A1 = A1_val, A2= A2_val)
                mcas.start_new_segment(name='tau', loop_count=1)
                mcas.asc(length_mus=correction_mus, name='tau', A1 = A1_val, A2= A2_val)
            else:
                mcas.start_new_segment(name='tau', loop_count=1)
                mcas.asc(length_mus=_I_['tau'], name='tau', A1 = A1_val, A2= A2_val)
            ### PI / 2 ###
            rf_pulse(rf_freq, dur=rf_dur/ 2.0, phase=_I_['readout_phase'])
            
            if False: #p32 pulses as well.
                state = 'p'+_I_['state'][1:]
                rf_freq = {'m32': 8.99166,  'm12':4.169582, 'p12': 0.649641, 'p32': 5.465889}[state]
                rf_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp(
                        '13c5 ms'+state.replace('p','+').replace('m', '-').replace('32',  '1.5').replace('12', '0.5'), amp=0.5).pi)
                rf_amp = self.queue.tt.rp(
                    '13c5 ms'+state.replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5'), amp=0.5
                    ).amp
                rf_pulse(rf_freq+_I_['rf_pulse2'], amp =rf_amp) # Flip in p32 #Erik used this, I dont know why
        

            ## SSR
        
            sna.ssr(mcas = mcas, queue=self.queue,
                    frequencies=[[trans['L1'],trans['R1']]],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
                    length_mus_mw = pi_durL,
                    amplitudes=[ampL,ampR],
                    repetitions = int(_I_['n_ssr2']) 
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
        ['init', '<', 12, 0, 0, 1],
        ['result', '>',20, 0, 0, 1], # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 10, 1, 0, 1],
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
    nuclear.do_confocal_A1A2_refocus = False
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.do_repump = False
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 30
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval= 6000

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    lst =   np.logspace(1, 5.5,15).tolist()
    lst1 = lst[0::2]
    lst2 = lst[1::2][::-1]
    ordered_list = []
    while len(lst2)>0:
        ordered_list.append(lst2.pop())
        ordered_list.append(lst1.pop())
    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(20)),
            ('A2_power', [5]),
            ('omega', [1.9]),
            ('t_read', [1.024*3]),
            ('init_time', [50]),
            ('state', ['m32']),
            ('t_reset', [50]),
            ('wait', [0.0]),
            ('laser', ['off', 'A1']),
            ('single', [True]),
            ('n_ssr2', [2000]),
            ('n_ssr1', [2000]),
            ('tau', E.round_length_mus_to_x_multiple_ps(ordered_list)),
            ('readout_phase', [0,180.0])
        )
    )
    nuclear.number_of_simultaneous_measurements = 4

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 160*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)