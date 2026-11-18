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
from qtpy import QtCore


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
        'type':'sine',
        'phases':[0],
        'amplitudes':[
                    mw_init32L1,
                    mw_init32L2,
                    mw_init32R1,
                    mw_init32R2],        
        'frequencies':freqs
    }
    
    return pd2g1

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        sequence_name = 'Electron_rabi_test' if sequence_name is None else sequence_name
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        trans = {}
        for t in ['L', 'C', 'R']:
            for i in [1, 2]:
                trans[t + str(i)] = self.queue.tt.mfl(td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]


        for idx, _I_ in current_iterator_df.iterrows():

            ### DEF ELECTRON RABI ###
            def cnot(amp, dur, freq):
                sna.electron_rabi(
                mcas,
                new_segment=False,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(dur),
                amplitudes=[amp],
                frequencies=[freq],
                mixer_deg=[-90]
                )

            ### REPUMP ###
            mcas.start_new_segment('Repump', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(10.0,64), repump=True, name='Repump')
            mcas.start_new_segment('Decay', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64), name='RepumpDecay')
            
            ### INITIALIZATION ###
            state = _I_['state']
            segment_length = 5
            loops, correction_mus = shared.calculate_loop_count(_I_['init_time'],segment_length)
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, [trans['L1'],trans['L2'],trans['R1'],trans['R2']]),
                ) 
            
            mcas.start_new_segment(name='sequence', loop_count = 1)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name = 'Init Decay')  

            # Conditional flip of electron
            if 'm' in _I_['state']:
                transition1 = 'L'+ str(_I_['read_freq'])
                transition2 = 'L1'
                amp = self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).amp
                pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-L', omega=_I_['omega']).pi)
            elif 'p' in _I_['state']:
                transition1 = 'R'+ str(_I_['read_freq'])
                transition2 = 'R1'
                #amp = self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).amp
                #pi_dur = E.round_length_mus_to_x_multiple_ps(self.queue.tt.rp('e_rabi_ou350deg-90-R', omega=_I_['omega']).pi)
                amp = 0.2863927
                pi_dur = .512
            
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256))
            cnot(amp, pi_dur, trans[transition1])

            # Nuclear flip
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1), name='RFSafetyWait1')
            
            freq = {'m32': 1.15, 'm12':0.14, 'p12': 2.405, 'p32': 3.699}[_I_['state']]+_I_['rf_freq']
            dur=_I_["rf_dur"]
            print(freq)
            
            mcas.asc(
                length_mus=E.round_length_mus_to_x_multiple_ps(dur), 
                name='nuc',
                pd2g2 = {"type":"sine", "frequencies":[freq],"amplitudes":[_I_['rf_amp']], "phase_type_offset": 'absolute'}
            ) 
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(5), name='RFSafetyWait2')

            # flip electron back
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW = True, name='gateMW')
            cnot(amp, pi_dur, trans[transition2])
            
            # if '12' in _I_['state']:
            #     sna.ssr(mcas = mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
            #         nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            # elif '32' in _I_['state']:
            sna.ssr(mcas = mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False,
                nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.512), name='sequence wait 2')

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['result', '>', 1, 1, 0, 1],
        # ['init', '>', 1, 1, 0, 1],
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
    nuclear.do_repump = False
    nuclear.check_A2_power = False

    nuclear.ple_refocus_interval = 120
    nuclear.confocal_refocus_interval = 200  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False
    
    # -3/2 expected at 11.82
    # +3/2 expected at 14.15
    nuclear.parameters = OrderedDict( 
        (
            ('sweeps', range(20)),
            ('A2_power',[5]),
            ('omega',[.2]),
            ('t_read',[2.048]),
            ('init_time', [50]),
            ("rf_dur",[60,100]),
            ('state', ['p12']),
            ('rf_freq', np.arange(-0.1,0.1,0.004)),
            ('readout', ['A2']),
            ('rf_amp', [0.7,0.3,0.1]),
            ('read_freq', [1,2]),
        )
    )
    nuclear.number_of_simultaneous_measurements =  2

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 5*1e6
    nuclear.pld.fit_function='lorentz'
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    #sig=QtCore.Signal(object, QtCore.Qt.QueuedConnection)
    #sig.connect(nuclear.run)
    #sig.emit(abort)
    nuclear.run(abort)