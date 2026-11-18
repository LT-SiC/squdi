# coding=utf-8
import datetime
import numpy as np
import os
import importlib
import notebooks.UserScripts.helpers.sequence_creation_helpers as sch;

importlib.reload(sch)
import notebooks.UserScripts.helpers.shared as shared
from hardware.Keysight_AWG_M8190.pym8190a import MultiChSeq as MultiChSeq
import notebooks.UserScripts.helpers.snippets_awg as sna

importlib.reload(sna)
importlib.reload(shared)
# importlib.reload(MultiChSeq)
import notebooks.UserScripts.helpers.shared as ush;

importlib.reload(ush)
from logic.qudip_enhanced import *
import hardware.Keysight_AWG_M8190.elements as E
from collections import OrderedDict

seq_name = os.path.basename(__file__).split('.')[0]
nuclear = sch.create_nuclear(__file__)
with open(os.path.abspath(__file__).split('.')[0] + ".py", 'r') as f:
    meas_code = f.read()

__TAU_HALF__ = 2 * 192 / 12e3
__SAMPLE_FREQUENCY__ = 12e3  # e.__SAMPLE_FREQUENCY__


def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name=None):
        tt = self.queue.tt
        tesla = (tt.mw_mixing_frequency_L+tt.mw_mixing_frequency_R)/(2*28031.6)
        c_bath = tt.c_bath
        si_bath = tt.si_bath
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]

        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ###
            trans_idx = _I_['init_nuc_state']
            if '-' in _I_['state']:
                transition = 'L'+trans_idx
                
            elif '+' in _I_['state']:
                transition = 'R'+trans_idx
                
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(_I_['state'],si_bath)
            #amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition)

            #dur = self.queue.tt.RP('e_rabi_ou350deg-90-'+transition, amp=_I_['amp']).pi
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition,pulseshape=_I_["pulseshape"],fast=_I_["driving"]=="fast",middle=_I_["driving"]=="middle")
            print(transition,pi_dur,pi2_dur)

            pi_dur=pi_dur+_I_["added_dur"]
            
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
                    pulseshape= 'sinehermite'
                )

            def rf_pulse(freq, amp=None, dur=None, phase=0):
                amp = si1_amp if amp is None else amp
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1', gateRF = True)
                if dur is None:
                    dur = si1_pi
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur,1),
                    name='nuc',
                    gateRF = True,
                    pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
                           "phase_offset_type": 'coherent'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)
           

            def erabi(freq, length, amp, phase=0.0):
                sna.electron_rabi(mcas,
                                  name='electron rabi',
                                  length_mus=length,
                                  amplitudes=amp,
                                  frequencies=freq,
                                  phases=np.rad2deg(phase),
                                  new_segment=False,
                                  gateMW=True,
                                  mixer_deg=-90,
                                  pulseshape= _I_['pulseshape']
                                  )
                
            def waveform(seq):
                mcas.start_new_segment('waveform')
                #sna.polarize(mcas, new_segment=False)
                mw = seq.times_fields_aphi('mw')
                wait = seq.times_fields_aphi('wait')
                for k, step in enumerate(seq.sequence_steps):
                    idx = int(step[1]) - 1

                    if step[0] == 'mw':
                        if k == 0 or k == len(seq.sequence_steps)-1:
                            erabi(freq=f,
                                length=E.round_length_mus_to_x_multiple_ps(pi2_dur,1),#pi2_dur*2,
                                amp=amp_dd,
                                #amp=self.queue.tt.rp('e_rabi_ou350deg-90-R'+trans_idx, period=1 / mw[idx, 1]).amp, # TODO is trans_idx correct here?
                                phase=mw[idx, 2])
                        else:
                            erabi(freq=f,
                                length=E.round_length_mus_to_x_multiple_ps(pi_dur,1),#pi_dur*2,
                                amp=amp_dd,
                                #amp=self.queue.tt.rp('e_rabi_ou350deg-90-R'+trans_idx, period=1 / mw[idx, 1]).amp, # TODO is trans_idx correct here?
                                phase=mw[idx, 2])
                            
                    elif step[0] == 'wait':
                        first={"normal":0,"start-mid":pi_dur,"mid-mid":3/4*pi_dur,"start-start":pi_dur/2,"start/end-mid":pi_dur,"custom":_I_["added_tau"]}
                        last={"normal":0,"start-mid":pi_dur/2,"mid-mid":3/4*pi_dur,"start-start":pi_dur,"start/end-mid":pi_dur,"custom":_I_["added_tau"]}
                        added=0
                        #print( len(wait),idx,step)
                        if idx==0:
                            added=first[_I_["ref"]] #CHECK!
                            print("first at index", idx)
                        elif idx+1==len(wait):
                            added=last[_I_["ref"]] #CHECK!
                            print("last at index", idx)

                        #print(added,_I_["ref"])

                        if wait[idx, 0] > 0.256:
                            mcas.asc(length_mus=wait[idx, 0]-0.256-0.256-added)#,pd2g1={"type": "sinehermite", "frequencies": [5200], "amplitudes": [1], "phases": [0], "phase_offset_type": 'coherent'})
                            mcas.asc(length_mus=0.256, gateMW = bool(_I_["gate_mw"]))#,pd2g1={"type": "sinehermite", "frequencies": [5200], "amplitudes": [1], "phases": [0],"phase_offset_type": 'coherent'})
                        else:
                            mcas.asc(length_mus=wait[idx, 0]-0.256-added, gateMW = bool(_I_["gate_mw"]),gateRF=_I_["gateRF"])#,pd2g1={"type": "sinehermite", "frequencies": [5200], "amplitudes": [1], "phases": [0], "phase_offset_type": 'coherent'})
                        mcas.asc(length_mus=0.256, gateMW = True)

            driving=_I_["driving"]
            if driving=="both":
                freq1 = [trans[transition.replace("2","1")]]
                freq2 = [trans[transition.replace("1","2")]]

                amp1, pi_dur1, pi2_dur1 = sna.get_hardcoded_e_values_for_control(trans[transition.replace("2","1")],pulseshape=_I_["pulseshape"])
                amp2, pi_dur2, pi2_dur2 = sna.get_hardcoded_e_values_for_control(trans[transition.replace("1","2")],pulseshape=_I_["pulseshape"])

                pi_dur1, pi2_dur1=  (pi_dur1 + pi_dur2)/2, (pi2_dur2 + pi2_dur1)/2

                f=freq1+freq2
                amp_dd=[amp1,amp2]

            elif driving=="middle":

                f=[(trans[transition.replace("1","2")]+trans[transition.replace("2","1")])/2]
                amp_dd=[amp]
            
            else:
                f=[trans[transition]]
                amp_dd=[amp]

            #amp=1.
            #pi_dur=0.043 #0.071
            #pi2_dur=0.021 #0.035

            #if pi_dur > _I_['tau']:
            #    print("Tau shorter than pi dur. Choose longer tau!")

            def dd(add_phase_2=0):
                rabi_period = pi_dur * 2
                pi2x = sc.Rabi(t_rabi=pi_dur, omega=1 / rabi_period, phase=0.0, control_field='mw')
                pi2_2 = sc.Rabi(t_rabi=pi2_dur, omega=1 / rabi_period, phase=_I_["phase_pi2_2"],# add_phase_2,
                                control_field='mw')
                dd = sc.DD(dd_type='{}_{}'.format(_I_['n_rep_dd'], _I_['ddt']), rabi_period=rabi_period,
                          tau=_I_['tau'])
                seq = sc.Concatenated([pi2x, dd, pi2_2], controls=['mw', 'wait'])
                waveform(seq)

        # Repump
            sna.repump(mcas, dur = 10)
        # Init nuclear via CNOT
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(trans_idx,weak=True)
            cnot([R_amp_read, L_amp_read]["L" in transition], pi_dur_read, trans[transition])
            rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)
        # Confirm initialized nuclear spin via SSR
            if trans_idx == '1':
                ssr_freqs=[trans['L2'], trans['R2']]
                read_idx = '2'
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                read_idx = '1'
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(read_idx,weak=True)
            
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

        # Initialize electron
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .15)
            
        # DD
            mcas.start_new_segment('DD', loop_count=1)
            mcas.asc(length_mus=0.256, gateMW=True)

            include_dd=_I_["include_dd"]

            if include_dd:
                dd()
                #dd(np.pi/2)
                #mcas.asc(length_mus=_I_["tau_scan"],name="tau_scan")
                #dd(3*np.pi/2)
            else:
                mcas.asc(length_mus=(8*pi_dur+8*_I_["tau"])*_I_["n_rep_dd"], gateMW = bool(_I_["gate_mw"]))

            
        # Copy electron state to nuclear
            if _I_['include_CeNOTn']:
                rf_pulse(si1_freq)

        # Readout of nuclear spin via SSR
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read'],8),
                    length_mus_mw=pi_dur_read,
                    amplitudes=[L_amp_read, R_amp_read],
                    repetitions=int(_I_['n_ssr2'])
                    )
            
            #CRC.
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[500],
                    wait_dur=0.0,
                    robust=False,
                    nuc='charge_state',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=2,
                    )

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements, n_vals = 1000)
        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
        ['init', '<', 12, 0, 0, 1],
        ['result', '>', 12, 0, 0, 1], # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 6, 1, 0, 1],
        # ['init', '>', 5, 1, 0, 1],
    ]
    # what does each entry do?
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
    # nuclear.analyze_type = 'consecutive'
    nuclear.analyze_type = 'average'  # experimental feature for the fast
    nuclear.save_smartly = False
    # PLE refocus
    nuclear.do_ple_refocusA1 = False  # not used
    nuclear.do_ple_refocusA2 = True

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    # confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus = True
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.do_repump = False
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 600
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval = 6000

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    tt  = nuclear.queue._transition_tracker
    tesla = (tt.mw_mixing_frequency_L+nuclear.queue._transition_tracker.mw_mixing_frequency_R)/(2*28031.6)
    si_bath = tesla * (-8.465)

    bath_period = np.abs(np.round(1/si_bath,3))
    
    def find_closest_tau_to_bath(tau):
        t_ = []
        for t in tau:
            n = 1
            while bath_period * n < t:
                n+=1
            if np.abs(bath_period*(n-1) - t) < np.abs(bath_period*(n) - t):
                n-=1
            matched_tau = bath_period * n
            t_.append(matched_tau)
        return t_

    taus = np.logspace(2.3,4,50)
    #taus = find_closest_tau_to_bath(taus)
    

    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('state', ['-3/2']),
            ('A2_power', [20]),
            ('Bfield', [tesla]),
            ('t_read', [1.024 * 3]),
            ('init_time', [300]),
            ('n_ssr2', [3000]),
            ('n_ssr1', [3000]),
            ("driving",["fast"]), #normal=use one freq with pi pulses tat mostly do not affect the other nuc spin transition, fast= to use for max amp on one transtion. middle= drive with max amp between the two nuc transitions. both = drive both 1 and 2 transitions at the same time with pulses that ry not to interfere with the other nuc transition
            ('init_nuc_state', ['1']),
            ("include_dd", [1]),
            ("gate_mw", [0]),
            ('n_rep_dd', [2]),
            #('tau', [42.3]),
            ('ddt', ["xy4","knillpi"]),#"hahn","xy4","kdd4"
            ('tau',  E.round_length_mus_to_x_multiple_ps([*np.arange(30,80,0.12)],1)),#E.round_length_mus_to_x_multiple_ps([*np.arange(1, 2., 0.002)],1)), E.round_length_mus_to_x_multiple_ps([*np.arange(0, 6., 0.05)],1)
            #('tau_scan',  E.round_length_mus_to_x_multiple_ps([*np.arange(5,500,0.1)],1)),#E.round_length_mus_to_x_multiple_ps([*np.arange(1, 2., 0.002)],1)), E.round_length_mus_to_x_multiple_ps([*np.arange(0, 6., 0.05)],1)
            #('tau',  E.round_length_mus_to_x_multiple_ps([3,7.773588594375156,23.190986064844182,39.05269465256891,54.1294319522422,70.14889234151583,17.54476842889407,51.632370952170774],1)),#E.round_length_mus_to_x_multiple_ps([*np.arange(1, 2., 0.002)],1)), E.round_length_mus_to_x_multiple_ps([*np.arange(0, 6., 0.05)],1)
            ('include_CeNOTn', [1]),
            ("ref", ["normal"]),
            #("ref", ["normal","start-mid","mid-mid","start-start","start/end-mid"]),
            #('tau',  [E.round_length_mus_to_x_multiple_ps(1,1)]),#E.round_length_mus_to_x_multiple_ps([*np.arange(1, 2., 0.002)],1)),
            #("added_dd_pi_dur",[*np.linspace(-0.05,0.05,40)]),
            ("added_dur", [0.]),#*np.arange(-0.006,0.006,0.002)
            #("added_tau", E.round_length_mus_to_x_multiple_ps([*np.linspace(-0.08,0.08,100)])),
            ("added_tau", E.round_length_mus_to_x_multiple_ps([0])),
            ("gateRF", [0,1]),

            #("added_dur", [*np.arange(-0.004,0.004,0.001)]),
            ('pulseshape', ['sinehermite']),
            ('phase_pi2_2', [0.,np.pi]),
            #('phase_pi2_2', [0]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 1


def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 5 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)