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
        mw_init32L1 = 0.1
        mw_init32L2 = 0.1
    elif 'm' in state:
        mw_init32R1 = 0.1
        mw_init32R2 = 0.1
    pd2g1 = {
        'type': 'sine',
        'phases': [0],
        'amplitudes': [
            mw_init32L1,
            mw_init32L2,
            mw_init32R1,
            mw_init32R2],
        'frequencies': freqs
    }

    return pd2g1


def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name=None):
        sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.c13_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]

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
            
            rf_freq = {'m32': 8.99198,  'm12':4.169902, 'p12': 0.649641, 'p32': 5.465629}[_I_['state']]
            #rf_omega = {'m32': 0.054881, 'm12':0.021297, 'p12': 0.02, 'p32': 0.024323}[_I_['state']]/2
            rf_dur = self.queue.tt.rp('13c5 ms'+_I_['state'].replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5'), amp=0.9).pi
            rf_amp = self.queue.tt.rp('13c5 ms'+_I_['state'].replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5'), amp=0.9).amp
            #rf_dur = {'m32': 24.55/2, 'm12':25.35, 'p12': 25.35, 'p32': 14.08}[_I_['state']]

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

            def electron_init(st=None ,t=None):
                state = _I_['state'] if st is None else st
                segment_length = 5
                it = _I_['init_time'] if t is None else t
                loops, correction_mus = shared.calculate_loop_count(_I_['init_time'], segment_length)
                mcas.start_new_segment(name='init', loop_count=loops)
                mcas.asc(
                    A1='32' in state,
                    A2='12' in state,
                    gateMW=True,
                    length_mus=E.round_length_mus_to_x_multiple_ps(segment_length),
                    name='resonant_init',
                    pd2g1=init_state_drive(state, [trans['L1'], trans['L2'], trans['R1'], trans['R2']]),
                )
                mcas.start_new_segment(name='sequence', loop_count=1)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='Init Decay')

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
                           "phase_offset_type": 'coherent'}
                )
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(2), name='RFSafetyWait2', gateRF = True)
            
            def ENDOR(state,Bath_freq,Bath_amp,Bath_dur,Tau):
                    mcas.start_new_segment('ENDOR', loop_count=1)
                    MW_Trans=["R","L"]["m" in state]

                # Hadamard
                    rf_pulse(rf_freq, dur=rf_dur / 2)  

                # First Phase
                    mcas.start_new_segment(name='FirstPhaseMeasurement', loop_count=1)
                    if _I_["cnot"]:
                        cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'1'])
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(Tau))
                    if _I_["cnot"]:
                        cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'2'])
                # Bath flip#trying a short electron int to see if there is some effect on the oscilations
                    # mcas.asc(
                    #         length_mus=E.round_length_mus_to_x_multiple_ps(_I_["reinit_time"]),
                    #         name='inter_init',
                    #         gateRF = True,
                    #         A1="12" in _I_["state"],
                    #         A2="32" in _I_["state"]
                    #     )
                    rf_pulse(freq=Bath_freq, amp =Bath_amp, dur=Bath_dur)
                # Second Phase
                    mcas.start_new_segment(name='SecondPhaseMeasurement', loop_count=1)
                    if _I_["cnot"]:
                        cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'1'])
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(Tau))
                    if _I_["cnot"]:
                        cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'2'])
                        
                # Hadamard
                    if _I_["adaptive_phase"]:
                        F={"m12":-1/26.71132784151228,"p32":1/21.726794344471777,"m32":1/27.780613018599325}[_I_["state"]]
                        #SSR2 result should always start with beeing dark -> it will be our phase=0 
                        print(F*(Tau)*360)
                        acumulated_phase=F*(Tau)*360
                    else:
                        acumulated_phase=0
                    phase_dict={"m12":0,"m32":0,"p32":0,"p12":0}
                    add_phase=phase_dict[_I_["state"]]+_I_["add_phase"] #-> to be bright
                    #acumulated_phase=80 #fixed to test for oscilations
                    phase=acumulated_phase + add_phase+ _I_['readout_phase']
                    print(_I_["state"],_I_["readout_phase"],acumulated_phase,add_phase,phase)

                    rf_pulse(rf_freq, dur=rf_dur / 2, phase= phase )
                    #rf_pulse(rf_freq, dur=rf_dur / 2, phase= phase + _I_['readout_phase'])


        # Nuclear Init
            sna.repump(mcas, dur=20)
            #sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'], trans['L2']], [trans['R1'], trans['R2']], max_amp = 0.15)
            electron_init()
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(rf_freq)

            ampL = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp
            ampR = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).amp
            pi_durL = E.round_length_mus_to_x_multiple_ps(
                self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi)
        # SSR 1
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[[trans['L1'], trans['R1']]],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=0,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read1']),
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
                    repetitions=int(_I_['n_ssr1'])
                    )
        
        # Electron init
            electron_init(st = _I_['state'], t = _I_['init_time']) # Reinit the electon state.
            
            if _I_["enhanced"]:
                #calculating parameters for optimal contrast.
                tau=abs(1/(_I_["coupling"]/([0.5,1.5]["12" in _I_["state"]])*2))
                print("Tau:",tau)
                if tau>30: #avoid too long taus where we do not get any contrast anymore
                    tau=30
                tau=E.round_length_mus_to_x_multiple_ps(tau)
                base_freq=[_I_["base_freq_Si"],_I_["base_freq_C"]]["C" in _I_["Bath"]]
                rf_freq_bath=base_freq+_I_["coupling"]
                rf_amp_bath=[0.2424,0.1653]["C" in _I_["Bath"]]
                print(rf_freq_bath,_I_["Bath"],rf_amp_bath,tau)
            else:
                rf_freq_bath=_I_["rf_freq_bath"]
                rf_amp_bath=_I_["rf_amp_bath"]
                tau=_I_["tau"]

            ENDOR(_I_["state"],rf_freq_bath,rf_amp_bath,_I_["rf_dur_bath"],tau)
        # SSR 2
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[[trans['L1'], trans['R1']]],
                    wait_dur=_I_['wait_dur'],
                    robust=False,
                    nuc='29Si8_A2',
                    mixer_deg=-90,
                    eom_ampl=0.0,
                    step_idx=1,
                    laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read2']),
                    length_mus_mw=pi_durL,
                    amplitudes=[ampL, ampR],
                    repetitions=int(_I_['n_ssr2'])
                    )
        # CRC
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
        ['init', '<', 10, 0, 0, 1], #SSR1
        ['result', '>', 10, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        #['result', '>', 0, 6, 0, 2], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 14, 1, 0, 1],   #CRC
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

    nuclear.ple_refocus_interval = 10*60 
    nuclear.confocal_refocus_interval = 10*60  # seconds
    nuclear.odmr_refocus_interval = 6000
    nuclear.follow_resonnance_by_counts=False

    # rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    Tesla=nuclear.queue._transition_tracker.current_magnetic_field#0.2087
    c_bath = 10.7084*Tesla
    si_bath = 8.465*Tesla
    tau=abs(1/(0.081/(1/2))/2) #si_bath-1.68477
    tau=E.round_length_mus_to_x_multiple_ps(tau)
    print(tau)

    #tau = []
    #for i in range(30):
    #    tau.append(np.random.random()*10)
    #plt.plot(np.sort(tau))
    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(20)),
            ('A2_power', [6]),
            ('t_read1', [1.024*4]),
            ('t_read2', [1.024*4]),
            ('wait_dur', [0.512]),
            ("adaptive_phase",[True]),
            ('add_phase', [0]),#*np.linspace(0,360,20) # 200 #340
            ('init_time', [150.]),
            ('n_ssr2', [1000]),
            ('n_ssr1', [1000]),
            ('omega', [1.4]),
            ('tau', [0]), # 15 #tau #*np.linspace(0,50,36)
            ('state', ["m12"]),
            ('cnot', [True]),
            ('rf_dur_bath', [400]),
            ("reinit_time",[0]),
            ("multiplier",[1.]),
            ('rf_amp_bath',[0.2424]),#0.1653 #0.2424 #*np.linspace(0,0.4,20)[::-1] #[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9][::-1] # np.linspace(0.1,1,10)[::-1]
            ('rf_freq_bath', [1.85]),#*np.arange(c_bath-0.02,c_bath+0.02, 0.0005) #*np.arange(2.2-0.02,2.2+0.02, 0.001),#*np.arange(si_bath-0.2,si_bath+0.2, 0.005*2)#*(np.arange(1.677,1.694, 0.001)-0.160)# *np.arange(1.677,1.694, 0.0005) #1.68477[*np.arange(1.67,1.72, 0.001)]),#2.2432*np.arange(si_bath-0.2,si_bath+0.2, 0.005)
            ("enhanced",[True]), #allows the use of referenced values below
            ("coupling", [*np.arange(-0.08,0.08,0.001)]),# [*np.arange(-0.08,0.08,0.0005)]),
            ("Bath",["Si"]),#["Si","C"]),
            ("base_freq_C",[c_bath]),
            ("base_freq_Si",[si_bath]),
            ('readout_phase', [0.,180.])

        )
    )
    nuclear.number_of_simultaneous_measurements = 1

def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 15 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    nuclear.pld.fit_function='cosine'
    settings()
    print('run_fun started')
    nuclear.run(abort)
