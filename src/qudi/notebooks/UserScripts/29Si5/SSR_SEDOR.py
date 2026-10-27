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
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]

        for idx, _I_ in current_iterator_df.iterrows():

            ### ELECTRON RABI PARAMETERS ###
            trans_idx = _I_['init_nuc_state']
            if 'm' in _I_['state']:
                transition = 'L'+trans_idx
                #amp = self.queue.tt.RP('e_rabi_ou350deg-90-L'+trans_idx, period=_I_['period']).amp
                #pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-L'+trans_idx, period=_I_['period']).pi,1)
                #pi2_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-L'+trans_idx, period=_I_['period']).pi2,1)
                #rabi_period = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-L'+trans_idx, period=_I_['period']).period,1)

            elif 'p' in _I_['state']:
                transition = 'R'+trans_idx
                #amp = self.queue.tt.RP('e_rabi_ou350deg-90-R'+trans_idx, period=_I_['period']).amp
                #pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-R'+trans_idx, period=_I_['period']).pi,1)
                #pi2_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-R'+trans_idx, period=_I_['period']).pi2,1)
                #rabi_period = E.round_length_mus_to_x_multiple_ps(self.queue.tt.RP('e_rabi_ou350deg-90-R'+trans_idx, period=_I_['period']).period,1)

            si5_freq, si5_amp, si5_pi, si5_pi2 = sna.get_hardcoded_si5_values(_I_['state'])
            R_amp, L_amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values(trans_idx)
            if 'p' in _I_['state']:
                amp = R_amp
            else:
                amp = L_amp

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
                    pulseshape= 'sinehermite'
                )

            def rf_pulse(freq, amp=None, dur=None, phase=0):
                amp = si5_amp if amp is None else amp
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1', gateRF = True)
                if dur is None:
                    dur = si5_pi
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    gateRF = True,
                    pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
                           "phase_type_offset": 'coherent'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)


            def erabi(freq, length, amp, phase=0.0):
                sna.electron_rabi(mcas,
                                  name='electron rabi',
                                  length_mus=length,
                                  amplitudes=[amp],
                                  frequencies=freq,
                                  phases=np.rad2deg(phase),
                                  new_segment=False,
                                  gateMW=True,
                                  mixer_deg=-90,
                                  pulseshape= 'sinehermite'
                                  )

            def waveform(seq):
                mcas.start_new_segment('waveform')
                #sna.polarize(mcas, new_segment=False)
                mw = seq.times_fields_aphi('mw')
                wait = seq.times_fields_aphi('wait')
                first_iteration = True
                for k, step in enumerate(seq.sequence_steps):
                    idx = int(step[1]) - 1
                    if step[0] == 'mw':
                        if k == 0 or k == len(seq.sequence_steps)-1:
                            erabi(freq=freq,
                                length=pi2_dur,
                                amp=amp,
                                #amp=self.queue.tt.rp('e_rabi_ou350deg-90-R'+trans_idx, period=1 / mw[idx, 1]).amp, # TODO is trans_idx correct here?
                                phase=mw[idx, 2])
                        else:
                            erabi(freq=freq,
                                length=pi_dur,
                                amp=amp,
                                #amp=self.queue.tt.rp('e_rabi_ou350deg-90-R'+trans_idx, period=1 / mw[idx, 1]).amp, # TODO is trans_idx correct here?
                                phase=mw[idx, 2])
                    elif step[0] == 'wait':
                        if first_iteration:
                            if wait[idx, 0] > 0.256:
                                mcas.asc(length_mus=wait[idx, 0]-0.256)
                                mcas.asc(length_mus=0.256, gateMW = True)
                            else:
                                mcas.asc(length_mus=wait[idx, 0], gateMW = True)
                        else:
                            erabi(freq=[_I_['target_freq']],
                                length=pi_dur,
                                amp=amp,
                                phase=mw[idx, 2])
                            if wait[idx, 0]-pi_dur > 0.256:
                                mcas.asc(length_mus=wait[idx, 0]-0.256-pi_dur)
                                mcas.asc(length_mus=0.256, gateMW = True)
                            else:
                                mcas.asc(length_mus=wait[idx, 0], gateMW = True)
                        first_iteration = False


            freq = [trans[transition]]

            def dd():
                
                pi2x = sc.Rabi(t_rabi=pi2_dur, omega=1 / (2*pi_dur), phase=0.0, control_field='mw')
                pi2_2 = sc.Rabi(t_rabi=pi2_dur, omega=1 / (2*pi_dur), phase=_I_['phase_pi2_2'],
                                control_field='mw')
                dd = sc.DD(dd_type='{}_{}'.format(_I_['n_rep_dd'], _I_['ddt']), rabi_period=(2*pi_dur),
                           tau=_I_['tau'])
                seq = sc.Concatenated([pi2x, dd, pi2_2], controls=['mw', 'wait'])
                waveform(seq)

            sna.repump(mcas, dur = 10)
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .24)
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(si5_freq)

            ### READOUT ###
            if trans_idx == '1':
                ssr_freqs=[trans['L2'], trans['R2']]
                read_idx = '2'
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                read_idx = '1'
            R_amp_read, L_amp_read, pi_dur_read, pi2_dur_read = sna.get_hardcoded_e_values(read_idx)

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


            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            

            mcas.start_new_segment('DD', loop_count=1)
            mcas.asc(length_mus=0.256, gateMW=True)
            dd()
            
            mcas.asc(length_mus=5.024)
            # CNOT nuclear. #?
            rf_pulse(si5_freq)

            sna.ssr(mcas=mcas, queue=self.queue,
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
                    repetitions=int(_I_['n_ssr2'])
                    )
            
            # sna.ssr(mcas=mcas, queue=self.queue,
            #     frequencies=[[trans['L1'], trans['R1']],[trans['L2'], trans['R2']]],
            #     wait_dur=0.0,
            #     robust=False,
            #     nuc='29Si8_A2',
            #     mixer_deg=-90,
            #     eom_ampl=0.0,
            #     step_idx=1,
            #     laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read2']),
            #     length_mus_mw=pi_durL,
            #     amplitudes=[ampL, ampR],
            #     repetitions=int(_I_['n_ssr2'])
            #     )
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

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)
        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq = [
        ['init', '<', 5, 0, 0, 1],
        ['result', '>', 9, 0, 0, 1], # Put "int(_I_['n_ssr']" as nlp_per_point?
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

    tesla=nuclear.queue._transition_tracker.current_magnetic_field#0.2087
    c_bath = 10.7084*tesla
    si_bath = 8.465*tesla

    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('A2_power', [20]),
            ('period', [.704]),
            ('t_read', [1.024 * 3]),
            ('init_time', [300]),
            ('n_ssr2', [2000]),
            ('n_ssr1', [2000]),
            ('init_nuc_state', ['2']),
            ('tau', E.round_length_mus_to_x_multiple_ps([10,17,33],1)),
            ('ddt', ['xy4']),
            ('n_rep_dd', [2]),
            ('state', ['m32']),
            ('target_freq', [*np.arange(5769+70,5800+70,0.1)]),
            ('phase_pi2_2', [0.0, np.pi]),
        )
    )
    nuclear.number_of_simultaneous_measurements = 2


def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 5 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)