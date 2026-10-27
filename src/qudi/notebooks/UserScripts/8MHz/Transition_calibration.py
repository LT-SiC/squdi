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

trans = {'L1': 36.35, 'L2': 40.35, 'C1': 35+69.7, 'C2': 39+69.7, 'R1': 36.35+140, 'R2': 40.35+140}
print("L", (trans['L1']+trans['L2'])/2)
print("C", (trans['C1']+trans['C2'])/2)
print("R", (trans['R1']+trans['R2'])/2)
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
            mw_init32L1 = 0.025
            mw_init32L2 = 0.025
    elif 'm' in state:
            mw_init32R1 = 0.025
            mw_init32R2 = 0.025
    pd2g2 = {
        'type':'sine',
        'phases':[0],
        'amplitudes':[
                    mw_init32L1,
                    mw_init32L2,
                    mw_init32R1,
                    mw_init32R2],        
        'frequencies':freqs
    }
    
    return pd2g2


def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        sequence_name = 'Electron_rabi_test' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():
            
            def erabi(freq, length, amp, phase=0.0):
                mcas.asc(
                    gateMW = True,
                    gateRF = True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(length), 
                    name='erabi',
                    pd2g2 = {'type':'sine', 'phases':[phase], 'amplitudes':[amp], 'frequencies':[freq]}),

            ### REPUMP ###
            mcas.start_new_segment('Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(50.0,64), repump=True, name='Repump')
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64))
            
            ### INITIALIZATION ###
            state = {"L": "m12", "C": "p12", "R": "p12"}[_I_['trans']]
            segment_length = 10
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                # A1= '32' in state,
                # A2 = '12' in state,
                A1= 'A1' in _I_['init_laser'],
                A2 = 'A2' in _I_['init_laser'],
                gateMW = True,
                gateRF = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g2 = init_state_drive(state, [trans['L1'],trans['L2'],trans['R1'],trans['R2']]),
                
            ) 
            mcas.start_new_segment(name='sequence', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5))

            # if _I_['trans'] == 'L':
            #     amp = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=_I_['omega']).amp
            #     pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=_I_['omega']).pi)
            # elif _I_['trans'] == 'C':
            #     amp = self.queue.tt.rp('e_rabi_ou500deg-90-C', omega=_I_['omega']).amp
            #     pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=_I_['omega']).pi)
            # else:
            #     amp = self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=_I_['omega']).amp
            #     pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou500deg-90-R', omega=_I_['omega']).pi)
            amp = _I_['amp']
            #pi_dur = 1/_I_['omega']
            pi_dur = _I_['pi_dur']
            freq = {"L": (trans['L1']+trans['L2'])/2, "C": (trans['C1']+trans['C2'])/2, "R": (trans['R1']+trans['R2'])/2}[_I_['trans']]+_I_['mw_freq']
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, gateRF = True, name='gateMW')
            erabi(freq, pi_dur,amp)
            if 'C' in _I_['trans']:
                amp_project = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=1).amp
                pi_dur_project = self.queue.tt.rp('e_rabi_ou500deg-90-L', omega=1).pi
                amp_project = 0.1
                pi_dur_project = .5
                erabi((trans['L1']+trans['L2'])/2+_I_['mw_freq'], pi_dur_project,amp_project)

            freq=[3000]
            if _I_['init_laser'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['init_laser'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
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
    nuclear.check_A2_power = False
    nuclear.do_repump = False

    nuclear.ple_refocus_interval = 500
    nuclear.confocal_refocus_interval = 1800  # seconds
    nuclear.odmr_refocus_interval= 1800

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(10)),
            ('A2_power',[5]),
            #('omega',[0.5,1,2]),
            ('t_read',[3.]),
            #('readout', ['A2']),
            ('init_time', [100, 30]),
            ('init_laser', ['A2','A1']),
            ('trans',['L', 'R']),
            ('pi_dur',[0.366*3]),
            ('amp',[0.05/3]),
            ('mw_freq', np.linspace(-9,9,120)),
        )
    )
    nuclear.number_of_simultaneous_measurements =  20

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10*1e6
    nuclear.pld.fit_function='lorentz'
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)