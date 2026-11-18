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
freqs_all = {'R2':177.8,'R1':168.4, 'C1':98.4,'C2':107.8,'L1':30.4,'L2':38.45,'RFp12':3.4,'RFm12':6.47}
ael = 1.0

def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name = None):
        sequence_name = 'Electron_rabi_test' if sequence_name is None else sequence_name
        #print(self, current_iterator_df)
        mcas = MultiChSeq(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
        mcas.start_new_segment('start_sequence')
        mcas.asc(length_mus=5.0, repump=True, name='Repump')
        mcas.asc(length_mus=10.0)  #Decay from metastables.
        freq = [30]
        
        for idx, _I_ in current_iterator_df.iterrows():
            
            ## Preliminary....
            
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
                        mw_init32R2 = 0.04
                    elif '-' in state:
                        RF_init12m = 0.1
                        mw_init32R1 = 0.04
                    mw_init32m = 0.04
                elif 'm' in state:
                    mw_init32R2 = 0.04
                    mw_init32R1 = 0.04

                pd2g1 = {
                    'type':'sine',
                    'phases':[0],
                    'amplitudes':[
                                mw_init32R2,
                                mw_init32R1,
                                mw_init32m,
                                mw_init32m, 
                                RF_init12p,
                                RF_init12m],                    
                    #'frequencies':[30.5,38.5],
                    'frequencies':[177.8,168.4,30.4,45.5,3.4,6.47]
                }
                
                return pd2g1
            ## Decide on init state for rabi calibration.
            state = {'L1':'m','L2':'m', 'C1':'m','C2':'m','R1':'p','R2':'p'}[_I_['trans']]
            state +={'L1':'32-','L2':'m12+', 'C1':'12','C2':'m12','R1':'32n','R2':'32n'}[_I_['trans']]
            print('Initialising to',state)

            ###
            ## Sequence after repump
            ###

            mcas.asc(
                A1= '32' in state,
                A2 = '12' in state, 
                length_mus=_I_['init_time'], 
                name='resonant_init',
                pd2g1 = init_state_drive(state)
            ) 

            mcas.asc(length_mus=2.0, name='sequence wait 1')
            freqs = {'L1':30.4,'L2':38.45,'C1':98.4,'C2':107.8,'R1':168.4,'R2':177.8}[_I_['trans']]
            omega = self.queue.tt.rp('e_rabi_ou350deg-90-R2', amp=_I_['amp']).omega
            mw_duration = np.linspace(0,_I_['number_of_periods']*omega,_I_['max_index_of_taus'])
            
            sna.electron_rabi(
                mcas,
                new_segment=False,
                length_mus=mw_duration[_I_['index_of_taus']],
                amplitudes=[_I_['amp']],
                frequencies=[freqs], #Later also debug the transition frequency. 
                mixer_deg=[-90]
            )

            mcas.asc(length_mus=0.5)
            if _I_['trans'].startswith('C'): #Used later for calibration of the C
                sna.electron_rabi(
                    mcas,
                    new_segment=False,
                    length_mus= 1.0,
                    amplitudes=[0.2, 0.2],
                    frequencies=[168.4,177.8],
                    mixer_deg=[-90,-90] ##Here is not perfect., sin it needs various calibrations. 
                )
            # sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
            #         nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=3.0)
            if _I_['readout'] == 'A2':
                sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                    nuc='ple_A2', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=1.5)
            elif _I_['readout'] == 'A1':
               sna.ssr(mcas = mcas, queue=self.queue, frequencies=freq, wait_dur=0.0, robust=False,
                   nuc='ple_A1', mixer_deg=-90, eom_ampl=0.0, step_idx=0, laser_dur=1.5)
            mcas.asc(length_mus=0.5, name='sequence wait 2')

        self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements) #how to get here the queue? readout duration/sequence length.

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

    nuclear.x_axis_title = 'tau [mus]'
    #nuclear.analyze_type = 'consecutive'
    #nuclear.analyze_type = 'standard'

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

    nuclear.ple_refocus_interval = 600
    nuclear.confocal_refocus_interval = 600  # seconds
    nuclear.odmr_refocus_interval= 600

    #rabi refocus ?

    nuclear.queue._gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue._gated_counter.trace.average_results = False

    max_index_of_taus = 34

    nuclear.parameters = OrderedDict(
        (
           ('sweeps', range(5)),
            ('init_time', [100.0]),
            ('mw_init12',[0.0]), 
            ('mw_init32',[0.0]), 
            ('mw_init32R1',[0.0]), 
            ('mw_init32R2',[0.04]), 
            #('mw_init32mL1',[0.0]), 
            #('mw_init32mL2',[0.04,0.0]), 
            ('RF_init12p',[0.0]), 
            ('RF_init12m',[0.1,0.0]), 
            ('mw_init32m',[0.04]), 
            ('init', ['A2']),
            ('t_read',[1.0]),
            ('A2_power',[5]),
            ('173pi', [False]),
            ('amp', [0.05,0.1,0.2,0.3,0.4]), #at 0.2 pi pulse is 0.1, at 0.4, 0.05 ns, 0.05*50 = 2.5
            #('trans',['L1','L2','R1','R2']),
            ('trans',['L1','L2']),
            ('max_index_of_taus',[max_index_of_taus]),
            ('number_of_periods',[3.3]),
            ('index_of_taus',(range(0,max_index_of_taus))),
            ('readout', ['A2','A1']),
        )
    )
    nuclear.number_of_simultaneous_measurements =  2#2*len(nuclear.parameters['mw_duration'])#len(nuclear.parameters['phase_pi2_2'])

def run_fun(abort, **kwargs):
    print(1,' Nuclear started!!!')
    nuclear.queue = kwargs['queue']
    nuclear.queue._gated_counter.readout_duration = 5*1e6#1.4e4 #6e5 #10*1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    print('run_fun started')
    nuclear.run(abort)

    # # ------------------------------------------------------
    # df = nuclear.data.df
    # # pld = nuclear.pld.data_fit_results.df
    # df = df[['sweeps', 'average_counts', 'amp0', 'mw_duration']]
    
    # # temp_df = pd.DataFrame(columns=['amp0', 'omega', 'average_counts', 'mw_duration'])
    # temp_df = pd.DataFrame(columns=['amp0', 'omega', 'transition','date'])
    # for amp in df['amp0'].unique():
    #     print('Ampl ', amp)
    #     sub_df = df[(df['amp0'] == amp)]
    
    
    
    #     # sub_pld = pld[(pld['amp0'] == amp)]
    #     x = sub_df['mw_duration'].unique()
    #     y = sub_df.groupby(by=['mw_duration']).agg({'average_counts': np.mean}).values.ravel()
    
    #     m = lmfit_models.CosineModel()
    #     p = m.guess(data=y, x=x)
    #     r = m.fit(data=y, params=p, x=x)
    
    
    #     temp_df = pd.concat([temp_df, pd.DataFrame({
    #         'amp0': [amp],
    #         # 'omega': 1.0 / sub_pld['T'].mean(),
    #         'transition': [0],
    
    #         'omega': [1.0 / r.params['T'].value],
    #         # 'average_counts': [y],
    #         # 'mw_duration': [x],
    
    #         'date': [str(datetime.datetime.now())]
    #     })])
    
    # f = 'e_rabi_ou350deg-90'
    # temp_df = temp_df[['amp0', 'transition', 'omega', 'date']]
    
    # print(temp_df)
    # pi3d.tt.rabi_parameters[f].update_file(temp_df)
    # ------------------------------------------------------

    # x = nuclear.data.df['mw_duration'].unique()
    # y = nuclear.data.df.groupby(by = ['mw_duration']).agg({'average_counts': np.mean}).values
    
    # T = nuclear.pld.fit_result_table.data['T'] #RabiPeriod
    # pi3d.tt.rabi_parameters[f].update_file(sub)  ## where sub is dataframe
    # nuclear.pld.data_fit_results.df
    # data_dict={
    #     'mw_durations' : x,
    #     'average_counts':y,
    #     'omega' : 1.0/T,
    #     # amp0    transition    omega    date
    
    # }
    # print('-----------')
    # print('x: ')
    # print(x)
    # print('y: ')
    # print(y)
    # print('-----------')