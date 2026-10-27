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

ael = 1.0


def init_state_drive(state):
    '''
    State could be "p(m)3(1)2+(-,n)", example m32+, or p32-, p32n
    '''
    mw_init32R2 = 0
    mw_init32R1 = 0
    mw_init32m = 0
    RF_init12p = 0
    RF_init12m = 0
    ## MW drive
    if 'p' in state:
        if '+' in state:
            RF_init12m = 0.1
            #RF_init12p = 0.1
            mw_init32R2 = 0.08
            mw_init32m = 0.4
        elif '-' in state:
            RF_init12m = 0.1
            #RF_init12p = 0.1
            mw_init32R1 = 0.08
            mw_init32m = 0.0
    elif 'm' in state:
        mw_init32R2 = 0.04
        mw_init32R1 = 0.04

    pd2g1 = {
        'type': 'sine',
        'phases': [0],
        'amplitudes': [
            mw_init32R2,
            mw_init32R1,
            mw_init32m,
            mw_init32m,
            RF_init12p,
            RF_init12m],
        # 'frequencies':[30.5,38.5],
        'frequencies': [183.48, 185.66, 44.29, 46.33, 3.4, 1.026]
    }

    return pd2g1

freqs = {'L1': 43.896, 'L2': 44.444, 'L3': 46.142, 'L4': 46.622, 'R1': 183.296, 'R2': 183.741, 'R3': 185.418, 'R4': 185.910}

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df,sequence_name = None):
        sequence_name = 'Electron_FID'
        #print(self, current_iterator_df)
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1,2], 'ps': [1]})
        mcas.start_new_segment('start_sequence')
        mcas.asc(length_mus=5.0, repump=True, name='Repump')
        mcas.asc(length_mus=10.0)

        for idx, _I_ in current_iterator_df.iterrows():
            state = _I_['init_state']
            mcas.asc(
                A1='32' in state,
                A2='12' in state,
                length_mus=_I_['init_time'],
                name='resonant_init',
                pd2g1=init_state_drive(state)
            )

            mcas.asc(length_mus=0.5)

            pi_2_dur = self.queue.tt.rp('e_rabi_ou350deg-90-L', amp=0.5).pi2
            pi_dur = self.queue.tt.rp('e_rabi_ou350deg-90-L', amp=0.5).pi
            

            ### PI/2 of electron ###
            if '32' in state:
                freq = (freqs['L3']+freqs['L4'])/2
            else:
                freq = (freqs['L1']+freqs['L2'])/2
            L_dur = 1.025 #pi

            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_full_sample(L_dur/2),
                amplitudes=[0.02],
                frequencies=[freq],
                phases = [0],
                mixer_deg=[-90]
            )

            if _I_['seq'] == 'fid':
                mcas.asc(length_mus=_I_['tau'])
            elif _I_['seq'] == 'he':
                mcas.asc(length_mus=_I_['tau'])

            if _I_['seq'] == 'fid':
                pass
            elif _I_['seq'] == 'he':
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus=E.round_length_mus_full_sample(L_dur),
                    amplitudes=[0.02],
                    frequencies=[freq],
                    phases = [0],
                    mixer_deg=[-90]
                )
            
            if _I_['seq'] == 'fid':
                mcas.asc(length_mus=_I_['tau'])
            elif _I_['seq'] == 'he':
                mcas.asc(length_mus=_I_['tau'])

            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=E.round_length_mus_full_sample(L_dur/2),
                amplitudes=[0.02],
                frequencies=[freq],
                phases = [_I_['phase_pi2_2']],
                mixer_deg = [-90]
            )
            
            mcas.asc(length_mus=0.1)

            freq = [33.0]
            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=1.5)
            elif _I_['readout'] == 'A1':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=1.5)
            mcas.asc(length_mus=0.5, name='sequence wait 2')

        self.queue._gated_counter.set_n_values(mcas,
        self.number_of_simultaneous_measurements) #how to get here the queue? readout duration/sequence length) #how to get here the queue?

        return mcas
    return ret_mcas

def settings(pdc={}):
    ana_seq=[
        ['result', '>', 1, 1, 0, 1],
        # ['init', '>', 1, 1, 0, 1],
        # ['init', '>', 5, 1, 0, 1],
    ]
    sch.settings(
        nuclear=nuclear,
        ret_mcas=ret_ret_mcas(pdc),
        analyze_sequence=ana_seq,
        pdc=pdc,
        meas_code=meas_code
    )

    nuclear.x_axis_title = 'Index'
    #nuclear.analyze_type = 'consecutive'
    # nuclear.analyze_type = 'standard'
    nuclear.analyze_type = 'average' #experimental feature for the fast 
    #nuclear.analyze_type = None
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

    # Resonant Laser power
    nuclear.checkA1LaserPower = False # Not yet implemented in powerstablogic
    nuclear.checkA2LaserPower = False
    nuclear.A1LaserPower = 1 #nW
    nuclear.A2LaserPower = 3 #nW

    nuclear.ple_refocus_interval = 900
    nuclear.confocal_refocus_interval = 900  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False


    nuclear.parameters = OrderedDict(
        (
            ('sweeps', range(50)),
            ('A2_power', [3]),
            ('init_state', ['m12']),
            ('init_time', [100]),
            ('seq', ['he']),
            ('readout',['A2']),
            ('tau', E.round_length_mus_full_sample(np.linspace(0.0, 8*2, 4*81))), #HE
            ('phase_pi2_2', [0, 180])
        )
    )
    nuclear.number_of_simultaneous_measurements =  2*len(
            # nuclear.parameters['tau_2'])*len(
            nuclear.parameters['phase_pi2_2']
        )

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 20e6
    nuclear.debug_mode = False
    nuclear.hashed = False
    settings()
    print('run_fun started')
    nuclear.run(abort)