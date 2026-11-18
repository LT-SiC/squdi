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
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-L'+trans_idx, period=_I_['period']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L'+trans_idx, period=_I_['period']).pi)
                rabi_period = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L'+trans_idx, period=_I_['period']).period)
            elif 'p' in _I_['state']:
                transition = 'R'+trans_idx
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-R'+trans_idx, period=_I_['period']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-R'+trans_idx, period=_I_['period']).pi)
                rabi_period = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-R'+trans_idx, period=_I_['period']).period)

            rf_freq = {'m32': 8.991558,  'm12':4.169322, 'p12': 0.649641, 'p32': 5.4661078}[_I_['state']]
            rf_dur = self.queue.tt.rp('29si5 ms'+_I_['state'].replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5'), amp = _I_['rf_amp']).pi
            rf_amp = self.queue.tt.rp('29si5 ms'+_I_['state'].replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5'), amp = _I_['rf_amp']).amp

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
                amp = rf_amp if amp is None else amp
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1', gateRF = True)
                if dur is None:
                    dur = rf_dur
                mcas.asc(
                    length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                    name='nuc',
                    gateRF = True,
                    pd2g2={"type": "sinehermite", "frequencies": [freq], "amplitudes": [amp], "phases": [phase],
                           "phase_type_offset": 'coherent'}
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
 
                    rf_pulse(freq=Bath_freq, amp =Bath_amp, dur=Bath_dur)
                    #if _I_["state"]=="p32":
                    cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'1'])
                    cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'2'])
                    rf_pulse(freq=1.49230966, amp =Bath_amp, dur=Bath_dur)
                    #if _I_["state"]=="p32":
                    cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'1'])
                    cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'2'])
                    
                # Second Phase
                    mcas.start_new_segment(name='SecondPhaseMeasurement', loop_count=1)
                    if _I_["cnot"]:
                        cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'1'])
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(Tau))
                    if _I_["cnot"]:
                        cnot(amp, pi_dur*_I_["multiplier"], trans[MW_Trans+'2'])
                        
                # Hadamard
                    if _I_["adaptive_phase"]:
                        F={"m12":-1/26.0,"p32":1/22.35,"m32":1/26.8}[_I_["state"]]
                        #SSR2 result should always start with beeing dark -> it will be our phase=0 
                        print(F*(Tau)*360)
                        acumulated_phase=F*(Tau)*360
                    else:
                        acumulated_phase=0
                    phase_dict={"m12":0,"m32":245.15738055084415,"p32":136.85279226471275}
                    add_phase=phase_dict[_I_["state"]]+_I_["add_phase"] #-> to be bright
                    #acumulated_phase=80 #fixed to test for oscilations

                    rf_pulse(rf_freq, dur=rf_dur / 2, phase= acumulated_phase + add_phase+ _I_['readout_phase'] )
                    #rf_pulse(rf_freq, dur=rf_dur / 2, phase= phase + _I_['readout_phase'])


        # Nuclear Init
            sna.repump(mcas, dur = 10)
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            cnot(amp, pi_dur, trans[transition])
            rf_pulse(rf_freq)

        ### READOUT ###
            pi_durL = E.round_length_mus_to_x_multiple_ps(
                self.queue.tt.rp('e_rabi_ou350deg-90-L'+trans_idx, period=_I_['period']).pi)
            if _I_["init_nuc_state"]=="1":
                #print("ssr on 1")
                ssr_freqs=[trans['L2'], trans['R2']]
                ampL = self.queue.tt.rp('e_rabi_ou350deg-90-L2', period=_I_['period']).amp
                ampR = self.queue.tt.rp('e_rabi_ou350deg-90-R2', period=_I_['period']).amp
            else:
                ssr_freqs=[trans['L1'], trans['R1']]
                ampL = self.queue.tt.rp('e_rabi_ou350deg-90-L1', period=_I_['period']).amp
                ampR = self.queue.tt.rp('e_rabi_ou350deg-90-R1', period=_I_['period']).amp
                #print("ssr on 2")

            #SSR1 # init nuc
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
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
            sna.electron_init(mcas, _I_['state'], _I_['init_time'], [trans['L1'],trans['L2']], [trans['R1'],trans['R2']], segment_length = 10, max_amp = .2)
            
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
                base_freq=[_I_["base_freq_Si"],_I_["base_freq_C"]]["C" in _I_["Bath"]]
                rf_freq_bath=_I_["rf_freq_bath"]#base_freq+_I_["coupling"]
                rf_amp_bath=[0.2424,0.1653]["C" in _I_["Bath"]]
                #rf_freq_bath=_I_["rf_freq_bath"]
                #rf_amp_bath=_I_["rf_amp_bath"]
                if _I_["adaptive_tau"]:
                    tau=abs(((180%360)/360)/((_I_["rf_freq_bath"]-base_freq)/([0.5,1.5]["12" in _I_["state"]])))  #_I_["tau"]
                else:
                    tau=_I_["tau"]


            ENDOR(_I_["state"],rf_freq_bath,rf_amp_bath,_I_["rf_dur_bath"],tau)
            sna.ssr(mcas=mcas, queue=self.queue,
                    frequencies=[ssr_freqs],
                    wait_dur=0.0,
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
        ['init', '<', 6, 0, 0, 1], #SSR1
        ['result', '>', 6, 0, 0, 1], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        #['result', '>', 0, 6, 0, 2], #SSR2 # Put "int(_I_['n_ssr']" as nlp_per_point?
        ['init', '>', 8, 1, 0, 1],   #CRC
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
            ('period', [.5]),
            ('tau', [3.]), # 15 #tau #*np.linspace(0,50,36)
            ('init_nuc_state', ['2']),
            ('state', ["m32"]),
            ('rf_amp', [.5]),
            ('cnot', [True]),
            ('rf_dur_bath', [200]),
            #('rf_dur_bath', [400]),
            ("reinit_time",[0]),
            ("multiplier",[1.]),
            ('rf_amp_bath',[0.2424*2]),#0.1653 #0.2424 #*np.linspace(0,0.4,20)[::-1] #[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9][::-1] # np.linspace(0.1,1,10)[::-1]
            #('rf_amp_bath',[0.2424]),#0.1653 #0.2424 #*np.linspace(0,0.4,20)[::-1] #[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9][::-1] # np.linspace(0.1,1,10)[::-1]
            ("enhanced",[False]), #allows the use of referenced values below
            ("coupling", [0]),# [*np.arange(-0.08,0.08,0.0005)]),
            ("Bath",["Si"]),#["Si","C"]),
            ("base_freq_C",[c_bath]),
            ("base_freq_Si",[si_bath]),
            ('readout_phase', [0., 180.]),
            ("adaptive_tau",[True, False]),
            ('rf_freq_bath', [*np.arange(2.03,2.05,0.001)])#*np.arange(c_bath-0.02,c_bath+0.02, 0.0005) #*np.arange(2.2-0.02,2.2+0.02, 0.001),#*np.arange(si_bath-0.2,si_bath+0.2, 0.005*2)#*(np.arange(1.677,1.694, 0.001)-0.160)# *np.arange(1.677,1.694, 0.0005) #1.68477[*np.arange(1.67,1.72, 0.001)]),#2.2432*np.arange(si_bath-0.2,si_bath+0.2, 0.005)

        )
    )
    nuclear.number_of_simultaneous_measurements = 2

def run_fun(abort, **kwargs):
    print(1, ' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 10 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    nuclear.pld.fit_function='cosine'
    settings()
    print('run_fun started')
    nuclear.run(abort)
