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
            
            ## TODO replace with sna.nuclear_rabi
            def rf_pulse(amp, dur, freq, phase = 0):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1')
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    pd2g2 = {"type":"sine", "frequencies":[freq],"amplitudes":[amp],'phases': [phase], "phase_type_offset": 'absolute'}
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

            sna.repump(mcas,50)


            ### READOUT ###
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

            used_freqs=[freqs_m,freqs][_I_["parity"]]
            used_amps=[amps_m,amps][_I_["parity"]]

            print(f"freqs_all_L={freqs_all_L}",f"freqs_all_R={freqs_all_R}",f"freqs_init_L={freqs_init_L}",f"freqs_init_R={freqs_init_R}",
                  f"freqs_all_but_init_L={freqs_all_but_init_L}",f"freqs_all_but_init_R={freqs_all_but_init_R}",sep="\n")


            # init nuclear spin
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[used_freqs], #[[*freqs_m,*freqs]],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='13c5000_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read1']),
                    length_mus_mw=pi_durL,
                    amplitudes=used_amps,#[*amps_m,*amps],
                    repetitions=int(_I_['n_ssr1'])
                    )
            
            # init electron spin
            #mcas, state, dur, freqs_all_L, freqs_all_R, segment_length = 10
            sna.electron_init(mcas, _I_["transition"], _I_["init_time"], freqs_all_L, freqs_all_R)

            dur= E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp(_I_["transition"], omega = _I_['omega_rf']).pi)
            amp= self.queue.tt.rp(_I_["transition"], omega = _I_['omega_rf']).amp
            freq=self.queue.tt.t(_I_["transition"]).current_frequency

            mcas.start_new_segment(name='Ramsey', loop_count = 1)

            print(amp,dur/2,freq)

            if False:
                rf_pulse(amp,dur/2,freq) #nuc on xy plane
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_["tau_echo"]), name='tau_echo')
                rf_pulse(amp,dur,freq)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(_I_["tau_echo"]), name='tau_echo')
                rf_pulse(amp,dur*3/2,freq) #nuc completly flipped now
            ### PI /2 ###
            rf_pulse(amp,dur=dur/2,freq=freq)

            ### TAU ###
            segment_length = E.round_length_mus_to_x_multiple_ps(1000, 64)
            lc, correction_mus = shared.calculate_loop_count(_I_['tau_echo'], segment_length)
            if lc>0:
                mcas.start_new_segment(name='tau_ramsey', loop_count=int(lc))
                mcas.asc(length_mus=segment_length, name='tau_echo')
            mcas.start_new_segment(name='tau_ramsey', loop_count=1)
            mcas.asc(length_mus=correction_mus, name='tau_echo')

            ### PI ###
            rf_pulse(amp,dur=dur,freq=freq)

            ### TAU ###
            if lc>0:
                mcas.start_new_segment(name='tau_ramsey', loop_count=int(lc))
                mcas.asc(length_mus=segment_length, name='tau_echo')
            mcas.start_new_segment(name='tau_ramsey', loop_count=1)
            mcas.asc(length_mus=correction_mus, name='tau_echo')

            ### PI / 2 ###
            rf_pulse(amp,dur=dur/2,freq=freq, phase=_I_['readout_phase'])



            if _I_['readout']=='ssr':
                # sna.ssr(mcas = mcas, queue=self.queue,
                #         frequencies=[[trans['L1'], trans['R1']]],
                #         wait_dur=0.0,
                #         robust=False,
                #         nuc='29Si8_A2',
                #         mixer_deg=-90,
                #         eom_ampl=0.0,
                #         step_idx=0,
                #         laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
                #         length_mus_mw = pi_durL,
                #         amplitudes=[ampL,ampR],
                #         repetitions = int(_I_['n_ssr1']) 
                #         )
                #rf_freq = {'m32': 12.0-0.056, 'm12': 3.2+0.021, 'p12': 5.5-0.026+0.04, 'p32': 14.3+0.012-0.04}[_I_['state']]
                #rf_dur = {'m32': 19.586, 'm12': 63.055, 'p12': 36.4/4, 'p32': 17.986}[_I_['state']]
                
                # electron_init(st='p12', t = _I_['t_reset'])

                # mcas.start_new_segment('n rabi', loop_count=1)
                # if _I_['single']:
                #     rf_pulse(rf_freq + _I_['rf_freq'], dur=rf_dur)
                #     mcas.asc(length_mus=_I_['tau_ramsey'], name='tau_ramsey')
                #     # segment_length = E.round_length_mus_to_x_multiple_ps(1000, 64)
                #     # lc, correction_mus = shared.calculate_loop_count(_I_['tau_ramsey'], segment_length)
                #     # if lc > 0:
                #     #     mcas.start_new_segment(name='tau_ramsey', loop_count=int(lc))
                #     #     mcas.asc(length_mus=segment_length, name='tau_ramsey')
                #     #     mcas.start_new_segment(name='tau_ramsey', loop_count=1)
                #     #     mcas.asc(length_mus=correction_mus, name='tau_ramsey')
                #     # else:
                #     #     mcas.start_new_segment(name='tau_ramsey', loop_count=1)
                #     #     mcas.asc(length_mus=correction_mus, name='tau_ramsey')

                #     rf_pulse(rf_freq + _I_['rf_freq'], dur = rf_dur, phase=_I_['readout_phase'])
                # else:
                #     rf_pulse2(freq1=3.224, freq2=5.512, dur=_I_['tau_rabi'])
                # #mcas.asc(length_mus=3.0)

                
                sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[used_freqs], #[[*freqs_m,*freqs]],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='13c5000_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read2']),
                    length_mus_mw=pi_durL,
                    amplitudes=used_amps,#[*amps_m,*amps],
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
        ['init', '<', 3, 0, 0, 1],
        ['result', '>', 2, 0, 0, 1], # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 5, 0, 0, 1],
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
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 300
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval= 6000

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    lst  =  np.logspace(1, 6, 10).tolist()
    #lst1 = lst[0::2]
    #lst2 = lst[1::2][::-1]
    #ordered_list = []
    #while len(lst2)>0:
    #    ordered_list.append(lst1.pop())
    #    ordered_list.append(lst2.pop())
    ordered_list=lst
    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(20)),
            ('A2_power', [5]),
            ('omega', [0.5]),
            ('omega_rf', [0.01]),
            ('wait_dur', [0.512]),
            ('readout', ['A2']),
            ('transition', ['29si8 ms-1.5']),#'29si8 ms+1.5','29si8 ms-1.5','29si8 ms+0.5',
            #('transition', ['29si8 ms+1.5','29si8 ms-1.5','29si8 ms+0.5','29si8 ms-0.5']),#'29si8 ms+1.5','29si8 ms-1.5','29si8 ms+0.5',
            ('init_time', [60]),
            ('n_ssr1', [250]),
            ('t_read1', [4*1.024]),
            ('n_ssr2', [250]),
            ('t_read2', [4*1.024]),
            ('state_init', ['+nn',"-nn"]),
            ('t_reset', [50]),
            ('single', [True]),
            ('tau_echo', ordered_list),
            #('tau_rabi',[38.512]),
            ('readout', ['ssr']),
            ('parity', [0, 1]),
            ('readout_phase', [0, 180])
        )
    )
    nuclear.number_of_simultaneous_measurements = 2 # 4

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 30*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)