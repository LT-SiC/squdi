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

#trans = {'L1': 3834.098, 'L2': 3842.675, 'C1': 3903.826, 'C2': 3912.51, 'R1': 3973.492, 'R2': 3982.335} # 8 MHz of GSLAC paper
#trans = {'L1': 3834.384, 'L2': 3843.127, 'C1': 3904.018, 'C2': 3912.766, 'R1': 3974.043, 'R2': 3982.709} # SIL A Defect 6
#trans = {'L1': 3835.833, 'L2': 3844.568, 'C1': 3905.372, 'C2': 3914.037, 'R1': 3975.264, 'R2': 3984.044} # SIL A Defect 5
#trans = {'L1': 3836.91, 'L2': 3845.604, 'C1': 3906.599, 'C2': 3915.385, 'R1': 3976.514, 'R2': 3985.238}
def init_state_drive(state,freqs):
    '''
    State could be "p(m)3(1)2+(-,n)", example m32+, or p32-, p32n 
    '''
    transitions_num=len(freqs)
    zeros=np.zeros(transitions_num//2)
    ones=np.ones(transitions_num//2)
    amplitude=0.1
    if '+' in state:
        amps=np.append(ones*amplitude,zeros)
    elif '-' in state:
        amps=np.append(zeros,ones*amplitude)
    pd2g1 = {
        'type':'sine',
        'phases':[0],
        'amplitudes':amps,        
        'frequencies':freqs
    }
    
    return pd2g1

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
    if '+' in state:
        mw_init32L1 = 0.1
        mw_init32L2 = 0.1
        mw_init32L4 = 0.1
        mw_init32L5 = 0.1
        mw_init32L6 = 0.1
        mw_init32L8 = 0.1
    elif '-' in state:
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
        for idx, _I_ in current_iterator_df.iterrows():
                        # def cnot(amp, dur, freqs):
            #     sna.electron_rabi(
            #     mcas,
            #     new_segment=False,
            #     gateMW = True,
            #     length_mus=E.round_length_mus_to_x_multiple_ps(dur),
            #     amplitudes=np.ones_like(freqs)*amp,
            #     frequencies=freqs,
            #     mixer_deg=np.ones_like(freqs)*(-90)
            #     )
           
            
            ## TODO This needs to go to snippets.
            def electron_init(st,t):
                state = st
                segment_length = 10
                loops, correction_mus  = shared.calculate_loop_count(t,segment_length)
                mcas.start_new_segment(name='init', loop_count = loops)
                mcas.asc(
                    A1= '1.5' in state,
                    A2 = '0.5' in state,
                    gateMW = True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                    name='resonant_init',
                    pd2g1 = init_state_drive(state, np.append(freqs_all_L, freqs_all_R))
                ) 
                mcas.start_new_segment(name='sequence', loop_count = 1)
                mcas.asc(
                    A1= '1.5' in state,
                    A2 = '0.5' in state,
                    gateMW = True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus), 
                    name='resonant_init',
                    pd2g1 = init_state_drive(state, np.append(freqs_all_L, freqs_all_R))
                ) 
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name = 'Init Decay')  

            
            ## TODO replace with sna.nuclear_rabi
            def rf_pulse(amp, dur, freq):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1')
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    pd2g2 = {"type":"sine", "frequencies":[freq],"amplitudes":[amp], "phase_type_offset": 'absolute'}
                ) 
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5), name='RFSafetyWait2')

            
            ## Not needed for now...
            def rf_pulse2(freq1,freq2,dur=None):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1')
                if dur is None:
                    dur = rf_dur
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    pd2g2 = {"type":"sine", "frequencies":[freq1],"amplitudes":[_I_['rf_amp']], "phase_type_offset": 'absolute'}
                )
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    pd2g2={"type": "sine", "frequencies": [freq2], "amplitudes": [_I_['rf_amp2']],
                           "phase_type_offset": 'absolute'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5), name='RFSafetyWait2')

            sna.repump(mcas)
            
            #electron_init(st=_I_['state'], t = _I_['init_time'])

            # Conditional flip of electron
            # if 'm' in _I_['state']:
            #     if _I_['read_freq'] == 1:
            #         freqs = [trans['L1'], trans['L2'], trans['L4']]
            #     else:
            #         freqs = [trans['L5'], trans['L6'], trans['L8']]
            #     transition = 'L' + str(_I_['read_freq'])
            #     amp = self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['mw_omega']).amp
            #     pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['mw_omega']).pi)
            # elif 'p' in _I_['state']:
            #     if _I_['read_freq'] == 1:
            #         freqs = [trans['R1'], trans['R2'], trans['R4']]
            #     else:
            #         freqs = [trans['R5'], trans['R6'], trans['R8']]
            #     transition = 'R' + str(_I_['read_freq'])
            #     amp = self.queue.tt.rp('e_rabi_ou950deg-90-R', omega=_I_['mw_omega']).amp
            #     pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-R', omega=_I_['mw_omega']).pi)
            
            
            # Here init cnot
            #cnot(amp, pi_dur, freqs)
            #rf_pulse(rf_amp, rf_dur_swap, rf_freq_swap)

            ### READOUT ###
            ampL = self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['omega']).amp
            ampR = self.queue.tt.rp('e_rabi_ou950deg-90-R', omega=_I_['omega']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['omega']).pi)
            pi_durR = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-R', omega=_I_['omega']).pi)

            # Conditional init on both 2.2 to be not in left most (that is why second guy is in both states)

            # init_state = '+++'
            # That means that we need to probe all but '+++'


            #in principle should work with any init state.

            init_state = _I_['state_init']
            mi = {'n':[-0.5,0.5], '-':[-0.5], '+':[0.5]}

            td = {}
            nucs = ['29si8', '29si2.2a', '29si2.2b']
            for ii, nuci in enumerate(nucs):
                td[nuci] = mi[init_state[ii]]

            freqs_all_L = np.unique(self.queue.tt.mfl({'29si8': [-0.5, .5],'29si2.2a': [-0.5,0.5],'29si2.2b': [-0.5,0.5]}, ms_trans='L'))
            freqs_all_R = np.unique(self.queue.tt.mfl({'29si8': [-0.5, .5],'29si2.2a': [-0.5,0.5],'29si2.2b': [-0.5,0.5]}, ms_trans='R'))
            
            freqs_init_L = np.unique(self.queue.tt.mfl(td, ms_trans='L'))
            freqs_init_R = np.unique(self.queue.tt.mfl(td, ms_trans='R'))

            freqs_all_but_init_L = np.setdiff1d(freqs_all_L, freqs_init_L)
            freqs_all_but_init_R = np.setdiff1d(freqs_all_R, freqs_init_R)

            freqs = np.append(freqs_all_but_init_L,freqs_all_but_init_R) # to remove double occurence of 2.2 up + 2.2 down transition
            freqs_m = np.append(freqs_init_L, freqs_init_R)
            amps = [ampL]*freqs_all_but_init_L.shape[0] + [ampR]*freqs_all_but_init_R.shape[0]
            amps_m = [ampL]*freqs_init_L.shape[0] + [ampR]*freqs_init_R.shape[0]

            print(f"freqs_all_L={freqs_all_L}",f"freqs_all_R={freqs_all_R}",f"freqs_init_L={freqs_init_L}",f"freqs_init_R={freqs_init_R}",
                  f"freqs_all_but_init_L={freqs_all_but_init_L}",f"freqs_all_but_init_R={freqs_all_but_init_R}",sep="\n")

            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[freqs_m], #[[*freqs_m,*freqs]],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='13c5000_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read1']),
                    length_mus_mw=pi_durL,
                    amplitudes=amps_m,#[*amps_m,*amps],
                    repetitions=int(_I_['n_ssr1'])
                    )
            
            #init_state_drive(_I_["transition"],np.append(freqs_all_L,freqs_all_R))
            electron_init(_I_["transition"][-4:], _I_["init_time"])
            
            dur= E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-R', omega = _I_['omega']).pi)
            amp= self.queue.tt.rp('e_rabi_ou950deg-90-R', omega = _I_['omega']).amp
            freq=np.mean(np.array([freqs_all_R[1], freqs_all_R[4]])) +_I_['mw_freq'] #Hardcoded here

            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')

            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                gateMW=True,
                amplitudes=[amp],
                frequencies=[freq], 
                mixer_deg=[-90]
            )

            if 'C' in _I_['trans']:
                amp_project = 0.4#self.queue.tt.rp('e_rabi_ou500deg-90-L', amp=amp).amp
                #print(amp_project)
                pi_dur_project = self.queue.tt.rp('e_rabi_ou500deg-90-L', amp=amp_project).pi
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                    gateMW = True,
                    amplitudes=[amp_project, amp_project],
                    frequencies=[trans['L1'], trans['L2']],
                    mixer_deg=[-90,-90]
                )

            if _I_['readout'] == 'A2':
                sna.ssr(mcas=mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                        nuc='ple_A2',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        step_idx=1,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            elif _I_['readout'] == 'A1':
                sna.ssr(mcas=mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                        nuc='ple_A1',
                        mixer_deg=-90,
                        eom_ampl=0.0,
                        step_idx=1,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))

            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.512), name='sequence wait 2')
            
        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['init', '<', 3, 0, 0, 1],
        ['result', '>', 0, 0, 0, 1],
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
            ('wait_dur', [0.512]),
            ('omega', [0.5]),
            ("nuc",['29Si2.2']),
            ('readout', ['A1','A2']),
            ('transition', ['29si8 ms+1.5','29si8 ms-1.5']),
            ('init_time', [100]),
            ('n_ssr1', [200]),
            ('state_init', ['---','+++','n--', 'n++', 'nn-',  'nn+']),
            ('t_read', [5]),
            ('t_read1', [4*1.024]),
            ('readout_proj', ['R1']),
            ('trans', ['R1']),
            #('amp', [0.8]),
            ('tau', [1.3*2]),
            ("mw_freq",np.arange(-9,9,2*0.128)),
        )
    )
    nuclear.number_of_simultaneous_measurements = 1#len(nuclear.parameters['mw_freq'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)