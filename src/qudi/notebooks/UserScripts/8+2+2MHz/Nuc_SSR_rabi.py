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
        trans = {}
        for t in ['L','C','R']:
            for i in range(0,8):
                pass
                ## TODO Please Avoid using the trans['L1'] or so in the code from now on, it is prone to errors. use mfl everywhere.

                #trans[t+str(i+1)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]:[-0.5,0.5],
                 #                                       self.queue._transition_tracker.si29_list[1]:[-0.5,0.5],
                  #                                      self.queue._transition_tracker.si29_list[2]:[-0.5,0.5]}, ms_trans=t)[i]
        
        freqs_all_L = np.unique(self.queue.tt.mfl({'29si8': [-0.5, .5],'29si2.2a': [-0.5,0.5],'29si2.2b': [-0.5,0.5]}, ms_trans='L'))
        freqs_all_R = np.unique(self.queue.tt.mfl({'29si8': [-0.5, .5],'29si2.2a': [-0.5,0.5],'29si2.2b': [-0.5,0.5]}, ms_trans='R'))

        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
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
                loops, correction_mus = shared.calculate_loop_count(t,segment_length)
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

            sna.repump(mcas, 50)
            
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
            
            # rf_dict_swap = {'m12': 11.623-0.042, 'm32': 3.101, 'p32': 5.394, 'p12': 13.991-0.072}
            # rf_dict = {'m32': 11.623-0.042, 'm12': 3.101, 'p12': 5.394, 'p32': 13.991-0.072} #8MHz transitions

            # rf_freq_swap = rf_dict_swap[_I_['state']]+_I_['rf_freq']
            # rf_freq = rf_dict[_I_['state']]+_I_['rf_freq']
            
            
            
            #rf_dur_swap = {'m12': 15, 'm32': 50, 'p32': 25, 'p12': 15}[_I_['state']]
            rf_amp = _I_['rf_amp']
            rf_dur = self.queue.tt.rp(name = _I_['transition'], amp=rf_amp).pi
            
            # Here init cnot
            #cnot(amp, pi_dur, freqs)
            #rf_pulse(rf_amp, rf_dur_swap, rf_freq_swap)

            ### READOUT ###
            ampL = self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['mw_omega']).amp
            ampR = self.queue.tt.rp('e_rabi_ou950deg-90-R', omega=_I_['mw_omega']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou950deg-90-L', omega=_I_['mw_omega']).pi)

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
            print(amps, amps_m)
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[freqs],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='13c5000_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read1']),
                    length_mus_mw=pi_durL,
                    amplitudes=amps,
                    repetitions=int(_I_['n_ssr1'])
                    )


            electron_init(st = _I_['transition'].split(" ")[1], t = _I_['t_reset'])
            rf_freq_rabi = self.queue.tt.t(_I_['transition']).current_frequency
            mcas.start_new_segment('nuclear rabi', loop_count=1)
            rf_pulse(_I_['rf_amp'], _I_['tau_rabi'], rf_freq_rabi+_I_['rf_freq'])
            
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[freqs_m, freqs], 
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='13c5000_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read2']),
                    length_mus_mw=pi_durL,
                    amplitudes=[amps_m, amps],
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
        ['init', '<', 1, 0, 0, 1],
        ['result', '>', 0, 2, 0, 2], # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>',7, 1, 0, 1],
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

    nuclear.x_axis_title = 'Time [µs]'
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
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 60
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval= 6000

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(20)),
            ('A2_power',[10]),
            ('mw_omega',[0.5]),
            ('t_read1', [1.024*7]),
            ('t_read2', [1.024*7]),
            ('wait_dur', [0.512]),
            ('rf_amp', [0.4]),
            ('rf_amp2', [0.4]),
            ('init_time', [50]),
            ('transition', ['29si8 ms+0.5']),
            ('t_reset',[50]),
            ('n_ssr2', [300]),
            ('n_ssr1', [300]),
            ('rf_freq', np.arange(-0.04,0.04,0.005)),
            #('rf_freq', [0.0]),
            ('state_init', ['-nn','+nn']),
            ('tau_rabi',[37]),
            #('tau_rabi',np.linspace(0, 170, 20)),
            
        )
    )
    nuclear.number_of_simultaneous_measurements = 1

####################################################################################################
# predefined transition lists
####################################################################################################
# transition_list = ['29Si8 ms0.5', '29Si2.2a ms0.5','29Si2.2b ms0.5',
#                    '29Si8 ms1.5', '29Si2.2a ms1.5','29Si2.2b ms1.5',
#                    '29Si8 ms-0.5', '29Si2.2a ms-0.5','29Si2.2b ms-0.5',
#                    '29Si8 ms-1.5', '29Si2.2a ms-1.5','29Si2.2b ms-1.5']
                   


def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10*1e6
    #nuclear.pld.fit_function = 'lorentz'
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)