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

        tt = self.queue.tt
        tesla = (tt.mw_mixing_frequency_L+tt.mw_mixing_frequency_R)/(2*28031.6)
        c_bath = tt.c_bath
        si_bath = tt.si_bath  
    
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]
        
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ###
            trans_idx = _I_['init_nuc_state']
            if '-' in _I_['init_state']:
                transition = 'L'+trans_idx
                
            elif '+' in _I_['init_state']:
                transition = 'R'+trans_idx
             
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(_I_['init_state'],si_bath)
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition)

            freq = [trans[transition]]       
            
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
                    mixer_deg=[-90],
                    pulseshape='sinehermite',
                )

            def rf_pulse(freq, amp=None, dur=None, phase=0):
                amp = si1_amp if amp is None else amp
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1', gateRF = True)
                if dur is None:
                    dur = si1_pi
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    gateRF = True,
                    pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
                           "phase_type_offset": 'absolute'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)

            sna.repump(mcas, 30)
            sna.electron_init(mcas, _I_['init_state'].replace("1/2","0.5").replace("3/2","1.5"), _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .05)
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(si1_freq)

            ### READOUT ###
            if trans_idx == '1':
                ssr_freqs=[trans['L2'], trans['R2']]
                read_idx = '2'
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                read_idx = '1'
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(read_idx,weak=True)

            factor = 1
            pi_dur_read = pi_dur_read * factor
            R_amp_read = R_amp_read / factor
            L_amp_read = L_amp_read / factor
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read'],8),
                    length_mus_mw=pi_dur_read,
                    amplitudes=[L_amp_read, R_amp_read],
                    repetitions=int(_I_['n_ssr1'])
                    )
            sna.electron_init(mcas, _I_['init_state'].replace("1/2","0.5").replace("3/2","1.5"), _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = _I_['init_amp'])
            
            A1_val = _I_['laser'] == 'A1'
            A2_val = _I_['laser'] == 'A2'
            gate_MW=bool(_I_["Gate_MW_open"])
            gate_RF=bool(_I_["Gate_RF_open"])
            
            
            laser = False
            if A1_val or A2_val:
                laser = True



            # # only use shutter when doing measurements longer than 200ms.
            if _I_['tau'] > 200e3:
                tau_closed = _I_['tau']-100e3
                tau_opened = 100e3

                segment_length = E.round_length_mus_to_x_multiple_ps(1000, 64)
                lc, correction_mus = shared.calculate_loop_count(tau_closed, segment_length)

                # Sequence with closed shutter            
                mcas.start_new_segment(name='tau', loop_count=int(lc))
                mcas.asc(length_mus=segment_length, name='tau', A1 = A1_val, A2= A2_val, laser = laser, shutter = True,gateMW=gate_MW,gateRF=gate_RF)
                if correction_mus>0:
                    mcas.start_new_segment(name='tau', loop_count=1)
                    mcas.asc(length_mus=correction_mus, name='tau', A1 = A1_val, A2= A2_val, laser = laser, shutter = True,gateMW=gate_MW,gateRF=gate_RF)
        
                # Open 100ms prior to readout
                lc, correction_mus = shared.calculate_loop_count(tau_opened, segment_length)

                mcas.start_new_segment(name='tau', loop_count=int(lc))
                mcas.asc(length_mus=segment_length, name='tau', A1 = A1_val, A2= A2_val, laser = laser,gateMW=gate_MW,gateRF=gate_RF)
                if correction_mus>0:
                    mcas.start_new_segment(name='tau', loop_count=1)
                    mcas.asc(length_mus=correction_mus, name='tau', A1 = A1_val, A2= A2_val, laser = laser,gateMW=gate_MW,gateRF=gate_RF)
    
            else: 
                segment_length = E.round_length_mus_to_x_multiple_ps(1000, 64)
                lc, correction_mus = shared.calculate_loop_count(_I_['tau'], segment_length)

                if lc > 0:            
                    mcas.start_new_segment(name='tau', loop_count=int(lc))
                    mcas.asc(length_mus=segment_length, name='tau', A1 = A1_val, A2= A2_val, laser = laser,gateMW=gate_MW,gateRF=gate_RF)
                    if correction_mus>0:
                        mcas.start_new_segment(name='tau', loop_count=1)
                        mcas.asc(length_mus=correction_mus, name='tau', A1 = A1_val, A2= A2_val, laser = laser,gateMW=gate_MW,gateRF=gate_RF)

                else:
                    mcas.start_new_segment(name='tau', loop_count=1)
                    mcas.asc(length_mus=_I_['tau'], name='tau', A1 = A1_val, A2= A2_val, laser = laser,gateMW=gate_MW,gateRF=gate_RF)
            
            # pi pulse on nuclear for readout
            for state in _I_["flip_state"].split(" "):
                si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(state,si_bath)
                rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)
                        

            sna.ssr(mcas = mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']),
                    length_mus_mw=pi_dur_read,
                    amplitudes=[L_amp_read, R_amp_read],
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
            
            # wait to let system cooldown again and make sure shutter is open long enough
            
            lc, correction_mus = shared.calculate_loop_count(50e3, segment_length)  
            if lc > 0:
               mcas.start_new_segment(name='tau', loop_count=int(lc))
               mcas.asc(length_mus=segment_length, name='tau')
               if correction_mus>0:
                    mcas.start_new_segment(name='tau', loop_count=1)
                    mcas.asc(length_mus=correction_mus, name='tau')
            else:
               mcas.start_new_segment(name='tau', loop_count=1)
               mcas.asc(length_mus=_I_['tau'], name='tau')
            
        
        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['init', '<', 12, 0, 0, 1], #SSR1
        ['result', '>', 12, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 10, 1, 0, 1],   #CRC
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
    nuclear.do_ple_refocusA2 = False

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    #confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = True
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.do_repump = False
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 100
    nuclear.confocal_refocus_interval = 1200  # seconds
    nuclear.odmr_refocus_interval= 6000

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(20)),
            ('A2_power', [5]),
            ('t_read', [1.024*3]),
            ('n_ssr2', [2000]),
            ('n_ssr1', [2000]),
            ('init_nuc_state',['1',"2"]),
            ('laser', ["A1"]),
            #('tau', E.round_length_mus_to_x_multiple_ps([300000])),
            ('init_time', [200]),
            ('init_amp', [0.1]),
            ('init_state',['-3/2']),
            ('flip_state', ['-3/2',"-3/2 -1/2"]),#,"m32",'m32 p32','m32 p32 m12']), #states in which we make a nuc spin flip before readout
            ('Gate_MW_open',[0]),
            ('Gate_RF_open',[0]),
            ('tau', E.round_length_mus_to_x_multiple_ps(np.logspace(2, 7,25).tolist())),
            ('readout_proj', [0])
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