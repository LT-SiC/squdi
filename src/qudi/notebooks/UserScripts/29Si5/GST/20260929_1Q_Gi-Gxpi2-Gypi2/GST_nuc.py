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

import re

seq_name = os.path.basename(__file__).split('.')[0]
nuclear = sch.create_nuclear(__file__)
with open(os.path.abspath(__file__).split('.')[0] + ".py", 'r') as f:
    meas_code = f.read()

__TAU_HALF__ = 2 * 192 / 12e3
__SAMPLE_FREQUENCY__ = 12e3  # e.__SAMPLE_FREQUENCY__

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name=None):
        tt = self.queue.tt
                
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
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(_I_['state'], _I_['bath_freq_Si'])
            amp, gate_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition,fast=True)
            
            # Use this for now. Should be replaced by fixed gate times with variable amps
            amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition,fast=True)
            freq = trans[transition]

            # not used in this version of the script as only nuclear is investigated
            q0_dict = {'amp': amp,
                       'gate_dur': gate_dur,
                       'pi2_dur': pi2_dur,
                       'freq': freq
                    }
            # placeholder for proper nuclear calibration file
            amps=[{"pi/2":0.223,"pi":0.450,"3pi/2":0.674},
                   {"pi/2":0.234,"pi":0.471,"3pi/2":0.744}]["C" in _I_["spin"]] 
                        
            q1_dict = {'pi2_amp': amps["pi/2"],
                       'pi_amp': amps["pi"],
                       'gate_dur': 600, # for silicon
                    }
            
            # combine with q1_dict:
            spin_data=tt.register.get_spin(_I_['spin'], _I_['state'].replace('+',''), _I_['ddrft'],Tau_finder=_I_["Tau_finder_tau_from_file"],comment=_I_["comment"])

            coupling = spin_data.detuning.iloc[_I_["file_index"]]
            ddrf_tau = spin_data.ddrf_tau.iloc[_I_["file_index"]]/2
            ddrf_amp = spin_data.ddrf_amp.iloc[_I_["file_index"]]
            #ddrf_amp = _I_['ddrf_amp']
            ddrf_phase_inc = spin_data.ddrf_phase_inc.iloc[_I_["file_index"]]
            n_rep_ddrf = int(spin_data.n_rep_ddrf.iloc[_I_["file_index"]])
            ddrf_phase_init =spin_data.ddrf_phase_init.iloc[_I_["file_index"]]
            ddrf_phase_read = spin_data.ddrf_phase_read.iloc[_I_["file_index"]]
            pi2_2_MW_phase = spin_data.pi2_2_MW_phase.iloc[_I_["file_index"]]
            reps_phase_inc = spin_data.reps_phase_inc.iloc[_I_["file_index"]]

            bath_freq = [_I_['bath_freq_Si'], _I_['bath_freq_C']]['C' in _I_['spin']]

            def GST_to_NucOPs(circuit, mcas, q0_dict, q1_dict):
                ### TO BE MOVED TO HELPERS!!! ###
                """
                Parses a pyGSTi circuit string (as found in dataset.txt) into an ordered
                sequence of experiment function calls: null(), idle(), pi2x(), pi2y(), ...

                Handles:
                {}          -> empty circuit (zero layers, zero time)   -> null()
                []          -> empty layer (one idle time step)         -> idle()
                Gxpi2:0     -> named single-qubit gate                  -> pi2x()  (etc.)
                (...)^N     -> germ power / repetition notation          -> expanded inline
                @(0)        -> trailing line-label annotation            -> stripped, not called
                                                                            (for now, needs to be
                                                                            extendend when adding
                                                                            a nuc spin)

                NOTE: does not yet handle multi-gate simultaneous layers like
                [Gxpi2:0Gypi2:1] (two gates on different qubits in the same time step).
                See the note at the bottom for how to extend this if your gate set needs it.

                circuit     -> a single circuit from the GST_file
                mcas        -> multichannel arbirary sequence: Sequence which can be passed to
                            the AWG. Should already contain the initialization of all qubits
                            to |0>. 
                q0_dict     -> contains calibration values for the qubit 0, e.g. amp, freq,...
                """
                
                # Matches a gate label: 'G' + lowercase/digit name + optional ':digit' qubit tags.
                # Restricting the name to [a-z0-9] (no uppercase) is what prevents this from
                # swallowing the next gate label, since every label starts with an uppercase 'G'.
                _GATE_RE = re.compile(r'G[a-z0-9]+(?::\d+)*')
                _POWER_RE = re.compile(r'\^(\d+)')
                def tokenize(circuit_str):
                    """Flatten a pyGSTi circuit string into an ordered list of tokens:
                    '{}' for the empty circuit, '[]' for an idle layer, or a gate label
                    string like 'Gxpi2:0'. Expands any (...)^N repetition groups."""

                    def parse_sequence(s, i):
                        seq = []
                        while i < len(s):
                            ch = s[i]
                            if ch == ')':
                                return seq, i
                            elif ch == '(':
                                inner, i = parse_sequence(s, i + 1)
                                i += 1  # skip the ')'
                                m = _POWER_RE.match(s, i)
                                power = int(m.group(1)) if m else 1
                                if m:
                                    i = m.end()
                                seq.extend(inner * power)
                            elif s[i:i + 2] == '{}':
                                seq.append('{}')
                                i += 2
                            elif s[i:i + 2] == '[]':
                                seq.append('[]')
                                i += 2
                            elif ch == '@':
                                break  # trailing line-label annotation -- stop parsing
                            else:
                                m = _GATE_RE.match(s, i)
                                if m:
                                    seq.append(m.group(0))
                                    i = m.end()
                                else:
                                    i += 1  # skip anything unexpected rather than crashing
                        return seq, i

                    tokens, _ = parse_sequence(circuit_str, 0)
                    return tokens

                def token_to_func_name(token):
                    """Map a circuit token to a key of `funcs`.
                    Qubit 0 (electron)  : 'Gxpi2'      / 'Gxpi2:0'  -> 'Gxpi2'
                    Qubit 1 (nuclear)   : 'Gxpi2:1'                 -> 'Gxpi2_nuc'
                    NOTE: gates of one layer, e.g. [Gxpi2:0Gypi2:1], are currently executed
                    one after the other, NOT simultaneously. Extend when 2-qubit GST starts.
                    """
                    if token == '{}':
                        return 'null'
                    parts = token.split(':')
                    gate_name = parts[0]
                    qubit = int(parts[1]) if len(parts) > 1 else 0
                    if qubit == 0:
                        return gate_name
                    if qubit == 1:
                        return gate_name + '_nuc'
                    raise NotImplementedError("No gate implementation for qubit %d (token %s)" % (qubit, token))

                def run_circuit(circuit, funcs):
                    """`line` is a raw dataset.txt line: '<circuit string>  <count1> <count2> ...'.
                    `funcs` is a dict mapping function names ('null', 'idle', 'Gxpi2', 'Gypi2', ...)
                    to the actual callables to invoke."""
                    tokens = tokenize(circuit)
                    call_sequence = [token_to_func_name(t) for t in tokens]
                    for name in call_sequence:
                        funcs[name]()
                    return call_sequence  # handy for logging/debugging

                def null(): # print("null")
                    return
                def idle(): # print("idle")
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(q0_dict['gate_dur']), gateMW=True)
                def Gxpi2(): # print("pi2x")
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(q0_dict['gate_dur'],1),
                            name='pi2x',
                            gateMW=True,
                            pd2g1={"type": "sinehermite",
                                    "frequencies": [q0_dict['freq']],
                                    "amplitudes": [q0_dict['amp']/2],
                                    "phases": [0],
                                    "phase_offset_type": 'coherent'})
                def Gypi2(): # print("pi2y")
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(q0_dict['gate_dur'],1),
                            name='pi2y',
                            gateMW=True,
                            pd2g1={"type": "sinehermite",
                                    "frequencies": [q0_dict['freq']],
                                    "amplitudes": [q0_dict['amp']/2],
                                    "phases": [90],
                                    "phase_offset_type": 'coherent'})
                def Gxpi(): # print("pix")
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(q0_dict['gate_dur'],1),
                            name='pix',
                            gateMW=True,
                            pd2g1={"type": "sinehermite",
                                    "frequencies": [q0_dict['freq']],
                                    "amplitudes": [q0_dict['amp']],
                                    "phases": [0],
                                    "phase_offset_type": 'coherent'})
                def Gypi(): # print("piy")
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(q0_dict['gate_dur'],1),
                            name='piy',
                            gateMW=True,
                            pd2g1={"type": "sinehermite",
                                    "frequencies": [q0_dict['freq']],
                                    "amplitudes": [q0_dict['amp']],
                                    "phases": [90],
                                    "phase_offset_type": 'coherent'})

                # ------------------------------------------------------------------
                # Second qubit (nuclear spin) -- TO BE FILLED MANUALLY for 2-qubit GST
                # ------------------------------------------------------------------
                

                accumulated_phase = 0
                def Gi_nuc():
                    sna.ddrf(mcas,
                        0, # global_mw_phase #phase around X
                        np.pi/2, # second_mw_phase #phase around Y
                        ddrf_phase_inc, # rf_phase_increment
                        accumulated_phase, # rotation_axis
                        pi_dur, # pi electron
                        pi2_dur, # pi/2 electron
                        coupling,  # detuning
                        _I_['bath_freq_Si'] if 'Si' in _I_['spin'] else _I_['bath_freq_C'],  # bath freq
                        ddrf_tau,  # tau
                        n_rep_ddrf,  # n_rep_ddrf
                        _I_['ddrft'],  # ddrft
                        trans[transition],  # mw freq
                        amp,  # mw amp
                        0,  # rf amp # FIXME keep RF gate closed
                        pi2_1 = False, # initial pi/2 pulse
                        pi2_2 = False, # final pi/2 pulse
                        constant_phase_offset=True,
                        )
                def Gxpi2_nuc():
                    nonlocal accumulated_phase
                    sna.ddrf(mcas,
                        0, # global_mw_phase #phase around X
                        np.pi/2, # second_mw_phase #phase around Y
                        ddrf_phase_inc, # rf_phase_increment
                        accumulated_phase, # rotation_axis
                        pi_dur, # pi electron
                        pi2_dur, # pi/2 electron
                        coupling,  # detuning
                        _I_['bath_freq_Si'] if 'Si' in _I_['spin'] else _I_['bath_freq_C'],  # bath freq
                        ddrf_tau,  # tau
                        n_rep_ddrf,  # n_rep_ddrf
                        _I_['ddrft'],  # ddrft
                        trans[transition],  # mw freq
                        amp,  # mw amp
                        ddrf_amp,  # rf amp
                        pi2_1 = False, # initial pi/2 pulse
                        pi2_2 = False, # final pi/2 pulse
                        constant_phase_offset=True,
                        )
                    accumulated_phase += reps_phase_inc # follow the nuc phase after each gate due to over rotation around z
                def Gypi2_nuc():
                    nonlocal accumulated_phase
                    sna.ddrf(mcas,
                        0, # global_mw_phase #phase around X
                        np.pi/2, # second_mw_phase #phase around Y
                        ddrf_phase_inc, # rf_phase_increment
                        accumulated_phase+np.pi/2, # rotation_axis
                        pi_dur, # pi electron
                        pi2_dur, # pi/2 electron
                        coupling,  # detuning
                        _I_['bath_freq_Si'] if 'Si' in _I_['spin'] else _I_['bath_freq_C'],  # bath freq
                        ddrf_tau,  # tau
                        n_rep_ddrf,  # n_rep_ddrf
                        _I_['ddrft'],  # ddrft
                        trans[transition],  # mw freq
                        amp,  # mw amp
                        ddrf_amp,  # rf amp
                        pi2_1 = False, # initial pi/2 pulse
                        pi2_2 = False, # final pi/2 pulse
                        constant_phase_offset=True,
                        )
                    accumulated_phase += reps_phase_inc # follow the nuc phase after each gate due to over rotation around z
                def Gxpi_nuc():
                    pass
                def Gypi_nuc():
                    pass
                def CNOT():
                    pass

                funcs = {'null': null,
                        # qubit 0 (electron)
                        # 'Gi': idle, 'Gxpi2': Gxpi2, 'Gypi2': Gypi2, 'Gxpi': Gxpi, 'Gypi': Gypi,
                        # qubit 1 (nuclear) -- empty for now
                        'Gi': Gi_nuc, 'Gxpi2': Gxpi2_nuc, 'Gypi2': Gypi2_nuc,
                        #'Gi_nuc': Gi_nuc, 'Gxpi2_nuc': Gxpi2_nuc, 'Gypi2_nuc': Gypi2_nuc,
                        'Gxpi_nuc': Gxpi_nuc, 'Gypi_nuc': Gypi_nuc,
                        # two-qubit gate -- empty for now (name must match the pyGSTi gate label)
                        'Gcnot': CNOT}

                print("Circuit:", circuit)
                print("Call sequence:", run_circuit(circuit, funcs))
                return accumulated_phase

            # def electron rabi
            def cnot(amp, dur, freq,phase=0):
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur,1),
                    amplitudes=[amp],
                    frequencies=[freq],
                    mixer_deg=[-90],
                    phase=[phase*180/np.pi],
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
            
            def ddrf_init(spin,state,ddrft,index,loops=3,electron_init=False,new_segment=False,electron_init_in_loop=False,individual_segments=False):
                spin_i=[1,0][spin==_I_["spin"]]
                print("spins",spin_i)
                #bath_freq,coupling,ddrf_tau,ddrf_amp,ddrf_phase_inc,n_rep_ddrf,ddrf_phase_init,ddrf_phase_read,pi2_2_MW_phase,reps_phase_inc=get_params(spin,state,ddrft,index)

                print("electron_init=",electron_init,"new_segment=",new_segment,"electron_init_in_loop=", electron_init_in_loop, "individual_segments=",individual_segments )
                print("params=",bath_freq,coupling,ddrf_tau,ddrf_amp,ddrf_phase_inc,ddrf_phase_init,ddrf_phase_read,pi2_2_MW_phase)

            
                def function():
                        if electron_init and not electron_init_in_loop:
                            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .1, newsegment=True) #FIXME max_amp = 0.24

                        if new_segment:
                            print("new segment")
                            mcas.start_new_segment(f'ddrf_init_{spin}', loop_count=loop) #FIXME loop_count = 3
                        
                        if electron_init and electron_init_in_loop:
                            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .1, newsegment=False) #FIXME max_amp = 0.24

                        mcas.asc(length_mus=0.256, gateMW=True, green = True)
                        sna.ddrf(mcas,
                            np.pi/2, # global_mw_phase
                            -np.pi/2, # second_mw_phase
                            ddrf_phase_inc, # rf_phase_increment
                            0.0, #rotation axis
                            #[increment_1,increment_2][spin_i], # rotation_axis
                            pi_dur, # pi electron
                            pi2_dur, # pi electron
                            coupling,  # detuning
                            bath_freq,  # bath freq
                            ddrf_tau,  # tau
                            n_rep_ddrf,  # n_rep_ddrf
                            ddrft,  # ddrft
                            trans[transition],  # mw freq
                            amp,  # mw amp
                            ddrf_amp,  # rf amp
                            constant_phase_offset=True,
                            )
                        sna.ddrf(mcas,
                            0, # global_mw_phase
                            0, # second_mw_phase
                            ddrf_phase_inc, # rf_phase_increment
                            #1.0*[increment_1,increment_2][spin_i]+np.pi/2, # rotation_axis
                            np.pi/2, # rotation_axis
                            pi_dur, # pi electron
                            pi2_dur, # pi electron
                            coupling,  # detuning
                            bath_freq,  # bath freq
                            ddrf_tau,  # tau
                            n_rep_ddrf,  # n_rep_ddrf
                            ddrft,  # ddrft
                            trans[transition],  # mw freq
                            amp,  # mw amp
                            ddrf_amp,  # rf amp
                            pi2_1 = False, # pi half before DDRF
                            pi2_2 = False, # pi half after DDRF
                            constant_phase_offset=True,
                            )

                if individual_segments:
                    loop=1
                    for i in range(loops):
                        function()
                else:
                    loop=loops
                    function()

        ### SEQUENCE STARTS HERE ###
        # Repump
            sna.repump(mcas, dur = 30)
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

        # Initialize electron and nuclear spin
            ddrf_init(_I_["spin"],_I_["state"],_I_["ddrft"],_I_["file_index"],loops=3,electron_init=True,new_segment=True,electron_init_in_loop=True,individual_segments=False)
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L'+trans_idx]], [trans['R'+trans_idx]], segment_length = 10, max_amp = .15, newsegment=False) #FIXME max_amp = 0.24
                        
            
        # Start actual Sequence
            accumulated_phase = GST_to_NucOPs(_I_['circuits'], mcas, q0_dict, q1_dict)

        # Flip nuc z to x for readout
            mcas.start_new_segment(name='DDRF_RO_')
            rf_pulse(bath_freq + coupling, amp=q1_dict['pi2_amp'], dur=q1_dict['gate_dur'], phase=np.rad2deg(accumulated_phase))
        # Write nuc x state to electron spin
            sna.ddrf(mcas,
                np.pi/2, # global_mw_phase
                -np.pi/2, # second_mw_phase
                ddrf_phase_inc, # rf_phase_increment
                #ddrf_phase_init_1 + ddrf_phase_read_1, # rotation_axis
                accumulated_phase+_I_['readout_phase'], 
                pi_dur, # pi electron
                pi2_dur, # pi electron
                coupling,  # detuning
                bath_freq,  # bath freq
                ddrf_tau,  # tau
                n_rep_ddrf,  # n_rep_ddrf
                _I_['ddrft'],  # ddrft
                trans[transition],  # mw freq
                amp,  # mw amp
                ddrf_amp,  # rf amp
                constant_phase_offset=True,
                )   
        
        # Copy electron state to nuclear state
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
        # CRC.
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[500],
                    wait_dur=0.0,
                    robust=False,
                    nuc='charge_state',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=2,
                    )

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements, n_vals = _I_['n_vals'])
        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
        ['init', '<', 8, 0, 0, 1], #SSR1
        ['result', '>', 9, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        #['result', '>', 0, 6, 0, 2], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 6, 1, 0, 1],   #CRC

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
    nuclear.do_ple_refocusA2 =  True

    # ODMR refocus
    nuclear.refocus_cw_odmr = False
    nuclear.refocus_pulsed_odmr = False

    # confocal refocus
    nuclear.do_confocal_repump_refocus = False
    nuclear.do_confocal_A1A2_refocus =  True
    nuclear.do_confocal_A2MW_refocus = False
    nuclear.do_repump = False
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 600
    nuclear.confocal_refocus_interval = 3000  # seconds
    nuclear.odmr_refocus_interval = 6000

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    tesla_z = nuclear.queue._transition_tracker.current_magnetic_field_vector[0]
    tesla_x = nuclear.queue._transition_tracker.current_magnetic_field_vector[1]
    c_bath = nuclear.queue._transition_tracker.c_bath
    si_bath = nuclear.queue._transition_tracker.si_bath
    
    # GST_file = "C:/src/qudi/notebooks/UserScripts/29Si5/GST/20260929_1Q_Gi-Gxpi2-Gypi2/data/dataset.txt"
    # circuits = list()
    # with open(GST_file, "r") as file:
    #     for i, row in enumerate(file):
    #         if i == 0: continue # remove header
    #         circuits.append(row.split()[0])
    circuits = ['(Gxpi2)^%d@(Q0)' % n for n in (1,2,3,4,5)]   # or Gypi2, (Gxpi2Gypi2)^n, ...
    
    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('A2_power', [20]),
            ('t_read', [1.024 * 4]),
            ('state', ['-3/2']),
            ('n_vals', [1500]),
            ('init_time', [150]),
            ('n_ssr2', [2000]),
            ('n_ssr1', [1000]),
            ("Bfield", [tesla_z]),
            ('bath_freq_C', [c_bath]),
            ('bath_freq_Si', [si_bath]),
            ('init_nuc_state', ['1']),
            ('spin', ['Si4']),
            ('file_index', [-1]),
            ('ddrft', ['xy4']),
            ('comment', ['testig_new_ddrft']),
            ('Tau_finder_tau_from_file', [0]),
            ('circuits', ['(Gi)@(Q0)','(Gxpi2Gxpi2)@(Q0)','(Gxpi2Gxpi2Gxpi2Gxpi2)@(Q0)']),
            #('ddrf_amp', list(np.linspace(0,1,21))),
            ('readout_phase', [0., np.pi/2]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 1


def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 7 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    #nuclear.pld.fit_function = 'lorentz'
    settings()
    print('run_fun started')
    nuclear.run(abort)