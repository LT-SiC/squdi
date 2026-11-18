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
from PyQt5 import QtTest

import re

seq_name = os.path.basename(__file__).split('.')[0]
nuclear = sch.create_nuclear(__file__)
with open(os.path.abspath(__file__).split('.')[0] + ".py", 'r') as f:
    meas_code = f.read()

__SAMPLE_FREQUENCY__ = 12e3  # e.__SAMPLE_FREQUENCY__

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name=None):
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})

        # ------------------------------------------------------------------------
        # First def some functions
        # ------------------------------------------------------------------------
        def erabi(freq, length, amp, phase=0.0, pulseshape = 'sinehermite'):
            sna.electron_rabi(mcas,
                                name='electron rabi',
                                length_mus=E.round_length_mus_to_x_multiple_ps(length,1),
                                amplitudes=[amp], #FIXME list or float?
                                frequencies=[freq],
                                phases=[np.rad2deg(phase)], #FIXME "phases" or "phase"?
                                # CHECK AWG FILE TO SEE IF PHASES ARE USED CORRECTLY
                                new_segment=False,
                                gateMW=True,
                                mixer_deg=-90,
                                pulseshape = pulseshape
                                )

        def waveform(seq, sequence_name = None):
            if sequence_name:
                mcas.start_new_segment(sequence_name)

            mw = seq.times_fields_aphi('mw')
            wait = seq.times_fields_aphi('wait')
            rise_time = 0.256
            for k, step in enumerate(seq.sequence_steps):
                idx = int(step[1]) - 1 ## what happens here? Why go one step back?
                # pi pulses
                if step[0] == 'mw':
                    erabi(freq=q0_dict['freq'],
                            length=q0_dict['gate_dur'],
                            amp=q0_dict['pi_amp'],
                            phase=mw[idx, 2])
                # close gate during long waits
                elif step[0] == 'wait':
                    if wait[idx, 0] > rise_time:
                        mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(wait[idx, 0]-rise_time), gateMW = False)
                        mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(rise_time), gateMW = True)
                    else:
                        mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(wait[idx, 0]), gateMW = True)

        def XY8(tau):
            rabi_period = q0_dict['gate_dur'] * 2
            dd = sc.DD_adapted_tau(dd_type='{}_{}'.format(1, 'xy8'), pi_dur = q0_dict['gate_dur'],
                        tau=tau) # sc is automatically loaded by qudi already
            waveform(dd)
        
        def GST_to_NucOPs(circuit, dd_tau):
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
                XY8(dd_tau)
            def Gxpi2(): # print("pi2x")
                XY8(dd_tau)
                erabi(q0_dict['freq'], q0_dict['gate_dur'], q0_dict['pi2_amp'], phase=0.0)
                XY8(dd_tau)
            def Gypi2(): # print("pi2y")
                XY8(dd_tau)
                erabi(q0_dict['freq'], q0_dict['gate_dur'], q0_dict['pi2_amp'], phase=np.pi/2)
                XY8(dd_tau)
            def Gxpi(): # print("pix")
                XY8(dd_tau)
                erabi(q0_dict['freq'], q0_dict['gate_dur'], q0_dict['pi_amp'], phase=0)
                XY8(dd_tau)
            def Gypi(): # print("piy")
                XY8(dd_tau)
                erabi(q0_dict['freq'], q0_dict['gate_dur'], q0_dict['pi_amp'], phase=np.pi/2)
                XY8(dd_tau)
                
            # ------------------------------------------------------------------
            # Second qubit (nuclear spin) -- TO BE FILLED MANUALLY for 2-qubit GST
            # ------------------------------------------------------------------
            def Gi_nuc():
                pass
            def Gxpi2_nuc():
                pass
            def Gypi2_nuc():
                pass
            def Gxpi_nuc():
                pass
            def Gypi_nuc():
                pass
            def CNOT():
                pass

            funcs = {'null': null,
                    # qubit 0 (electron)
                    'Gi': idle, 'Gxpi2': Gxpi2, 'Gypi2': Gypi2, 'Gxpi': Gxpi, 'Gypi': Gypi,
                    # qubit 1 (nuclear) -- empty for now
                    'Gi_nuc': Gi_nuc, 'Gxpi2_nuc': Gxpi2_nuc, 'Gypi2_nuc': Gypi2_nuc,
                    'Gxpi_nuc': Gxpi_nuc, 'Gypi_nuc': Gypi_nuc,
                    # two-qubit gate -- empty for now (name must match the pyGSTi gate label)
                    'Gcnot': CNOT}

            print("Circuit:", circuit)
            print("Call sequence:", run_circuit(circuit, funcs))

        # -------------------------------------------------------------------------
        # Load experimental parameters
        # like frequencies, gate durations and amplitudes
        # -------------------------------------------------------------------------
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]

        for idx, _I_ in current_iterator_df.iterrows():

            ### NUCLEAR RABI PARAMETERS ###
            si1_freq, si1_amp, si1_pi, si1_pi2 = sna.get_hardcoded_si1_values(_I_['state'], _I_['bath_freq_Si'])
            
            ### ELECTRON RABI PARAMETERS ###
            trans_idx = _I_['init_nuc_state']
            if '-' in _I_['state']:
                transition = 'L'+trans_idx
            elif '+' in _I_['state']:
                transition = 'R'+trans_idx
            freq = trans[transition]
            
            # pi_amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(transition,fast=True)
            q0_dict = {'pi_amp': 0.95, # transfer into sna when working
                       #'pi2_amp': 0.45,
                       'pi2_amp': _I_['pi2_amp'],
                       'gate_dur': 0.128,
                       'freq': freq
                    }

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
            
            


        ### SEQUENCE STARTS HERE ###
        # Repump
            sna.repump(mcas, dur = 30)
        # Init nuclear via CNOT
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(trans_idx,weak=True)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256,1), gateMW = True)
            erabi(trans[transition], pi_dur_read, [R_amp_read, L_amp_read]["L" in transition], pulseshape = 'sine') # CnNOTe            
            rf_pulse(si1_freq, amp =si1_amp, dur = si1_pi)
        # Confirm initialized nuclear spin via SSR
            if trans_idx == '1':
                ssr_freqs=[trans['L2'], trans['R2']]
                read_idx = '2'
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                read_idx = '1'

            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values_for_readout(read_idx,weak=True)
            #print(R_amp_read,L_amp_read, pi_dur_read)
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
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .15)
            
        # Start actual Sequence
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True)               
            GST_to_NucOPs(_I_['circuits'], _I_['dd_tau'])
            
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

    nuclear.x_axis_title = 'Circuits'
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
    
    #GST_file = "C:/src/qudi/notebooks/UserScripts/29Si5/GST/dataset_smq1Q_XXYI.txt"
    #GST_file = "C:/src/qudi/notebooks/UserScripts/29Si5/GST/20260929_1Q_Gi-Gxpi2-Gypi2/data/dataset.txt"
    # circuits = list()
    # with open(GST_file, "r") as file:
    #     for i, row in enumerate(file):
    #         if i == 0: continue # remove header
    #         circuits.append(row.split()[0])
    # in settings()
    circuits = ['(Gxpi2)^%d@(Q0)' % n for n in [2,22,42,62]]   # or Gypi2, (Gxpi2Gypi2)^n, ...
    
    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('A2_power', [20]),
            ('t_read', [1.024 * 4]),
            ('state', ['-3/2']),
            ('n_vals', [1500]),
            ('init_time', [300]),
            ('n_ssr2', [2000]),
            ('n_ssr1', [1000]),
            ("Bfield", [tesla_z]),
            ('bath_freq_c', [c_bath]),
            ('bath_freq_Si', [si_bath]),
            ('init_nuc_state', ['1']),
            #('pi2_amp', [*np.linspace(0., 0.99, 21)]),
            #('repetitions', [2,22,42,62]),
            ('pi2_amp', list(np.linspace(0.43, 0.47, 21))+list(np.linspace(0.93, 0.97, 21))),
            ('dd_tau', [E.round_length_mus_to_x_multiple_ps(8.192,1)]),
            ('circuits', circuits),
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