from __future__ import print_function, absolute_import, division
import importlib
#import hardware.Keysight_AWG_M8190.pym8190a as MCAS #; importlib.reload(MCAS)
import qudi.notebooks.UserScripts.helpers.sequence_creation_helpers as sch; importlib.reload(sch)

from traits.api import *
import numpy as np
import qudi.logic.mcas.elements as E
from qudi.logic.qudip_enhanced import *

import qudi.logic.misc as misc

import qudi.notebooks.UserScripts.helpers.shared as shared
import numbers

import collections

__CURRENT_POL_RED__ = 76
__T_POL_RED__ = 0.2
__RED_LASER__DELAY__ = 0.1
__SSR_REPETITIONS__ = {'14n+1': 1500, '14n-1': 1500, '14n': 1500, '14n0': 1200, '13c414': 1500, '13c90': 2000, '13c5000': 10,
                       'charge_state':1,'charge_state_A1_aom_Ex':1,
                       'charge_state_ExMW':1,
                       'ple_A2': 1,
                       'ple_A1': 1,
                       'ple_A2_delay': 1,
                       'ple_A1_delay': 1,
                       'Ex_pi_readout':1,
                       'Ex_pi_readout_6ns':1,
                       'Ex_ampl_sweep_SSR' : 1,
                       'opt_mw_delays_calibration':1,
                       'opt_mw_delays_calibration2': 1,
                        '2_opt_mw_delays_calibration':1,
                       'Ex_RO':1,
                        '2opt_withMW_pi':1,
                       'entanglement_for_tests':1,
                        'HOM':1,
                        'entanglement':1,
                       'Ex_ampl_sweep_SSR_6ns' :10,
                       'Ex_pi_readout_10ns':10}
__LASER_DUR_DICT__ = {'14n+1': .175, 
                     '14n-1': .175, '14n': .175, 
                     '14n0': .9, 
                     '13c414': .9, 
                     '13c90': .21,
                     '29Si8_A2': 5.,
                     '13c5000_A2': 5.,
                     '13c5000': 5.,
                    'single_state': .9, 
                      'charge_state': 500.0,
                      'charge_state_ExMW': 2000.0,
                      'charge_state_A1_aom_Ex':2000.0,
                      'ple_A2': 50.0,
                      'ple_A1': 50.,
                      'Ex_pi_readout_6ns' : 481*3/12.0e3, # (Len in samples / sampling rate)
                      'Ex_ampl_sweep_SSR' : 481*1/12e3,
                      'opt_mw_delays_calibration': 481*1/12e3,
                      'opt_mw_delays_calibration2': 481 * 1 / 12e3,
                      '2_opt_mw_delays_calibration': 481 * 1 / 12e3,
                      'Ex_RO': 5.0,
                      '2opt_withMW_pi':481*1/12e3,
                      'entanglement_for_tests':481*1/12e3,
                        'HOM':481*1/12e3,
                      'entanglement':481*1/12e3,
                      'Ex_ampl_sweep_SSR_6ns' : 481*3/12e3,
                      'Ex_pi_readout_10ns' : 481*5/12.0e3,
                        'Ex_pi_readout' : 481/12.0e3 # (Len in samples / sampling rate)
                      } # us
__PERIODS__ = {'14n+1': 1.6, '14n-1': 1.6, '29Si8_A2':1.0, '13c5000_A2':1.0, '14n': 1.6,  '14n0': 1.6, '13c414': 6.0, '13c90': 20., 'charge_state': 0.0,'charge_state_A1_aom_Ex': 0.0,
               'charge_state_ExMW': 0.0,'ple_A2': 0.0,'ple_A1': 0.0,'ple_A2_delay': 0.0,'ple_A1_delay': 0.0,'Ex_pi_readout':0.0,'Ex_pi_readout_6ns':0.0,'Ex_ampl_sweep_SSR' :0.0,
               'Ex_ampl_sweep_SSR_6ns' :0.0, 'Ex_pi_readout_10ns':0.0,'opt_mw_delays_calibration':0.0,
               'opt_mw_delays_calibration2':0.0,'2_opt_mw_delays_calibration':0.0,'Ex_RO':0.0,
               '2opt_withMW_pi':0.0,'entanglement':0.0,'entanglement_for_tests':0.0,'HOM':0.0}
__WAVE_FILE_SCALING_FACTOR_DICT__ = {'14n+1': 2.5, '14n-1': 2.5, '14n': 2.5, '14n0': 2.5, '13c414': 1.0, '13c5000': 1.0,'charge_state_A1_aom_Ex':1.0, 'charge_state': 1.0,'ple_A2': 1.0,'ple_A1': 0.0}
__STANDARD_WAVEFILE__ = 'D:\data\Robust_Pulses\single_pulse_ON03_OFF05_Rabi10_02.dat'
__STANDARD_WAVEFILES__ = {'14n+1': r"D:\data\NuclearOPs\Robust\test_pi_three_nitrogen\20171204-h18m52s32CnROTe-gateFN3.08e-01_selective_to_all\MW.dat"}

__WAIT_SWITCH__ = 0.0
__IQ_MIXER__ = False
__TT_TRIGGER_LENGTH__ = 0.064#10*192/12e3
__SAMPLE_FREQUENCY__ = 12e3

def nuclear_rabi(mcas, new_segment=False, **kwargs):
    type = 'robust' if 'wave_file' in kwargs else 'sinehermite'
    if new_segment:
        mcas.start_new_segment(name='nuclear_rabi')
    if 'pd128m' in kwargs:
        raise Exception('Error!')
    pd = {}
    for awg_str, chl in mcas.ch_dict.items():
        for ch in chl:
            if 'pd' + awg_str + str(ch) in kwargs:
                pd['pd' + awg_str + str(ch)] = kwargs.pop('pd' + awg_str + str(ch), None)
    mcas.asc(pd2g2=dict(type=type, **kwargs), name=kwargs.get('name', 'rf'), **pd)

def electron_pi_and_rf_on(mcas, new_segment = False,iq_mixer=__IQ_MIXER__, **allkwargs):
    """
    Should be similar to electron rabi but with RF on....
    :param mcas:
    :param new_segment:
    :param kwargs:
    :return:
    """
    kwargs = allkwargs['d2g']
    rfkwargs = allkwargs['d128m']
    type_mw = 'robust' if 'wave_file' in kwargs else 'sinehermite'
    type_rf = 'sine'
    if new_segment:
        mcas.start_new_segment(name='Electron Rabi with RF')
    pd = {}
    for awg_str, chl in mcas.ch_dict.items():
        for ch in chl:
            if 'pd' + awg_str + str(ch) in kwargs:
                pd['pd' + awg_str + str(ch)] = kwargs.pop('pd' + awg_str + str(ch), None)
    if kwargs['mixer_deg'] is None:
        raise Exception('Error: mixer_deg must be given.')
    elif isinstance(kwargs['mixer_deg'], (list, np.ndarray)):
        if len(kwargs['mixer_deg']) != len(kwargs['frequencies']):
            raise Exception
        else:
            mixer_deg = np.array(kwargs['mixer_deg'])
    elif isinstance(kwargs['mixer_deg'], (int, float, complex)):
        kwargs['mixer_deg'] = np.array([kwargs['mixer_deg']])
    else:
        raise Exception
    if 'phases' in kwargs:
        if isinstance(kwargs['phases'], (np.ndarray, list)):
            if len(kwargs['phases']) != len(kwargs['frequencies']):
                raise Exception
            kwargs['phases'] = np.array(kwargs['phases'])
        elif isinstance(kwargs['phases'], (int, float, complex)):
            kwargs['phases'] = np.array([kwargs['phases']])
    else:
        kwargs['phases'] = np.zeros(len(kwargs['frequencies']))
    ch_list = [1, 2] if iq_mixer else [1]
    pd2g = dict([(ch, dict(type=type_mw, **kwargs)) for ch in ch_list])
    if iq_mixer:
        pd2g[2]['phases'] = np.array(pd2g[2]['phases']) + kwargs['mixer_deg']
        pd2g[2]['smpl_marker'] = False
        pd128ml = dict(type=type_rf, **rfkwargs)
        mcas.asc(pd2g1=pd2g[1], pd2g2=pd2g[2],pd128m1=pd128ml, name=kwargs.get('name', 'mw+rf'), **pd)
    else:
        mcas.asc(pd2g1=pd2g[1], name=kwargs.get('name', 'mw+rf'), **pd)

def electron_rabi(mcas, name='e_rabi', iq_mixer=__IQ_MIXER__, mixer_deg=-90, new_segment=False, pulseshape = 'sine', **kwargs):
    #print(kwargs)
    """
    :param transition: addressed transition in ODMR, i.e. 'left' or 'right', just like in TransitionTracker
    """
    if new_segment:
        mcas.start_new_segment(name='electron_rabi')
    type = 'robust' if 'wave_file' in kwargs else pulseshape
    if 'pd2g1' in kwargs or 'pd2g2' in kwargs:
        raise Exception('Error!')
    pd = {}
    
    for awg_str, chl in mcas.ch_dict.items():
        for ch in chl:
            if 'pd' + awg_str + str(ch) in kwargs:
                pd['pd' + awg_str + str(ch)] = kwargs.pop('pd' + awg_str + str(ch), None)
    
    if mixer_deg is None:
        raise Exception('Error: mixer_deg must be given.')
    elif isinstance(mixer_deg, (list, np.ndarray)):
        if len(mixer_deg) != len(kwargs['frequencies']):
            raise Exception
        else:
            mixer_deg = np.array(mixer_deg)
    elif isinstance(mixer_deg, (int, int, float, complex)):
        mixer_deg = np.array([mixer_deg])
    else:
        raise Exception

    if 'phases' in kwargs:
        if isinstance(kwargs['phases'], (np.ndarray, list)):
            if len(kwargs['phases']) != len(kwargs['frequencies']):
                raise Exception
            kwargs['phases'] = np.array(kwargs['phases'])
        elif isinstance(kwargs['phases'], (int, int, float, complex)):
            kwargs['phases'] = np.array([kwargs['phases']])
    else:
        kwargs['phases'] = np.zeros(len(kwargs['frequencies']))
    ch_list = [1, 2] if iq_mixer else [1]
    pd2g = dict([(ch, dict(type=type, **kwargs)) for ch in ch_list])
    if iq_mixer:
        pd2g[2]['phases'] = np.array(pd2g[2]['phases']) + mixer_deg
        pd2g[2]['smpl_marker'] = False
        mcas.asc(pd2g1=pd2g[1], pd2g2=pd2g[2], name=name, **pd, **kwargs) #UNFUG
        #mcas.asc(pd2g1=pd2g[1], pd2g2=pd2g[2], name=name, **pd) #MW is set here
    else:
        mcas.asc(pd2g1=pd2g[1], name=name, **pd, **kwargs)#UNFUG
        #mcas.asc(pd2g1=pd2g[1], name=name, **pd)

def electron_rabi_parabol(mcas, name='e_rabi', iq_mixer=__IQ_MIXER__, mixer_deg=-90, new_segment=False, **kwargs):

    """
    :param transition: addressed transition in ODMR, i.e. 'left' or 'right', just like in TransitionTracker
    """
    if new_segment:
        mcas.start_new_segment(name='electron_rabi')
    type = 'robust' if 'wave_file' in kwargs else 'sineparabol'
    if 'pd2g1' in kwargs or 'pd2g2' in kwargs:
        raise Exception('Error!')
    pd = {}
    
    for awg_str, chl in mcas.ch_dict.items():
        for ch in chl:
            if 'pd' + awg_str + str(ch) in kwargs:
                pd['pd' + awg_str + str(ch)] = kwargs.pop('pd' + awg_str + str(ch), None)
    
    if mixer_deg is None:
        raise Exception('Error: mixer_deg must be given.')
    elif isinstance(mixer_deg, (list, np.ndarray)):
        if len(mixer_deg) != len(kwargs['frequencies']):
            raise Exception
        else:
            mixer_deg = np.array(mixer_deg)
    elif isinstance(mixer_deg, (int, int, float, complex)):
        mixer_deg = np.array([mixer_deg])
    else:
        raise Exception

    if 'phases' in kwargs:
        if isinstance(kwargs['phases'], (np.ndarray, list)):
            if len(kwargs['phases']) != len(kwargs['frequencies']):
                raise Exception
            kwargs['phases'] = np.array(kwargs['phases'])
        elif isinstance(kwargs['phases'], (int, int, float, complex)):
            kwargs['phases'] = np.array([kwargs['phases']])
    else:
        kwargs['phases'] = np.zeros(len(kwargs['frequencies']))
    ch_list = [1, 2] if iq_mixer else [1]
    pd2g = dict([(ch, dict(type=type, **kwargs)) for ch in ch_list])
    if iq_mixer:
        pd2g[2]['phases'] = np.array(pd2g[2]['phases']) + mixer_deg
        pd2g[2]['smpl_marker'] = False
        mcas.asc(pd2g1=pd2g[1], pd2g2=pd2g[2], name=name, **pd, **kwargs) #UNFUG
        #mcas.asc(pd2g1=pd2g[1], pd2g2=pd2g[2], name=name, **pd) #MW is set here
    else:
        mcas.asc(pd2g1=pd2g[1], name=name, **pd, **kwargs)#UNFUG
        #mcas.asc(pd2g1=pd2g[1], name=name, **pd)

def set_init_seq(mcas, state, init_time = 10, segment_length = 1, **kwargs):
    pd2g1 = kwargs.pop("pd2g1").copy() # Need to copy to circumvent using the same pd twice, because pd gets changed in asc.
    loops, correction_mus = shared.calculate_loop_count(init_time,segment_length)

    # main loop
    mcas.start_new_segment(name='init', loop_count = loops)
    mcas.asc(**kwargs, length_mus = segment_length) 
    
    # correction segment
    mcas.start_new_segment(name='init', loop_count = 1)
    if correction_mus >= 0.128: correction_mus = correction_mus-0.128
    mcas.asc(**kwargs, length_mus = correction_mus)

    # Turning of gateMW
    gateMW = False
    mcas.asc(**kwargs, length_mus = correction_mus)

def init_state_drive(state,freqs, max_amp):
    '''
    State could be "+(-)0(1).5", example "+1.5" or "-0.5".
    '''
    transitions_num = len(freqs)
    zeros = np.zeros(transitions_num // 2)
    ones = np.ones(transitions_num // 2)
    amplitude = min(0.99 / transitions_num,max_amp)
    if '+' in state:
        amps=np.append(ones * amplitude, zeros)
    elif '-' in state:
        amps=np.append(zeros, ones * amplitude)
    pd2g1 = {
        'type': 'sinehermite',
        'phases': [0], #*transitions_num ?
        'amplitudes': amps,        
        'frequencies': freqs
    }
    
    return pd2g1

def electron_init(mcas, state, dur, freqs_all_L, freqs_all_R, segment_length = 10, max_amp = 0.5, newsegment = True):
    '''
    State could be "+(-)0(1).5", example "+1.5" or "-0.5".
    Duration (µs) will be used to calculate loop_count (int) depending on segment_length (10µs standard).
    Duration which doesn't fit into >> loop_counts * segment_length << will be corrected for at the end.
    Initialization segment ends with 1024ns of decay to ensure all lasers are off.
    '''
    state = state.replace('p', '+').replace('m', '-').replace('32', '1.5').replace('12', '0.5').replace('3/2', '1.5').replace('1/2', '0.5')
    if newsegment:
        loops, correction_mus  = shared.calculate_loop_count(dur,segment_length)
        if loops!=0:
            mcas.start_new_segment(name='init', loop_count = loops)
            mcas.asc(
                A1= '1.5' in state,
                A2 = '0.5' in state,
                laser = True,
                gateMW = True,
                length_mus=E.round_length_mus_to_x_multiple_ps(segment_length), 
                name='resonant_init',
                pd2g1 = init_state_drive(state, np.append(freqs_all_L, freqs_all_R), max_amp)
            ) 
        mcas.start_new_segment(name='init_correction', loop_count = 1)
        mcas.asc(
            A1= '1.5' in state,
            A2 = '0.5' in state,
            laser = True,
            gateMW = True,
            length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus), 
            name='resonant_init',
            pd2g1 = init_state_drive(state, np.append(freqs_all_L, freqs_all_R), max_amp)
        ) 
    else:
        mcas.asc(
        A1= '1.5' in state,
        A2 = '0.5' in state,
        laser = True,
        gateMW = True,
        length_mus=E.round_length_mus_to_x_multiple_ps(dur), 
        name='resonant_init',
        pd2g1 = init_state_drive(state, np.append(freqs_all_L, freqs_all_R), max_amp)
    ) 
    mcas.asc(
        A1= '1.5' in state,
        A2 = '0.5' in state,
        laser = True,
        length_mus=E.round_length_mus_to_x_multiple_ps(1.024), 
        name='resonant_init',
    ) 
    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.512), name = 'Init Decay')  

def repump(mcas, dur):
    mcas.start_new_segment('Repump', loop_count = 5)
    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(dur/5,64), repump=True, name='Repump')
    mcas.start_new_segment('Decay', loop_count = 1)
    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1.0,64), name='RepumpDecay')


# def single_robust_electron_pi(mcas, nuc, **kwargs):
#     if 'mixer_deg' in kwargs:
#         raise Exception('Error: mixer_deg can not be set manually.')
#     nuc = nuc.replace('14N', '14n').replace('13C', '13c')
#     if nuc in ['14n+1', '14n-1', '14n', '13c414']:
#         wave_file = WaveFile(filepath=__STANDARD_WAVEFILE__,
#                              rp=pi3d.tt.rabi_parameters['e_rabi_ou{:.0f}deg-90'.format(pi3d.awgs['2g'].ch[1].output_amplitude*1000)],
#                              scaling_factor=__WAVE_FILE_SCALING_FACTOR_DICT__[nuc])
#         kwargs['wave_file'] = wave_file
#         kwargs['mixer_deg'] = -90
#     elif nuc == 'all': #flip electron independently of nuclear spin state
#         max_rabi_file = 'e_rabi_ou{:.0f}deg-90'.format(pi3d.awgs['2g'].ch[1].output_amplitude*1000)
#         # if pi3d.tt.rp(max_rabi_file, amp=1.0).omega > 15.:
#         kwargs['length_mus'] = pi3d.tt.rp(max_rabi_file, amp=1.0).pi
#         kwargs['amplitudes'] = [1.0]
#         kwargs['mixer_deg'] = -90
#         # else:
#         #     wave_file = WaveFile(filepath='D:/Python/pi3diamond/UserScripts/Robust/test_pi_three_nitrogen/p4.dat',
#         #                          rp=pi3d.tt.rabi_parameters['e_rabi_ou{:.0f}deg-90'.format(pi3d.awgs['2g'].ch[1].output_amplitude*1000)],
#         #                          )
#         #     kwargs['wave_file'] = wave_file
#         #     kwargs['mixer_deg'] = -90
#     else:
#         raise Exception('Nuc does not exist!')
#     electron_rabi(mcas, **kwargs)

def polarize_red(mcas, new_segment=False, length_mus=__T_POL_RED__, red_laserdelay =__RED_LASER__DELAY__, **kwargs):
    if new_segment:
        mcas.start_new_segment(name='polarize')
    pd = {}
    for awg_str, chl in mcas.ch_dict.items():
        for ch in chl:
            if 'pd' + awg_str + str(ch) in kwargs:
                if not awg_str in pd:
                    pd[awg_str] = {}
                pd[awg_str][ch] = kwargs.pop('pd' + awg_str + str(ch))
    # print('Polarize Red New')
    mcas.asc(length_mus=length_mus, name='polarize', aom_A1=True, **pd)
    mcas.asc(length_mus=red_laserdelay, name='red_laserdelay', **pd)
    mcas.asc(length_mus=1.5, name='wait_cts', **pd)

def polarize_green(mcas, new_segment=False, length_mus=0.2, laser_delay=0.1, **kwargs):
    if new_segment:
        mcas.start_new_segment(name='polarize')
    pd = {}
    for awg_str, chl in mcas.ch_dict.items():
        for ch in chl:
            if 'pd' + awg_str + str(ch) in kwargs:
                if not awg_str in pd:
                    pd[awg_str] = {}
                pd[awg_str][ch] = kwargs.pop('pd' + awg_str + str(ch))
    mcas.asc(length_mus=length_mus, name='polarize', green=True, **pd)
    mcas.asc(length_mus=laser_delay, name='laserdelay', **pd)
    mcas.asc(length_mus=1.5, name='wait_cts', **pd)

polarize = polarize_red

# def init_13c(mcas, s='90', state='left', new_segment=False, waitmwrf=0.5, rotation_angles=None, **pd):
#     rotation_angles = [np.pi] if rotation_angles is None else rotation_angles
#     if state in {'+', '-'}: #only true for ms-1
#         state = {'-': 'left', '+': 'right'}[state]
#     if new_segment:
#         mcas.start_new_segment(name='init_13c' + s)
#     polarize(mcas=mcas, new_segment=False, **pd)
#     mcas.asc(length_mus=waitmwrf, name='waitmwrf', **pd)
#     if s == '414':
#         single_robust_electron_pi(
#             mcas,
#             nuc='13c{}'.format(s),
#             frequencies=pi3d.tt.mfl("13c{}_{}".format(s, {'left': 'right', 'right': 'left'}[state])),
#         )
#         mcas.asc(length_mus=waitmwrf, name='waitmwrf', **pd)
#     elif s == '90':
#         period = 40.
#         electron_rabi(mcas,
#                       length_mus=0.5*period,
#                       amplitudes=[pi3d.tt.rp('e_rabi_ou{:.0f}deg-90'.format(1000*pi3d.awgs['2g'].ch[1].output_amplitude), period=period).amp],
#                       frequencies=pi3d.tt.mfl("13c{}_{}".format(s, {'left': 'right', 'right': 'left'}[state])),
#                       new_segment=False,
#                       mixer_deg=-90,
#                       **pd
#                       )
#         mcas.asc(length_mus=waitmwrf, name='waitmwrf', **pd)
#     else:
#         raise Exception('Nuc does not exist!')
#     transition = "13c{} mS-1".format(s)
#     try:
#         amp = pi3d.tt.rp(transition, period=100.).amp
#     except:
#         amp = 1.
#     nuclear_rabi(mcas,
#                  length_mus=pym8190a.elements.round_length_mus_full_sample(pi3d.tt.rp(transition, amp=amp).pi*rotation_angles[0]/np.pi),
#                  amplitudes=[amp],
#                  name=transition,
#                  new_segment=False,
#                  frequencies=[pi3d.tt.t(transition).current_frequency],
#                  **pd)
#     mcas.asc(length_mus=waitmwrf, name='waitmwrf', **pd)

# init_13C = init_13c

# def init_14n(mcas, mn='+1', new_segment=False, waitmwrf=0.5, rotation_angles=None, **pd):
#     rotation_angles = [np.pi, np.pi] if rotation_angles is None else rotation_angles
#     if mn == '+':
#         mn = '+1'
#     if mn == '-':
#         mn = '-1'
#     if isinstance(mn, numbers.Number):
#         mn = "{:+d}".format(mn)
#     if mn == "+0":
#         mn = "0"
#     s = [
#         dict(
#             e={'+1': '0', '0': '0', '-1': '0'},
#             n={'+1': '-1', '0': '-1', '-1': '+1'}
#         ),
#         dict(
#             e={'+1': '+1', '0': '0', '-1': '-1'},
#             n={'+1': '+1', '0': '+1', '-1': '-1'}
#         )
#     ]
#     if new_segment:
#         mcas.start_new_segment(name='init_14n' + mn)
#     for idx, ss in enumerate(s):
#         if rotation_angles[idx] > 0.0:
#             polarize(mcas, new_segment=False, **pd)
#             mcas.asc(length_mus=waitmwrf, name='waitmwrf', **pd)
#             single_robust_electron_pi(mcas, frequencies=pi3d.tt.mfl({'14n': [int(ss['e'][mn])]}), nuc='14n', new_segment=False, **pd)
#             mcas.asc(length_mus=waitmwrf, name='waitmwrf', **pd)
#             try:
#                 amp = pi3d.tt.rp(transition, period=100.).amp
#             except:
#                 amp = 1.0
#             transition = '14n{} mS0'.format(ss['n'][mn])
#             nuclear_rabi(mcas,
#                          amplitudes=[amp],
#                          length_mus=pym8190a.elements.round_length_mus_full_sample(pi3d.tt.rp(transition, amp=amp).pi*rotation_angles[idx]/np.pi),
#                          name=transition,
#                          frequencies=[pi3d.tt.t(transition).current_frequency],
#                          new_segment=False,
#                          **pd)
#             mcas.asc(length_mus=waitmwrf, name='waitmwrf', **pd)


# init_14N = init_14n


# def init(mcas, nuc, n=1, **kwargs):
#     nuc = nuc.replace('14N', '14n').replace('13C', '13c')
#     sms = sch.ret_sms(nuc=nuc)
#     if '13c' in nuc:
#         initf = init_13c
#     elif '14n' in nuc:
#         initf = init_14n
#     else:
#         raise Exception('Nuc {} not found'.format(nuc))
#     for i in range(n):
#         initf(mcas, sms['s'], **kwargs)


# def init_multiple(mcas, init_14n='not', init_13c414='not', init_13c90='not', ssr_repetitions=450, number_of_frequencies=1, **kwargs):
#     mn_14n = [+1, 0, -1] if init_14n is "not" else [int(init_14n)]
#     mn_13c414 = [+.5, -.5] if init_13c414 is "not" else [.5 * int("{}1".format(init_13c414))]
#     mn_13c90 = [+.5, -.5] if init_13c90 is "not" else [.5 * int("{}1".format(init_13c90))]
#     nuc = None
#     if init_13c90 != 'not':
#         nuc = '13c90'
#         init_13c(mcas, s='90', state=init_13c90, new_segment=True)
#         frequencies = pi3d.tt.mfl({'14N': mn_14n, '13c414': mn_13c414, '13c90': mn_13c90})
#     if init_13c414 != 'not':
#         init_13c(mcas, s='414', state=init_13c414, new_segment=True)
#         if nuc is None:
#             nuc = '13c414'
#             frequencies = pi3d.tt.mfl({'14N': mn_14n, '13c414': mn_13c414})
#     if init_14n != 'not':
#         init_14N(mcas, mn=init_14n, new_segment=True)
#         if nuc is None:
#             nuc = '14n'
#             frequencies = pi3d.tt.mfl({'14N': mn_14n})
#     if number_of_frequencies == 1:
#         ssr(mcas, frequencies=frequencies, nuc=nuc, robust=True, repetitions=ssr_repetitions, mixer_deg=-90, **kwargs)
#     elif number_of_frequencies == 2:
#         frequencies_not = pi3d.tt.mfl({'14n': [+1, 0, -1], '13c414': [+.5, -.5], '13c90': [+.5, -.5]})
#         frequencies_not = np.delete(frequencies_not, np.argwhere(frequencies_not == frequencies[0])[0, 0])
#         ssr(mcas, frequencies=[frequencies, frequencies_not], nuc='13c90', robust=True, repetitions=ssr_repetitions, mixer_deg=-90, **kwargs)

# def make_csd(mcas, ms='-1', mn='+1', e_amp=.05, robust=False):
#     mcas.start_new_segment(name='csd')
#     polarize(mcas)
#     frequencies = pi3d.tt.mfl({'14n': [int(mn)], '13c414': [-0.5], '13c90': [-0.5]})
#     if ms == '-1':
#         # electron pi to ms-1
#         if robust is True:
#             rpd = dict(wave_file='D:/data/Robust_Pulses/Pi-20130222T131525_YaWang.dat',
#                        er2d=TransitionTracker.ElectronRabi2d(lr='left'),
#                        wave_file_nonlinear_rabi=True)
#             mcas.asc(wos='wave', name='robust_pi', pd2g1=dict(frequencies=frequencies, type='robust', rpd=rpd))
#         else:
#             # amp = 0.05  # nuclei are initialized, high power does no harm
#             # amp = 0.2
#             electron_rabi(mcas, wos='wave', frequencies=frequencies, amplitudes=[e_amp], length_mus=pi3d.tt.rp('e_rabi_left', amp=e_amp).pi)
#     # nuclear pi on 14n
#     transition = "14n{} mS{}".format(mn, ms)
#     amp_t = pi3d.tt.rp(transition, period=100.).amp
#     amp = amp_t if amp_t <= 1.0 else 1.0
#     nuclear_rabi(mcas,
#                  name=transition,
#                  amplitudes=[amp],
#                  frequencies=[pi3d.tt.t(transition).current_frequency],
#                  length_mus=pi3d.tt.rp(transition, amp=amp).pi
#                  )


class SSR(object):

    __ALTERNATING_REPETITIONS__ = 1
    __LENGTH_MUS_FINAL_WAIT__ = 0.1
    __TRANSITION__ = 'left'
    __ADVANCE_MODE__ = 'AUTO'
    __ROBUST__ = False
    __GATE_OR_TRIGGER__ = 'trigger'
    # __WAIT_DARK_COUNTS__ = 10*192 #5*1920

    def __init__(self, mcas, queue, frequencies, wait_dur=1.,protected_readout=False, **kwargs):
        super(SSR, self).__init__()

        if 'nuc' in kwargs and kwargs['nuc'] is not None:
            kwargs['nuc'] = kwargs['nuc'].replace('29Si', '29si').replace('13C', '13c')
        self.queue = queue
        self.mcas = mcas
        self.frequencies = frequencies
        self.gate_or_trigger = kwargs.get('gate_or_trigger', self.__GATE_OR_TRIGGER__)
        self.set_laser_dur(kwargs)
        self.iq_mixer = kwargs.get('iq_mixer', __IQ_MIXER__)
        self.set_transition(kwargs)
        self.wait_dur = wait_dur
        self.check_kwargs_validity(kwargs)
        self.set_mixer_deg(kwargs)
        self.set_rp(kwargs)
        self.set_robust(kwargs)
        self.set_wave_file_kwargs(kwargs)
        self.set_length_mus_mw(kwargs)
        self.set_repetitions(kwargs)
        self.set_name(kwargs)
        self.set_amplitudes(kwargs)
        self.advance_mode = kwargs.get('advance_mode', self.__ADVANCE_MODE__)
        self.set_final_wait(kwargs)
        self.set_dur_step()
        self.kwargs = kwargs
        self.protected_readout=protected_readout

    laser_dur = misc.ret_property_typecheck('laser_dur', float)
    wait_dur = misc.ret_property_typecheck('wait_dur', float)
    rabi_file = misc.ret_property_typecheck('rabi_file', str)

    def check_kwargs_validity(self, kwargs):
        if 'robust' in  kwargs and kwargs['robust']:
            if ('length_mus_mw' in kwargs or 'amplitudes' in kwargs):
                raise Exception("When 'robust' is True, neither 'length_mus_mw' nor 'amplitudes' must be given.")
        elif 'wave_file' in kwargs:
                raise Exception("'wave_file' is not None but 'robust' is False")
        if 'amplitudes' in kwargs and 'rabi_file' in kwargs:
            raise Exception("Either parameter 'amplitudes' or give parameter 'rabi_file' can be given.")
        if not 'nuc' in kwargs and not 'repetitions' in kwargs:
            raise Exception("At least one out of parameters ['nuc','repetitions'] must be given.")

    @property
    def frequencies(self):
        return self._frequencies

    @frequencies.setter
    def frequencies(self, val):
        if type(val) in [list, np.ndarray]:
            for i in val:
                if all([isinstance(i, numbers.Number) for i in val]):
                    self._frequencies = [val]
                elif all([isinstance(i, list) or isinstance(i, np.ndarray)]):
                    self._frequencies = val
                else:
                    raise Exception('SSR._frequencies must be a list of (list, numpy.ndarray) of numbers. If you pass a (list, np.ndarray) of numbers. this will be converted.')
        else:
            raise Exception('frequencies must be an numpy array or a list.')

    @property
    def number_of_alternating_steps(self):
        return len(self.frequencies)

    def set_robust(self, kwargs):
        self.robust = kwargs.get('robust', self.__ROBUST__)
        if kwargs.get('nuc', None) == '13c90' and self.robust and not 'wave_file_kwargs' in kwargs:
            self.robust = False

    def set_mixer_deg(self, kwargs):
        if 'mixer_deg' not in kwargs:
            raise Exception('Error: mixer_deg must be given.')
        self.mixer_deg = kwargs['mixer_deg']

    def set_laser_dur(self, kwargs):
        if 'laser_dur' in kwargs:
            self.laser_dur = kwargs['laser_dur']
        else:
            self.laser_dur = __LASER_DUR_DICT__[kwargs['nuc']]

    def set_rp(self, kwargs):

        if 'rp' in kwargs:
            self.rp = kwargs['rp']

        elif 'mixer_deg' in kwargs:
            if 'ms_transition' in kwargs.keys():
                ms_transition = {'right': 'R', 'left': 'L', 'center': 'C'}[kwargs['ms_transition']]
            else:
                ms_transition = 'L'

            self.rp = self.queue.tt.rabi_parameters['e_rabi_ou{:.0f}deg{}-{}'.format(
                self.queue._awg.mcas_dict.awgs['2g'].ch[1].output_amplitude*1000, #TODO
                self.mixer_deg,
                ms_transition
            )]
        else:
            raise Exception('TransitionTracker.RabiParametersStatic or mixer_deg instance must be given.')

    def set_wave_file_kwargs(self, kwargs):
        if self.robust:
            if 'wave_file_kwargs' in kwargs:
                if isinstance(kwargs['wave_file_kwargs'], list) and len(kwargs['wave_file_kwargs']) == self.number_of_alternating_steps:
                    self.wave_file_kwargs = kwargs['wave_file_kwargs']
                elif self.number_of_alternating_steps == 1 and isinstance(kwargs['wave_file_kwargs'], dict):
                    self.wave_file_kwargs = [kwargs['wave_file_kwargs']]
                else:
                    raise Exception('Error: {}'.format(kwargs))
            else:
                fp = kwargs.get('wave_file_filepath', __STANDARD_WAVEFILE__)
                if 'nuc' in kwargs:
                    sf = __WAVE_FILE_SCALING_FACTOR_DICT__[kwargs['nuc']]
                else:
                    sf = kwargs.get('wave_file_scaling_factor', 1.0)
                self.wave_file_kwargs = [dict(filepath=fp, rp=self.rp, scaling_factor=sf) for i in range(self.number_of_alternating_steps)]
            self.wave_file = [E.WaveFile(**i) for i in self.wave_file_kwargs]

    def set_length_mus_mw(self, kwargs):
        if self.robust:
            self.length_mus_mw = [self.wave_file[n].length_mus for n in range(self.number_of_alternating_steps)]
            self.mw_step_length_mus = [self.wave_file[n].step_length_mus for n in range(self.number_of_alternating_steps)]
        else:
            self.length_mus_mw = kwargs['length_mus_mw'] if 'length_mus_mw' in kwargs else [__PERIODS__[kwargs['nuc']]/2.]*self.number_of_alternating_steps
            if 'pi_pulse_factor' in kwargs:
                self.length_mus_mw *= kwargs['pi_pulse_factor']
            if not hasattr(self.length_mus_mw, '__iter__'):
                self.length_mus_mw = [self.length_mus_mw]*self.number_of_alternating_steps
            if len(self.length_mus_mw) != self.number_of_alternating_steps:
                raise Exception('Wrong number of length_mus_mw. Allowed is 1 or number_of_alternating_steps')

    @property
    def alternating(self):
        return True if self.number_of_alternating_steps > 1 else False

    def set_repetitions(self, kwargs):
        r = kwargs['repetitions'] if 'repetitions' in kwargs else __SSR_REPETITIONS__[kwargs['nuc']]
        if int(r) != r:
            raise Exception('repetititons is not an integer')
        if self.alternating:
            if r%self.number_of_alternating_steps != 0:
                raise Exception('Repetitions must be divisible by number_of_alternating_steps.', kwargs['repetitions'], self.number_of_alternating_steps)
            else:
                self.repetitions = int(r/self.number_of_alternating_steps)
        else:
            self.repetitions = r
        if self.repetitions == 0:
            print('Something went wrong with your ssr repetitions! {}'.format(self.repetitions))

    def set_name(self, kwargs):
        if 'name' in kwargs:
            self.name = kwargs['name']
        elif 'nuc' in kwargs:
            self.name = 'ssr' + kwargs['nuc']
        else:
            self.name = 'ssrt{}'.format("t".join("{:.2f}".format(i) for i in self.length_mus_mw))

    def set_amplitudes(self, kwargs):
        if not self.robust:
            if 'amplitudes' in kwargs:
                amps = kwargs['amplitudes']
                if isinstance(amps,list):
                    if isinstance(amps[0],list) or isinstance(amps[0],np.ndarray):
                        self.amplitudes = kwargs['amplitudes']            
                    else:
                        self.amplitudes = [kwargs['amplitudes'] for i in self.length_mus_mw] # basically for eawch length mus there will be an iteration?
                else:
                    self.amplitudes = [[kwargs['amplitudes']] for i in self.length_mus_mw] # basically for eawch length mus there will be an iteration?
                #print('SSR MW amps: ', self.amplitudes,'SSR MW dur: ', self.length_mus_mw)

            else:# 'amplitudes' not in kwargs or None in np.array(self.amplitudes).flatten():
                if any(np.array(self.length_mus_mw) == 0): # Implemented here in order to charge state control
                    self.amplitudes = [[0] for i in self.length_mus_mw]
                else:
                    # self.amplitudes = [self.rp.amplitude(tni={'left': [0], 'right': [1]}[self.transition], period=[2*i]) for i in self.length_mus_mw]
                    # Right or left transition has already been taken into account by chosing proper self.rp initialization file
                    self.amplitudes = [self.rp.amplitude(tni=[0], period=[2*i]) for i in self.length_mus_mw]

    def set_transition(self, kwargs):
        t = kwargs.get('transition', self.__TRANSITION__).replace('14N', '14n').replace('13C', '13c').replace('mS', 'ms')
        if t not in ['left', 'right']:
            raise Exception('Error {}, {}'.format(t, kwargs['transition']))
        self.transition = t

    def set_final_wait(self, kwargs):
        self.final_wait = kwargs.get('final_wait', 0.1)
        if self.final_wait == 0.0 and self.alternating:
            raise Exception("When alternating is True, final_wait must not be False. (I AM NOT SURE IF THIS IS TRUE FOR TIMETAGGER AS COUNTER)")

    def set_dur_step(self):
        self.dur_step = [
            {
             2: self.length_mus_mw[n], # CNOT 38
             #3: self.length_mus_mw[n], # CNOT 177
             5: self.laser_dur,
             6: self.wait_dur} for n in range(self.number_of_alternating_steps)]

    def part_step(self, n):
        t = np.cumsum([0.0, self.dur_step[n][2]])
        return {
            2: self.wave_file[n].ret_part(t[0], t[1]),
        }


    def pd2g_dict(self, n):
        if n > len(self.frequencies) - 1:
            raise Exception('Not enough frequencies given.')

        pd2g_dict = {1: {}, 2: {}}
        for ch in [1]:
            # for i in [2, 3, 4]:
            for i in [2]:
                pd2g_dict[ch][i] = {}
                if ch == 2 and not self.iq_mixer:
                    continue
                pd2g_dict[ch][i]['frequencies'] = self.frequencies[n]
                if self.robust:
                    pd2g_dict[ch][i].update(dict(type='robust', wave_file=E.WaveFile(part=self.part_step(n)[i], **self.wave_file_kwargs[n])))
                else:
                    pd2g_dict[ch][i].update(dict(type='sinehermite', amplitudes=self.amplitudes[n], length_mus=self.dur_step[n][i]))
                if ch == 2 and self.iq_mixer:
                    pd2g_dict[ch][i]['phases'] = np.array([self.mixer_deg])
                else:
                    pd2g_dict[2][i] = {}
                #if ch == 1 and self.wait_switch > 0: # TODO
                #    pd2g_dict[ch][i]['gateMW'] = True
                
        return pd2g_dict

    def compile(self):
        optical = False
        optical = ('nuc' in self.kwargs.keys()) and (self.kwargs['nuc'] in [
                        'charge_state',
                        'ple_A2',
                        'ple_A1',
                        "long_readout",
                        # 'Ex_pi_readout_6ns',
                        # 'Ex_ampl_sweep_SSR',
                        # 'opt_mw_delays_calibration',
                        # 'opt_mw_delays_calibration2',
                        # '2_opt_mw_delays_calibration',

                        # '2opt_withMW_pi',
                        # 'entanglement_for_tests',
                        # 'HOM',
                        # 'entanglement',
                        # 'Ex_ampl_sweep_SSR_6ns',
                        # 'Ex_pi_readout_10ns' ,
                        # 'Ex_pi_readout'
                          ])
        if optical:
            self.compileOptical()
        else:
            self.compileMW()

    def compileMW(self):
        aa = dict()
        if self.repetitions != 0:
            self.mcas.start_new_segment(name=self.name,
                                        loop_count=self.repetitions,
                                        advance_mode=self.advance_mode)

            #if self.number_of_alternating_steps!= 1:
            #    pass
                #raise Warning('most probably something is wrong with PulseStreamer - AWG syncronization')
            for alt_step in range(self.number_of_alternating_steps):
                d = self.pd2g_dict(alt_step)
                #if 'cw_mw' in self.kwargs.keys():
                #    laser = self.kwargs['cw_mw']
                #else:
                #   laser = False

                #if self.gate_or_trigger == 'trigger':
                if not self.kwargs.get("discard",False): #"discard" in self.kwargs.keys(): #this is a workaround because 4 ssr lead to errors, here we try to have just the ssr code without counting
                    self.mcas.asc(name = 'triggerTrue_gate', length_mus=__TT_TRIGGER_LENGTH__, gate=True, gateMW = True) # Gated counter

                #else:
                    #self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name = 'triggerFalse_memory') # ODMR... ORABI
                    #self.mcas.asc(length_mus=2.1, name = 'wait_after_memory')

                # self.mcas.asc(pd2g1=d[1][2], pd2g2=d[2][2], name='MW', **aa) # CNOT(s) #ORIGINAL VERSION
                if self.protected_readout: # we use self.kwargs for convenience here
                    print("doing central pi")
                    if all(item in self.kwargs.keys() for item in ["central_frequencies","central_amplitudes","central_length_mus"]):
                        self.mcas.asc(name='MW', length_mus=0.256-__TT_TRIGGER_LENGTH__, gateMW=True)
                        for idx,freq in enumerate(self.kwargs['central_frequencies']):
                            pd2g1 = {'frequencies': [self.kwargs['central_frequencies'][idx]], 'type': 'sinehermite', 
                                    'amplitudes': [self.kwargs['central_amplitudes'][idx]], 'length_mus': self.kwargs['central_length_mus']}
                            self.mcas.asc(pd2g1=pd2g1, gateMW=True, name='MW', **aa) #Each pi pulse will be writte separately.

                    else:
                        print(list(self.kwargs.keys()))
                        print("Raising exception")
                        raise Exception('You need to have "central_frequencies", "central_amplitudes" and "central_length_mus" in your pd2g dictionary for protected SSR to work.')
                    
                self.mcas.asc(name='MW', length_mus=0.256-__TT_TRIGGER_LENGTH__, gateMW=True)
                
                for idx,freq in enumerate(d[1][2]['frequencies']): #d[1][2] means awg, ch2?
                    #print("compileMW in snippets_awg")
                    #print(d[1][2]['frequencies'][idx])
                    #pd2g1 = {'frequencies': [d[1][2]['frequencies'][idx]], 'type': 'sine', 'amplitudes': [d[1][2]['amplitudes'][idx]], 'length_mus': d[1][2]['length_mus']}
                    #self.mcas.asc(pd2g1=pd2g1, gateMW=True, name='MW', **aa)
                    ## Here the frequencies are written separately :(((
                    pd2g1 = {'frequencies': [d[1][2]['frequencies'][idx]], 'type': 'sinehermite', 
                             'amplitudes': [d[1][2]['amplitudes'][idx]], 'length_mus': d[1][2]['length_mus']}
                    
                    #print("pd2g1 MW:",pd2g1)
                    self.mcas.asc(pd2g1=pd2g1, gateMW=True, name='MW', **aa) #Each pi pulse will be writte separately.

                #self.mcas.asc(name='MW', length_mus=0.256-__TT_TRIGGER_LENGTH__, gateMW=False)
                ### ===============================
                ### Conventional repetitive readout
                ### ===============================
                # read out counts after system is fully polarized
                self.mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(self.dur_step[alt_step][5]), laser=True, A2=True, name='Laser A2', **aa)

                if not self.kwargs.get("discard",False):
                    self.mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(self.dur_step[alt_step][6]), name='Count', **aa)
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'triggerTrue2_memory')
            
                #if self.gate_or_trigger == 'trigger':
                #if 'buffer_time' in self.kwargs.keys():
                #   self.mcas.asc(length_mus=self.kwargs['buffer_time'], name = 'Buffer')

        # print('compileMW finished')

    def compileOptical(self):
        # print('compileOptical in snippets_awg')
        aa = dict()
        if self.repetitions != 0:
            if 'no_new_segment' in self.kwargs.keys():
                pass

            else:
                self.mcas.start_new_segment(name=self.name,
                                            loop_count=self.repetitions,
                                            advance_mode=self.advance_mode)

            for alt_step in range(self.number_of_alternating_steps):
                d = self.pd2g_dict(alt_step)

                # if self.gate_or_trigger == 'trigger':
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True,name = 'gate1') # Gated counter
                # elif self.gate_or_trigger == 'gate_after_pulse':
                #     pass    # Correlation
                # self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter

                if 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'charge_state':
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter

                    #EOM on
                    # pd2g2 = dict(type='sine',
                    #              frequencies=[self.queue.ple_Ex.eom_freq],
                    #              amplitudes=[0.0],
                    #              )

                    self.mcas.asc(length_mus=self.dur_step[alt_step][5],
                                  A1=True, A2=True, laser = True,
                                  name='State_check', **aa)

                    self.mcas.asc(length_mus=2.0,name = 'wait')
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')

                elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'long_readout':
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter

                    #print(self.kwargs,self.kwargs.keys(),print(self.frequencies))
                    
                    pd2g1 = {'frequencies': self.frequencies[0], 'type': 'sinehermite', 'amplitudes': self.kwargs["amplitudes"]}
                    #print("DURRATION::::::::::",self.dur_step[alt_step][5])

                    self.mcas.asc(length_mus=self.dur_step[alt_step][5],
                                  A1=self.kwargs.get("A1",False), A2=self.kwargs.get("A2",False),repump=self.kwargs.get("repump",False), laser = True, gateMW=True, pd2g1=pd2g1,
                                  name='long_readout',gate=self.kwargs.get("gate",False), **aa)

                    self.mcas.asc(length_mus=2.0,name = 'wait')
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')


                elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'ple_A2':
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                    self.mcas.asc(A2=True, laser = True, length_mus=E.round_length_mus_to_x_multiple_ps(self.dur_step[alt_step][5]), name = 'ple_A2_readout')
                    self.mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.5),name = 'wait')
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                
                
                elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'ple_A1':
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                    #self.mcas.asc(A1=False, length_mus=self.dur_step[alt_step][6], name = 'initial wait') # Delete me again
                    self.mcas.asc(A1=True, laser = True, length_mus=E.round_length_mus_to_16_multiple_ps(self.dur_step[alt_step][5]), name = 'ple_A1_readout')
                    self.mcas.asc(length_mus=E.round_length_mus_to_16_multiple_ps(0.5),name = 'wait')
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')

                elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'ple_A2_delay':
                    aom_A2_delay = 0.45 # delay is 450ns
                    aom_A2_delay = self.wait_dur
                    print("Using ple_A2_delay")
                    print("Delay: ", aom_A2_delay)

                    self.mcas.asc(A2=True, laser = True, length_mus=self.dur_step[alt_step][5], name = 'ple_A2_readout')

                    if self.dur_step[alt_step][5] < aom_A2_delay:
                        self.mcas.asc(length_mus=aom_A2_delay-self.dur_step[alt_step][5], name = 'wait')
                        self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                    else:
                        self.mcas.asc(A2=True, laser = True, length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                        self.mcas.asc(A2=True, laser = True, length_mus=self.dur_step[alt_step][5]-(aom_A2_delay+__TT_TRIGGER_LENGTH__), name = 'ple_A2_readout')
                        self.mcas.asc(length_mus=aom_A2_delay,name = 'wait')
                    self.mcas.asc(length_mus=0.1,name = 'wait')
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                
                elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'ple_A1_delay':
                    aom_A1_delay = 0.37 # delay is 370ns
                    aom_A1_delay = self.wait_dur
                    print("Using ple_A1_delay")
                    print("Delay: ", aom_A1_delay)

                    self.mcas.asc(A1=True, laser = True, length_mus=self.dur_step[alt_step][5], name = 'ple_A1_readout')

                    if self.dur_step[alt_step][5] < aom_A1_delay:
                        self.mcas.asc(length_mus=aom_A1_delay-self.dur_step[alt_step][5], name = 'wait')
                        self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                    else:
                        self.mcas.asc(A1=True, laser = True, length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                        self.mcas.asc(A1=True, laser = True, length_mus=self.dur_step[alt_step][5]-(aom_A1_delay+__TT_TRIGGER_LENGTH__), name = 'ple_A1_readout')
                        self.mcas.asc(length_mus=aom_A1_delay,name = 'wait')
                    self.mcas.asc(length_mus=0.1,name = 'wait')
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                
                    # delta+=self.dur_step[alt_step][5]
                #
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'Ex_pi_readout_6ns':
                #     # print('snipets were updated')
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #     for i in range(1):
                #         self.mcas.asc(length_mus=0.02, aom_Ex=True)
                #         self.mcas.asc(length_mus=0.145)
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss_6ns',
                #                 inv_fwhm=1,
                #                 amplitudes=[1.0]),
                #             # aom_Ex = True,
                #             # gate = True,
                #             # memory = True,
                #             length_smpl=481 * 3,
                #         )
                #         if i == 0:
                #             g=True
                #         else:
                #             g=False
                #         self.mcas.asc(gate=g, memory=False, length_mus=0.1)
                #         # mcas.asc(length_mus=0.550, aom_Ex=True)
                #         self.mcas.asc(length_mus=0.05)
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True)
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'Ex_pi_readout_10ns':
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #     # print('snipets were updated')
                #     self.mcas.asc(length_mus=0.050, aom_Ex=True)
                #     self.mcas.asc(length_mus=0.15)
                #     self.mcas.asc(
                #         name='Ex_pi_readout_10ns',
                #         pd2g2=dict(
                #             type='gauss_6ns',
                #             inv_fwhm=1,
                #             amplitudes=[1.0],
                #         ),
                #         length_smpl=481*5,
                #         **aa
                #     )
                #     self.mcas.asc(length_mus=1.0)
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'Ex_pi_readout':
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #     # print('snipets were updated')
                #     for i in range(10): # why we have here 10 iterations??
                #         self.mcas.asc(length_mus=0.050, aom_Ex=True)
                #         self.mcas.asc(length_mus=0.15)
                #         self.mcas.asc(
                #             name='Ex_pi_readout',
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[1.0],
                #             ),
                #             length_smpl=481,
                #             **aa
                #         )
                #         self.mcas.asc(length_mus=1.0)
                #
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True)
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'Ex_ampl_sweep_SSR_6ns':
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #     # print('snipets were updated')
                #     self.mcas.asc(length_mus=0.09, aom_Ex=True)
                #     self.mcas.asc(length_mus=0.08, name='aom_delay')
                #     self.mcas.asc(
                #         pd2g2=dict(
                #             type='gauss_6ns',
                #             inv_fwhm=1,
                #             amplitudes=[self.kwargs['eom_ampl']]),
                #         length_mus=481 * 3. / __SAMPLE_FREQUENCY__,
                #         name='Gauss')
                #
                #     self.mcas.asc(length_mus=1.0)
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True)
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'Ex_ampl_sweep_SSR':
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #
                #
                #     # self.mcas.asc(length_mus=0.02, aom_Ex=True)
                #     # self.mcas.asc(length_mus=0.137, name='aom_delay')
                #     #
                #     self.mcas.asc(length_mus=0.009, aom_Ex=True)
                #     self.mcas.asc(length_mus=0.151, name='aom_delay')
                #     # self.mcas.asc(length_mus=0.015, aom_Ex=True)
                #     # self.mcas.asc(length_mus=0.155, name='aom_delay')
                #
                #     self.mcas.asc(
                #         pd2g2=dict(
                #             type='gauss',
                #             inv_fwhm=1,
                #             amplitudes=[self.kwargs['eom_ampl']]),
                #         length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #         name='Gauss')
                #
                #     self.mcas.asc(length_mus=0.1)
                #
                #
                #
                #     # =========DELETE IT AFTER TEST!!!
                #     #
                #     # self.mcas.asc(length_mus=0.009, aom_Ex=True)
                #     # self.mcas.asc(length_mus=0.151, name='aom_delay')
                #     # # self.mcas.asc(length_mus=0.015, aom_Ex=True)
                #     # # self.mcas.asc(length_mus=0.155, name='aom_delay')
                #     #
                #     # self.mcas.asc(
                #     #     pd2g2=dict(
                #     #         type='gauss',
                #     #         inv_fwhm=1,
                #     #         amplitudes=[self.kwargs['eom_ampl']]),
                #     #     length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #     #     name='Gauss')
                #     # =========DELETE IT AFTER TEST!!!
                #
                #
                #     self.mcas.asc(length_mus=0.5)
                #     self.mcas.asc(length_mus=self.laser_dur)
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'opt_mw_delays_calibration':
                #
                #     pi_dur = self.kwargs['pi_dur']
                #     mw_amplitude = self.kwargs['mw_amplitude']
                #     # print('kwargs keys: ',self.kwargs.keys())
                #     # print('self.frequencies: ',self.frequencies)
                #
                #     mw_freq = self.frequencies[0]
                #     tau = self.kwargs['tau']
                #     # aom_Ex_dur = 0.015#0.02
                #     # aom_delay = 0.155#0.137
                #     aom_Ex_dur = 0.02#0.02
                #     aom_delay = 0.137#0.137
                #     opt_pi_dur = 481 * 1. / __SAMPLE_FREQUENCY__
                #     # print('======= Tau is: ',tau)
                #     # tau determines the start of the MW pulse relative to start of the aom pulse
                #
                #     if tau <0 and np.abs(tau)>=pi_dur:
                #
                #         # print('if_1')
                #         if np.abs(tau) < __TT_TRIGGER_LENGTH__:
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #             # print('if_1.1')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),
                #                 name='MW_pi',
                #             )
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(np.abs(tau) - pi_dur), name='wait')
                #
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,name='Ex_aom')
                #             self.mcas.asc(length_mus=aom_delay, name='aom_delay')
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[self.kwargs['eom_ampl']]),
                #                 length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #                 name='Gauss')
                #         elif np.abs(tau) >= __TT_TRIGGER_LENGTH__:
                #             # print('if_1.2')
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),
                #                 name='MW_pi',
                #             )
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(np.abs(tau) - pi_dur-__TT_TRIGGER_LENGTH__), name='wait')
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,name='Ex_aom')
                #             self.mcas.asc(length_mus=aom_delay, name='aom_delay')
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[self.kwargs['eom_ampl']]),
                #                 length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #                 name='Gauss')
                #
                #         self.mcas.asc(length_mus=self.laser_dur)
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                #
                #     elif tau < 0 and np.abs(tau) < pi_dur:
                #         # print('if_2')
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(np.abs(tau)),
                #             name='MW_pi',
                #         )
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(pi_dur-np.abs(tau)),
                #             name='MW_pi_with_aom_Ex',
                #             aom_Ex = True
                #         )
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur-(pi_dur-np.abs(tau))),
                #                       aom_Ex=True,name='Ex_aom_residual')
                #
                #         self.mcas.asc(length_mus=aom_delay, name='aom_delay')
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[self.kwargs['eom_ampl']]),
                #             length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #             name='Gauss')
                #
                #         self.mcas.asc(length_mus=self.laser_dur)
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                #
                #     elif tau >= 0 and np.abs(tau) <aom_Ex_dur:
                #         # print('if_3')
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau),
                #                       aom_Ex=True,name='Ex_aom')
                #         if pi_dur <= (aom_Ex_dur-tau):
                #             # print('if_3.1')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),
                #                 name='MW_pi_with_aom_Ex', aom_Ex=True
                #             )
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur - (pi_dur + tau)),
                #                           aom_Ex=True,name='Ex_aom_residiual')
                #
                #             self.mcas.asc(length_mus=aom_delay, name='aom_delay')
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[self.kwargs['eom_ampl']]),
                #                 length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #                 name='Gauss')
                #
                #             self.mcas.asc(length_mus=self.laser_dur)
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                #
                #         if pi_dur > (aom_Ex_dur-tau):
                #             # print('if_3.2')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(aom_Ex_dur - tau),
                #                 name='MW_pi_with_aom_Ex',aom_Ex=True
                #             )
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur - (aom_Ex_dur - tau)),
                #                 name='MW_pi'
                #             )
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_delay - (pi_dur - (aom_Ex_dur - tau))),#aom_delay
                #                           name='aom_delay')
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[self.kwargs['eom_ampl']]),
                #                 length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #                 name='Gauss')
                #
                #             self.mcas.asc(length_mus=self.laser_dur)
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                #
                #     elif tau > 0 and np.abs(tau) >= aom_Ex_dur and (np.abs(tau)+pi_dur)<=(aom_delay+aom_Ex_dur):
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #         # print('if_4')
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur),
                #                       aom_Ex=True,name='Ex_aom')
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau - aom_Ex_dur))
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(pi_dur),
                #             name='MW_pi')
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_delay-pi_dur-(tau - aom_Ex_dur)),
                #                       name='aom_delay')
                #
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[self.kwargs['eom_ampl']]),
                #             length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #             name='Gauss')
                #
                #         self.mcas.asc(length_mus=self.laser_dur)
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #     elif tau > 0 and np.abs(tau) >= aom_Ex_dur and (np.abs(tau)+pi_dur)>(aom_delay+aom_Ex_dur):
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #         # print('if_5')
                #         if np.abs(tau)<=(aom_delay+aom_Ex_dur):
                #             # print('if_5.1')
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur),
                #                           aom_Ex=True,name='Ex_aom')
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau - aom_Ex_dur))
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(aom_delay - (tau - aom_Ex_dur)),
                #                 name='MW_pi')
                #
                #             remaining_mw_dur = pi_dur - (aom_delay-(tau-aom_Ex_dur))
                #             # print('remaining mw_dur = ',remaining_mw_dur)
                #             if remaining_mw_dur >= opt_pi_dur:
                #                 # print('if_5.1.1')
                #                 self.mcas.asc(
                #                     pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                     length_mus=opt_pi_dur,
                #                     name='Gauss')
                #
                #                 self.mcas.asc(
                #                     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                     length_mus=E.round_length_mus_full_sample(remaining_mw_dur - opt_pi_dur),
                #                     name='MW_pi')
                #                 self.mcas.asc(length_mus=self.laser_dur)
                #                 self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #             if remaining_mw_dur < opt_pi_dur:
                #                 # print('if_5.1.2')
                #                 self.mcas.asc(
                #                     pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                     length_mus=remaining_mw_dur,
                #                     name='Gauss')
                #                 already_written_samples = np.around(remaining_mw_dur * __SAMPLE_FREQUENCY__).astype(int)
                #
                #                 self.mcas.asc(
                #                     pd2g2=dict(type='gauss', inv_fwhm=1, wf_start=already_written_samples,amplitudes=[self.kwargs['eom_ampl']]),
                #
                #                     length_mus=opt_pi_dur - remaining_mw_dur,
                #                     name='Gauss')
                #
                #                 self.mcas.asc(length_mus=self.laser_dur)
                #                 self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #
                #         if np.abs(tau)>(aom_delay+aom_Ex_dur):
                #             # print('if_5.2')
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur),
                #                           aom_Ex=True,name='Ex_aom')
                #             self.mcas.asc(length_mus=aom_delay, name='aom_delay')
                #
                #
                #             if tau >=(aom_delay+aom_Ex_dur+opt_pi_dur):
                #                 # print('if_5.2.1')
                #                 if tau >=(aom_delay+aom_Ex_dur+opt_pi_dur+__TT_TRIGGER_LENGTH__):
                #                     self.mcas.asc(
                #                         pd2g2=dict(
                #                             type='gauss',
                #                             inv_fwhm=1,
                #                             amplitudes=[self.kwargs['eom_ampl']]),
                #                         length_mus=opt_pi_dur,
                #                         name='Gauss')
                #
                #
                #                     self.mcas.asc(length_mus=self.laser_dur)
                #                     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #                     self.mcas.asc(length_mus=tau - (opt_pi_dur + aom_delay + aom_Ex_dur+__TT_TRIGGER_LENGTH__),
                #                                   name='wait for mw')
                #
                #                     self.mcas.asc(
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=E.round_length_mus_full_sample(pi_dur),
                #                         name='MW_pi',
                #                     )
                #
                #                     # self.mcas.asc(length_mus=self.laser_dur)
                #                     # self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #
                #                 else:
                #                     self.mcas.asc(
                #                         pd2g2=dict(
                #                             type='gauss',
                #                             inv_fwhm=1,
                #                             amplitudes=[self.kwargs['eom_ampl']]),
                #                         length_mus=opt_pi_dur,
                #                         name='Gauss')
                #
                #                     self.mcas.asc(length_mus=tau - (opt_pi_dur+aom_delay+aom_Ex_dur), name='wait for mw')
                #                     self.mcas.asc(
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=E.round_length_mus_full_sample(pi_dur),
                #                         name='MW_pi',
                #                     )
                #
                #                     self.mcas.asc(length_mus=self.laser_dur)
                #                     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #
                #             if tau < (aom_delay + aom_Ex_dur + opt_pi_dur):
                #                 # print('if_5.2.2')
                #
                #                 self.mcas.asc(
                #                     pd2g2=dict(
                #                         type='gauss',
                #                         inv_fwhm=1,
                #                         amplitudes=[self.kwargs['eom_ampl']]),
                #                     length_mus=E.round_length_mus_full_sample(tau-aom_Ex_dur-aom_delay),
                #                     name='Gauss_begin')
                #
                #                 already_written_samples = np.around((tau-aom_Ex_dur-aom_delay) * __SAMPLE_FREQUENCY__).astype(int)
                #                 remaining_optical = opt_pi_dur - (tau-aom_Ex_dur-aom_delay)
                #                 if pi_dur >= remaining_optical:
                #                     # print('if_5.2.2.1')
                #
                #                     self.mcas.asc(
                #                         pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                         wf_start=already_written_samples,
                #
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=remaining_optical,
                #                         name='Gauss_end')
                #
                #                     self.mcas.asc(
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=E.round_length_mus_full_sample(pi_dur-remaining_optical),
                #                         name='MW_pi')
                #                     self.mcas.asc(length_mus=self.laser_dur)
                #                     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #                 if pi_dur < remaining_optical:
                #                     # print('if_5.2.2.2')
                #
                #                     self.mcas.asc(
                #                         pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                         wf_start=already_written_samples,
                #
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=pi_dur,
                #                         name='Gauss_MW')
                #                     already_written_samples+= np.around(pi_dur* __SAMPLE_FREQUENCY__).astype(int)
                #
                #                     self.mcas.asc(
                #                         pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                         wf_start=already_written_samples,
                #                         # length_mus=pi_dur,
                #                         length_mus=opt_pi_dur - (tau-aom_Ex_dur-aom_delay)-pi_dur,
                #                         name='Gauss_end')
                #
                #                     self.mcas.asc(length_mus=self.laser_dur)
                #                     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'opt_mw_delays_calibration2':
                #
                #     pi_dur = self.kwargs['pi_dur']
                #     mw_amplitude = self.kwargs['mw_amplitude']
                #     mw_freq = self.frequencies[0]
                #     tau = self.kwargs['tau']
                #     aom_Ex_dur = 0.02#0.02
                #     aom_delay = 0.137#0.137
                #     opt_pi_dur = 481 * 1. / __SAMPLE_FREQUENCY__
                #
                #     if tau <0 and np.abs(tau)>=pi_dur:
                #
                #         # print('if_1')
                #         if np.abs(tau) < __TT_TRIGGER_LENGTH__:
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #             # print('if_1.1')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),
                #                 name='MW_pi',
                #             )
                #             self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(np.abs(tau) - pi_dur), name='wait')
                #
                #             self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=aom_Ex_dur, aom_Ex=True,name='Ex_aom')
                #             self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=aom_delay, name='aom_delay')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[self.kwargs['eom_ampl']]),
                #                 length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #                 name='Gauss')
                #         elif np.abs(tau) >= __TT_TRIGGER_LENGTH__:
                #             # print('if_1.2')
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),
                #                 name='MW_pi',
                #             )
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(np.abs(tau) - pi_dur-__TT_TRIGGER_LENGTH__), name='wait')
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=aom_Ex_dur, aom_Ex=True,name='Ex_aom')
                #             self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=aom_delay, name='aom_delay')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[self.kwargs['eom_ampl']]),
                #                 length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #                 name='Gauss')
                #
                #         self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=self.laser_dur,)
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                #
                #     elif tau < 0 and np.abs(tau) < pi_dur:
                #         print('tau is : ', tau)
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(np.abs(tau)),
                #             name='MW_pi',
                #         )
                #
                #         self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(aom_Ex_dur),
                #                       aom_Ex=True,name='Ex_aom_residual')
                #
                #         self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=aom_delay, name='aom_delay')
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[self.kwargs['eom_ampl']]),
                #             length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #             name='Gauss')
                #
                #         self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                       length_mus=self.laser_dur)
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                #
                #     elif tau >= 0 and np.abs(tau) <aom_Ex_dur:
                #         # print('if_3')
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau),
                #                       aom_Ex=True,name='Ex_aom')
                #         if pi_dur <= (aom_Ex_dur-tau):
                #             # print('if_3.1')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),
                #                 name='MW_pi_with_aom_Ex', aom_Ex=True
                #             )
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur - (pi_dur + tau)),
                #                           pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                           aom_Ex=True,name='Ex_aom_residiual')
                #
                #             self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=aom_delay, name='aom_delay')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[self.kwargs['eom_ampl']]),
                #                 length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #                 name='Gauss')
                #
                #             self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                           length_mus=self.laser_dur)
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                #
                #         if pi_dur > (aom_Ex_dur-tau):
                #             # print('if_3.2')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(aom_Ex_dur - tau),
                #                 name='MW_pi_with_aom_Ex',aom_Ex=True
                #             )
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur - (aom_Ex_dur - tau)),
                #                 name='MW_pi'
                #             )
                #
                #             self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(aom_delay - (pi_dur - (aom_Ex_dur - tau))),#aom_delay
                #                           name='aom_delay')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[self.kwargs['eom_ampl']]),
                #                 length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #                 name='Gauss')
                #
                #             self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=self.laser_dur)
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True,name = 'memory')
                #
                #     elif tau > 0 and np.abs(tau) >= aom_Ex_dur and (np.abs(tau)+pi_dur)<=(aom_delay+aom_Ex_dur):
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #         # print('if_4')
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur),
                #                       aom_Ex=True,name='Ex_aom')
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau - aom_Ex_dur))
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(pi_dur),
                #             name='MW_pi')
                #
                #         self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(aom_delay-pi_dur-(tau - aom_Ex_dur)),
                #                       name='aom_delay')
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[self.kwargs['eom_ampl']]),
                #             length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #             name='Gauss')
                #
                #         self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                       length_mus=self.laser_dur)
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #     elif tau > 0 and np.abs(tau) >= aom_Ex_dur and (np.abs(tau)+pi_dur)>(aom_delay+aom_Ex_dur):
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #
                #         # print('if_5')
                #         if np.abs(tau)<=(aom_delay+aom_Ex_dur):
                #             # print('if_5.1')
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur),
                #                           aom_Ex=True,name='Ex_aom')
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau - aom_Ex_dur))
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(aom_delay - (tau - aom_Ex_dur)),
                #                 name='MW_pi')
                #
                #             remaining_mw_dur = pi_dur - (aom_delay-(tau-aom_Ex_dur))
                #             # print('remaining mw_dur = ',remaining_mw_dur)
                #             if remaining_mw_dur >= opt_pi_dur:
                #                 # print('if_5.1.1')
                #                 self.mcas.asc(
                #                     pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                     length_mus=opt_pi_dur,
                #                     name='Gauss')
                #
                #                 self.mcas.asc(
                #                     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                     length_mus=E.round_length_mus_full_sample(remaining_mw_dur - opt_pi_dur),
                #                     name='MW_pi')
                #                 self.mcas.asc(length_mus=self.laser_dur)
                #                 self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #             if remaining_mw_dur < opt_pi_dur:
                #                 # print('if_5.1.2')
                #                 self.mcas.asc(
                #                     pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                     length_mus=remaining_mw_dur,
                #                     name='Gauss')
                #                 already_written_samples = np.around(remaining_mw_dur * __SAMPLE_FREQUENCY__).astype(int)
                #
                #                 self.mcas.asc(
                #                     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                     pd2g2=dict(type='gauss', inv_fwhm=1, wf_start=already_written_samples,amplitudes=[self.kwargs['eom_ampl']]),
                #
                #                     length_mus=opt_pi_dur - remaining_mw_dur,
                #                     name='Gauss')
                #
                #                 self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                               length_mus=self.laser_dur)
                #                 self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #
                #         if np.abs(tau)>(aom_delay+aom_Ex_dur):
                #             # print('if_5.2')
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur),
                #                           aom_Ex=True,name='Ex_aom')
                #             self.mcas.asc(length_mus=aom_delay, name='aom_delay')
                #
                #
                #             if tau >=(aom_delay+aom_Ex_dur+opt_pi_dur):
                #                 # print('if_5.2.1')
                #                 if tau >=(aom_delay+aom_Ex_dur+opt_pi_dur+__TT_TRIGGER_LENGTH__):
                #                     self.mcas.asc(
                #                         pd2g2=dict(
                #                             type='gauss',
                #                             inv_fwhm=1,
                #                             amplitudes=[self.kwargs['eom_ampl']]),
                #                         length_mus=opt_pi_dur,
                #                         name='Gauss')
                #
                #
                #                     self.mcas.asc(length_mus=self.laser_dur)
                #                     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #                     self.mcas.asc(length_mus=tau - (opt_pi_dur + aom_delay + aom_Ex_dur+__TT_TRIGGER_LENGTH__),
                #                                   name='wait for mw')
                #
                #                     self.mcas.asc(
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=E.round_length_mus_full_sample(pi_dur),
                #                         name='MW_pi',
                #                     )
                #
                #                     # self.mcas.asc(length_mus=self.laser_dur)
                #                     # self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #
                #                 else:
                #                     self.mcas.asc(
                #                         pd2g2=dict(
                #                             type='gauss',
                #                             inv_fwhm=1,
                #                             amplitudes=[self.kwargs['eom_ampl']]),
                #                         length_mus=opt_pi_dur,
                #                         name='Gauss')
                #
                #                     self.mcas.asc(length_mus=tau - (opt_pi_dur+aom_delay+aom_Ex_dur), name='wait for mw')
                #                     self.mcas.asc(
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=E.round_length_mus_full_sample(pi_dur),
                #                         name='MW_pi',
                #                     )
                #
                #                     self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                                   length_mus=self.laser_dur)
                #                     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #
                #             if tau < (aom_delay + aom_Ex_dur + opt_pi_dur):
                #                 # print('if_5.2.2')
                #
                #                 self.mcas.asc(
                #                     pd2g2=dict(
                #                         type='gauss',
                #                         inv_fwhm=1,
                #                         amplitudes=[self.kwargs['eom_ampl']]),
                #                     length_mus=E.round_length_mus_full_sample(tau-aom_Ex_dur-aom_delay),
                #                     name='Gauss_begin')
                #
                #                 already_written_samples = np.around((tau-aom_Ex_dur-aom_delay) * __SAMPLE_FREQUENCY__).astype(int)
                #                 remaining_optical = opt_pi_dur - (tau-aom_Ex_dur-aom_delay)
                #                 if pi_dur >= remaining_optical:
                #                     # print('if_5.2.2.1')
                #
                #                     self.mcas.asc(
                #                         pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                         wf_start=already_written_samples,
                #
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=remaining_optical,
                #                         name='Gauss_end')
                #
                #                     self.mcas.asc(
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=E.round_length_mus_full_sample(pi_dur-remaining_optical),
                #                         name='MW_pi')
                #                     self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                                   length_mus=self.laser_dur)
                #                     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                #
                #                 if pi_dur < remaining_optical:
                #                     # print('if_5.2.2.2')
                #
                #                     self.mcas.asc(
                #                         pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                         wf_start=already_written_samples,
                #
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         length_mus=pi_dur,
                #                         name='Gauss_MW')
                #                     already_written_samples+= np.around(pi_dur* __SAMPLE_FREQUENCY__).astype(int)
                #
                #                     self.mcas.asc(
                #                         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                         pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #                         wf_start=already_written_samples,
                #                         # length_mus=pi_dur,
                #                         length_mus=opt_pi_dur - (tau-aom_Ex_dur-aom_delay)-pi_dur,
                #                         name='Gauss_end')
                #
                #                     self.mcas.asc(pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                                   length_mus=self.laser_dur)
                #                     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == '2_opt_mw_delays_calibration_old':
                #
                #
                #     mw_amplitude = self.kwargs['mw_amplitude']
                #     if 'mw_pihalf_ampl' in self.kwargs.keys():
                #         mw_pihalf_ampl = self.kwargs['mw_pihalf_ampl']
                #     else:
                #         mw_pihalf_ampl = mw_amplitude
                #
                #     optical_delay = self.kwargs['optical_delay'] #56ns (was 125ns) delay between optical pulses aka interferometer length
                #
                #     pi_dur = self.kwargs['pi_dur']
                #     mw_freq = self.frequencies[0]
                #     tau = self.kwargs['tau']
                #     pihalf_dur =self.kwargs['pihalf_dur']
                #     eom_ampl = self.kwargs['eom_ampl']
                #     aom_Ex_dur = 0.02#0.02
                #     aom_delay = 0.137#0.137
                #     opt_pi_dur = 481 * 1. / __SAMPLE_FREQUENCY__
                #     # tau determines the start of the MW pulse relative to start of the aom pulse
                #     # if aom_delay +aom_Ex_dur + optical_delay <tau < (aom_delay+aom_Ex_dur):
                #
                #     if tau< optical_delay+aom_Ex_dur:
                #         raise Exception('Tau is too short. must be greater than 76ns')
                #
                #
                #     if tau <= (aom_delay+aom_Ex_dur):
                #         if tau+pi_dur>=(aom_delay+aom_Ex_dur):
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True,
                #                           name='gate1')  # 160ns Gated counter
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_1')  # 20 ns. AOM for the first pulse
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #                 name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #
                #             self.mcas.asc(length_mus=optical_delay - aom_Ex_dur-pihalf_dur,
                #                           name='wait_1.1')  # 36ns ns. Delay between first and second AOM_Ex pulses
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_2')  # 20 ns. AOM for the first puls
                #
                #             self.mcas.asc(length_mus=tau - (optical_delay+aom_Ex_dur) , name='wait_2')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(aom_Ex_dur + aom_delay - tau),
                #                 name='MW_begin')  # 13.5ns. First pi/2 pulse
                #
                #             gauss1_begin = pi_dur - (aom_Ex_dur + aom_delay - tau)
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #                 name='Gauss1_MW')  # First EOM Pulse
                #             already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss1_begin),  #
                #                 name='Gauss1_end')
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - opt_pi_dur),
                #                           name='wait')  #
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=opt_pi_dur,  # 0.04008333333333333 ns Second EOM pulse starts
                #                 name='Gauss2')
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #
                #         else:
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True,
                #                           name='gate1')  # 160ns Gated counter
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_1')  # 20 ns. AOM for the first pulse
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #                 name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #
                #             self.mcas.asc(length_mus=optical_delay - aom_Ex_dur - pihalf_dur,
                #                           name='wait_1.1')  # 36ns ns. Delay between first and second AOM_Ex pulses
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_2')  # 20 ns. AOM for the first puls
                #
                #             self.mcas.asc(length_mus=tau - (optical_delay + aom_Ex_dur), name='wait_2')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),
                #                 name='MW_begin')  # 13.5ns. First pi/2 pulse
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur +aom_delay - (tau+pi_dur)),
                #                           name='wait_3')
                #
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #                 name='Gauss1')  # First EOM Pulse
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - opt_pi_dur),
                #                           name='wait')  #
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=opt_pi_dur,  # 0.04008333333333333 ns Second EOM pulse starts
                #                 name='Gauss2')
                #
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #     elif aom_delay +aom_Ex_dur + optical_delay <=tau<aom_delay +aom_Ex_dur + optical_delay +opt_pi_dur:
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                       name='Ex_aom_1')  # 20 ns. AOM for the first pulse
                #         self.mcas.asc(length_mus=optical_delay - aom_Ex_dur,
                #                       name='wait_1.1')  # 36ns ns. Delay between first and second AOM_Ex pulses
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                       name='Ex_aom_2')  # 20 ns. AOM for the first puls
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(0.007), name='wait_1')  # 7ns
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #             length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #             name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #
                #         self.mcas.asc(length_mus=0.0605, name='wait_2')
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[eom_ampl]),
                #             length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #             name='Gauss1')  # First EOM Pulse
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - opt_pi_dur), name='wait_2')
                #
                #         gauss2_begin = tau - (aom_Ex_dur+aom_delay+optical_delay)
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[eom_ampl]),
                #             length_mus=E.round_length_mus_full_sample(gauss2_begin),
                #             name='Gauss2_begin')  # First EOM Pulse
                #         already_written_samples = np.around(gauss2_begin * __SAMPLE_FREQUENCY__).astype(int)
                #
                #         if tau + pi_dur <= aom_delay +aom_Ex_dur + optical_delay +opt_pi_dur:
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),  #
                #                 name='Gauss2_MW')
                #             already_written_samples+=np.around(pi_dur * __SAMPLE_FREQUENCY__).astype(int)
                #
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - (gauss2_begin + pi_dur)),
                #                 name='Gauss2_end')
                #
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #         else:
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss2_begin),  #
                #                 name='Gauss2_MW')
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur-(opt_pi_dur - gauss2_begin)),
                #                 name='MW_end')
                #
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #     elif tau >= aom_delay + aom_Ex_dur + optical_delay + opt_pi_dur:
                #         # ---------------
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                       name='Ex_aom_1')  # 20 ns. AOM for the first pulse
                #         self.mcas.asc(length_mus=optical_delay - aom_Ex_dur,
                #                       name='wait_1.1')  # 36ns ns. Delay between first and second AOM_Ex pulses
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                       name='Ex_aom_2')  # 20 ns. AOM for the first puls
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(0.007), name='wait_1')  # 7ns
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #             length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #             name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #         self.mcas.asc(length_mus=0.0605, name='wait_2')
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[eom_ampl]),
                #             length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #             name='Gauss1')  # First EOM Pulse
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - opt_pi_dur), name='wait_2')
                #
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[eom_ampl]),
                #             length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #             name='Gauss2')  # Second EOM Pulse
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau - ( aom_delay + aom_Ex_dur + optical_delay + opt_pi_dur)), name='wait_2')
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(pi_dur),
                #             name='MW_pi')  # 27ns
                #
                #         self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #     else:
                #         # !!!!!! THIS PART IS USED
                #
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                       name='Ex_aom_1')  # 20 ns. AOM for the first pulse
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - aom_Ex_dur),
                #                       name='wait_1.1')  # 36ns ns. Delay between first and second AOM_Ex pulses
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                       name='Ex_aom_2')  # 20 ns. AOM for the first puls
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(0.007), name='wait_1')  # 7ns
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #             length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #             name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #
                #         self.mcas.asc(length_mus=0.0605, name='wait_2')
                #
                #         if tau >= aom_delay + aom_Ex_dur and tau + pi_dur <= (aom_delay + aom_Ex_dur + opt_pi_dur):
                #
                #             gauss1_begin = tau - (aom_delay + aom_Ex_dur)
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #                 name='Gauss1_begin')  # First EOM Pulse
                #             already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),  #
                #                 name='Gauss1_MW')
                #             already_written_samples += np.around(pi_dur * __SAMPLE_FREQUENCY__).astype(int)
                #
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - pi_dur - gauss1_begin),  #
                #                 name='Gauss1_end')
                #             self.mcas.asc(length_mus=optical_delay - opt_pi_dur,
                #                           name='wait_3')  # 14.5ns wait before second optical pi pulse
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=opt_pi_dur,  # 0.04008333333333333 ns Second EOM pulse starts
                #                 name='Gauss2')
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #         elif aom_delay + aom_Ex_dur < tau < aom_delay + aom_Ex_dur +opt_pi_dur \
                #                 and aom_delay + aom_Ex_dur +optical_delay>=tau + pi_dur > (aom_delay + aom_Ex_dur + opt_pi_dur):
                #             gauss1_begin = tau - (aom_delay + aom_Ex_dur)
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #                 name='Gauss1_begin')  # First EOM Pulse
                #             already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss1_begin),  #
                #                 name='Gauss1_MW')
                #
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur - (opt_pi_dur - gauss1_begin)),  #
                #                 name='MW_end')
                #
                #             self.mcas.asc(length_mus=optical_delay - (opt_pi_dur+pi_dur - (opt_pi_dur - gauss1_begin)),
                #                           name='wait_3')  # 14.5ns wait before second optical pi pulse
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=opt_pi_dur,  # 0.04008333333333333 ns Second EOM pulse starts
                #                 name='Gauss2')
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #         elif aom_delay + aom_Ex_dur < tau < aom_delay + aom_Ex_dur +opt_pi_dur \
                #                 and aom_delay + aom_Ex_dur +optical_delay < tau + pi_dur:
                #             # !!!!!! THIS PART IS USED
                #
                #             gauss1_begin = tau - (aom_delay + aom_Ex_dur)
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #                 name='Gauss1_begin')  # First EOM Pulse
                #             already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss1_begin),  #
                #                 name='Gauss1_MW')
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(optical_delay - opt_pi_dur),  #
                #                 name='MW')
                #
                #             gauss2_begin =E.round_length_mus_full_sample(pi_dur - (opt_pi_dur - gauss1_begin + optical_delay - opt_pi_dur))
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=gauss2_begin,  # 0.04008333333333333 ns Second EOM pulse starts
                #                 name='Gauss2_MW')
                #             already_written_samples = np.around(gauss2_begin * __SAMPLE_FREQUENCY__).astype(int)
                #
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss2_begin),  #
                #                 name='Gauss2_end')
                #
                #
                #
                #             if 'tau_bell' in self.kwargs.keys():
                #                 self.mcas.asc(length_mus=E.round_length_mus_full_sample(0.075917),
                #                               name='wait_before_MW')  # 100ns
                #                 tau_bell = self.kwargs['tau_bell']
                #                 self.mcas.asc(
                #                     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #                     length_mus=E.round_length_mus_full_sample(tau_bell),
                #                     name='tau bell')  # 13.5ns. First pi/2 pulse
                #
                #
                #
                #
                #
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #         elif aom_delay + aom_Ex_dur + optical_delay > tau > aom_delay + aom_Ex_dur + opt_pi_dur :
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #                 name='Gauss1_begin')  # First EOM Pulse
                #
                #             self.mcas.asc(length_mus=tau - (aom_delay + aom_Ex_dur + opt_pi_dur),
                #                           name='wait_3')  # 14.5ns wait before second optical pi pulse
                #
                #             # pd2g1 = dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(aom_delay + aom_Ex_dur + optical_delay - tau),  #
                #                 name='MW_end')
                #
                #             gauss2_begin = pi_dur - (aom_delay + aom_Ex_dur + optical_delay - tau)
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=gauss2_begin,  # 0.04008333333333333 ns Second EOM pulse starts
                #                 name='Gauss2_MW')
                #             already_written_samples = np.around(gauss2_begin * __SAMPLE_FREQUENCY__).astype(int)
                #
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss2_begin),  #
                #                 name='Gauss')
                #
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == '2_opt_mw_delays_calibration':
                #
                #
                #     mw_amplitude = self.kwargs['mw_amplitude']
                #     if 'mw_pihalf_ampl' in self.kwargs.keys():
                #         mw_pihalf_ampl = self.kwargs['mw_pihalf_ampl']
                #     else:
                #         mw_pihalf_ampl = mw_amplitude
                #
                #     optical_delay = self.kwargs['optical_delay'] #56ns (was 125ns) delay between optical pulses aka interferometer length
                #
                #     pi_dur = self.kwargs['pi_dur']
                #     mw_freq = self.frequencies[0]
                #     tau = self.kwargs['tau']
                #     pihalf_dur =self.kwargs['pihalf_dur']
                #     eom_ampl = self.kwargs['eom_ampl']
                #     aom_Ex_dur = 0.009#0.02
                #     aom_delay = 0.151#0.137
                #     opt_pi_dur = 1201 * 1. / __SAMPLE_FREQUENCY__
                #     # tau determines the start of the MW pulse relative to start of the aom pulse
                #     # if aom_delay +aom_Ex_dur + optical_delay <tau < (aom_delay+aom_Ex_dur):
                #
                #     if tau< optical_delay+aom_Ex_dur:
                #         raise Exception('Tau is too short. must be greater than 76ns')
                #
                #
                #     if tau <= (aom_delay+aom_Ex_dur):
                #
                #         if tau+pi_dur>=(aom_delay+aom_Ex_dur):
                #             print(1)
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True,
                #                           name='gate1')  # 160ns Gated counter
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_1')  # 5 ns. AOM for the first pulse
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #                 name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - aom_Ex_dur-pihalf_dur),
                #                           name='wait_1.1')  # 37.3ns ns. Delay between first and second AOM_Ex pulses
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_2')  # 5 ns. AOM for the first puls
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau - (optical_delay+aom_Ex_dur)),
                #                           name='wait_2')
                #
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(aom_Ex_dur + aom_delay - tau),
                #                 name='MW_begin')  #
                #
                #             gauss1_begin = pi_dur - (aom_Ex_dur + aom_delay - tau)
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss_2_pulses',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #                 name='Gauss1_MW')  # First EOM Pulse
                #             already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss_2_pulses',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss1_begin),  #
                #                 name='Gauss1_end')
                #
                #
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #
                #         else:
                #             print(2)
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True,
                #                           name='gate1')  # 160ns Gated counter
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_1')  # 5 ns. AOM for the first pulse
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #                 name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - aom_Ex_dur - pihalf_dur),
                #                           name='wait_1.1')  # 37.3 ns. Delay between first and second AOM_Ex pulses
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_2')  # 5 ns. AOM for the first puls
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau - (optical_delay + aom_Ex_dur)),
                #                           name='wait_2')
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),
                #                 name='MW_pi')  # 13.5ns. First pi/2 pulse
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_Ex_dur +aom_delay - (tau+pi_dur)),
                #                           name='wait_3')
                #
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss_2_pulses',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #                 name='Gauss1')  # First EOM Pulse
                #
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #     elif (aom_delay+aom_Ex_dur + opt_pi_dur) > tau > (aom_delay+aom_Ex_dur): #0.155 to 0.255083333
                #         if tau + pi_dur < (aom_delay + aom_Ex_dur + opt_pi_dur): # tau <0.2280833333
                #             # THIS CASE IS USED
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True,
                #                           name='gate1')  # 160ns Gated counter
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_1')  # 5 ns. AOM for the first pulse
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #                 name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - aom_Ex_dur - pihalf_dur),
                #                           name='wait_1.1')  # 37.3ns ns. Delay between first and second AOM_Ex pulses
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_2')  # 5 ns. AOM for the first puls
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_delay - optical_delay),
                #                      name='aom_delay_wait')
                #
                #
                #             gauss1_begin = tau - (aom_delay+aom_Ex_dur)
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss_2_pulses',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #                 name='2Gauss')  # First EOM Pulse
                #             already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #
                #
                #             self.mcas.asc(
                #
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss_2_pulses',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(pi_dur),  #
                #                 name='2Gauss_MW')
                #             already_written_samples2 = np.around(pi_dur * __SAMPLE_FREQUENCY__).astype(int)
                #
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss_2_pulses',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples2+already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - (gauss1_begin + pi_dur)),  #
                #                 name='2Gauss_end')
                #
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #         else:
                #             print(4)
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True,
                #                           name='gate1')  # 160ns Gated counter
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_1')  # 5 ns. AOM for the first pulse
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #                 name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #
                #             # print(optical_delay)
                #             # print(aom_Ex_dur)
                #             # print(pihalf_dur)
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - aom_Ex_dur - pihalf_dur),
                #                           name='wait_1.1')  # 37.3ns ns. Delay between first and second AOM_Ex pulses
                #             self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                           name='Ex_aom_2')  # 5 ns. AOM for the first puls
                #
                #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_delay - optical_delay),
                #                      name='aom_delay_wait')
                #
                #
                #             gauss1_begin = tau - (aom_delay+aom_Ex_dur)
                #             self.mcas.asc(
                #                 pd2g2=dict(
                #                     type='gauss_2_pulses',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #                 length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #                 name='2Gauss')  # First EOM Pulse
                #             already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 pd2g2=dict(
                #                     type='gauss_2_pulses',
                #                     inv_fwhm=1,
                #                     amplitudes=[eom_ampl]),
                #
                #                 wf_start=already_written_samples,
                #                 length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss1_begin),  #
                #                 name='2Gauss_MW')
                #
                #
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pi_dur - (opt_pi_dur - gauss1_begin)),  #
                #                 name='MW_end')
                #
                #             self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #             self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #
                #
                #
                #     elif (aom_delay+aom_Ex_dur + opt_pi_dur) <= tau:
                #
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True,
                #                       name='gate1')  # 160ns Gated counter
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                       name='Ex_aom_1')  # 5 ns. AOM for the first pulse
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #             length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #             name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - aom_Ex_dur - pihalf_dur),
                #                       name='wait_1.1')  # 37.3ns ns. Delay between first and second AOM_Ex pulses
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                       name='Ex_aom_2')  # 5 ns. AOM for the first puls
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(aom_delay - optical_delay),
                #                       name='aom_delay_wait')
                #
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss_2_pulses',
                #                 inv_fwhm=1,
                #                 amplitudes=[eom_ampl]),
                #             length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #             name='2Gauss')  # First EOM Pulse
                #
                #         self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau - (aom_Ex_dur+aom_delay+opt_pi_dur)),
                #                       name='wait before MW')
                #
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(pi_dur),
                #             name='MW_pi')  # 13.5ns. First pi/2 pulse
                #
                #         self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #
                #
                #
                #
                #
                #     else:
                #         raise('smth is wrong tau is {}'.format(tau))
                #     # elif aom_delay +aom_Ex_dur + optical_delay <= tau <aom_delay +aom_Ex_dur + optical_delay +opt_pi_dur:
                #     #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #     #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #     #                   name='Ex_aom_1')  # 20 ns. AOM for the first pulse
                #     #     self.mcas.asc(length_mus=optical_delay - aom_Ex_dur,
                #     #                   name='wait_1.1')  # 36ns ns. Delay between first and second AOM_Ex pulses
                #     #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #     #                   name='Ex_aom_2')  # 20 ns. AOM for the first puls
                #     #     self.mcas.asc(length_mus=E.round_length_mus_full_sample(0.007), name='wait_1')  # 7ns
                #     #
                #     #     self.mcas.asc(
                #     #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #     #         length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #     #         name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #     #
                #     #     self.mcas.asc(length_mus=0.0605, name='wait_2')
                #     #     self.mcas.asc(
                #     #         pd2g2=dict(
                #     #             type='gauss',
                #     #             inv_fwhm=1,
                #     #             amplitudes=[eom_ampl]),
                #     #         length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #     #         name='Gauss1')  # First EOM Pulse
                #     #     self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - opt_pi_dur), name='wait_2')
                #     #
                #     #     gauss2_begin = tau - (aom_Ex_dur+aom_delay+optical_delay)
                #     #     self.mcas.asc(
                #     #         pd2g2=dict(
                #     #             type='gauss',
                #     #             inv_fwhm=1,
                #     #             amplitudes=[eom_ampl]),
                #     #         length_mus=E.round_length_mus_full_sample(gauss2_begin),
                #     #         name='Gauss2_begin')  # First EOM Pulse
                #     #     already_written_samples = np.around(gauss2_begin * __SAMPLE_FREQUENCY__).astype(int)
                #     #
                #     #     if tau + pi_dur <= aom_delay +aom_Ex_dur + optical_delay +opt_pi_dur:
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #
                #     #             wf_start=already_written_samples,
                #     #             length_mus=E.round_length_mus_full_sample(pi_dur),  #
                #     #             name='Gauss2_MW')
                #     #         already_written_samples+=np.around(pi_dur * __SAMPLE_FREQUENCY__).astype(int)
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #
                #     #             wf_start=already_written_samples,
                #     #             length_mus=E.round_length_mus_full_sample(opt_pi_dur - (gauss2_begin + pi_dur)),
                #     #             name='Gauss2_end')
                #     #
                #     #         self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #     #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #     #
                #     #     else:
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #             wf_start=already_written_samples,
                #     #             length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss2_begin),  #
                #     #             name='Gauss2_MW')
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             length_mus=E.round_length_mus_full_sample(pi_dur-(opt_pi_dur - gauss2_begin)),
                #     #             name='MW_end')
                #     #
                #     #         self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #     #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #     #
                #     # elif tau >= aom_delay + aom_Ex_dur + optical_delay + opt_pi_dur:
                #     #     # ---------------
                #     #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #     #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #     #                   name='Ex_aom_1')  # 20 ns. AOM for the first pulse
                #     #     self.mcas.asc(length_mus=optical_delay - aom_Ex_dur,
                #     #                   name='wait_1.1')  # 36ns ns. Delay between first and second AOM_Ex pulses
                #     #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #     #                   name='Ex_aom_2')  # 20 ns. AOM for the first puls
                #     #     self.mcas.asc(length_mus=E.round_length_mus_full_sample(0.007), name='wait_1')  # 7ns
                #     #     self.mcas.asc(
                #     #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #     #         length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #     #         name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #     #     self.mcas.asc(length_mus=0.0605, name='wait_2')
                #     #     self.mcas.asc(
                #     #         pd2g2=dict(
                #     #             type='gauss',
                #     #             inv_fwhm=1,
                #     #             amplitudes=[eom_ampl]),
                #     #         length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #     #         name='Gauss1')  # First EOM Pulse
                #     #
                #     #     self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - opt_pi_dur), name='wait_2')
                #     #
                #     #     self.mcas.asc(
                #     #         pd2g2=dict(
                #     #             type='gauss',
                #     #             inv_fwhm=1,
                #     #             amplitudes=[eom_ampl]),
                #     #         length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #     #         name='Gauss2')  # Second EOM Pulse
                #     #
                #     #     self.mcas.asc(length_mus=E.round_length_mus_full_sample(tau - ( aom_delay + aom_Ex_dur + optical_delay + opt_pi_dur)), name='wait_2')
                #     #
                #     #     self.mcas.asc(
                #     #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #         length_mus=E.round_length_mus_full_sample(pi_dur),
                #     #         name='MW_pi')  # 27ns
                #     #
                #     #     self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #     #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #     #
                #     # else:
                #     #     # !!!!!! THIS PART IS USED
                #     #
                #     #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #     #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #     #                   name='Ex_aom_1')  # 20 ns. AOM for the first pulse
                #     #     self.mcas.asc(length_mus=E.round_length_mus_full_sample(optical_delay - aom_Ex_dur),
                #     #                   name='wait_1.1')  # 36ns ns. Delay between first and second AOM_Ex pulses
                #     #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #     #                   name='Ex_aom_2')  # 20 ns. AOM for the first puls
                #     #     self.mcas.asc(length_mus=E.round_length_mus_full_sample(0.007), name='wait_1')  # 7ns
                #     #
                #     #     self.mcas.asc(
                #     #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #     #         length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #     #         name='MW_pihalf')  # 13.5ns. First pi/2 pulse
                #     #
                #     #     self.mcas.asc(length_mus=0.0605, name='wait_2')
                #     #
                #     #     if tau >= aom_delay + aom_Ex_dur and tau + pi_dur <= (aom_delay + aom_Ex_dur + opt_pi_dur):
                #     #
                #     #         gauss1_begin = tau - (aom_delay + aom_Ex_dur)
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #             length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #     #             name='Gauss1_begin')  # First EOM Pulse
                #     #         already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #
                #     #             wf_start=already_written_samples,
                #     #             length_mus=E.round_length_mus_full_sample(pi_dur),  #
                #     #             name='Gauss1_MW')
                #     #         already_written_samples += np.around(pi_dur * __SAMPLE_FREQUENCY__).astype(int)
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #
                #     #             wf_start=already_written_samples,
                #     #             length_mus=E.round_length_mus_full_sample(opt_pi_dur - pi_dur - gauss1_begin),  #
                #     #             name='Gauss1_end')
                #     #         self.mcas.asc(length_mus=optical_delay - opt_pi_dur,
                #     #                       name='wait_3')  # 14.5ns wait before second optical pi pulse
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #             length_mus=opt_pi_dur,  # 0.04008333333333333 ns Second EOM pulse starts
                #     #             name='Gauss2')
                #     #         self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #     #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #     #
                #     #     elif aom_delay + aom_Ex_dur < tau < aom_delay + aom_Ex_dur +opt_pi_dur \
                #     #             and aom_delay + aom_Ex_dur +optical_delay>=tau + pi_dur > (aom_delay + aom_Ex_dur + opt_pi_dur):
                #     #         gauss1_begin = tau - (aom_delay + aom_Ex_dur)
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #             length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #     #             name='Gauss1_begin')  # First EOM Pulse
                #     #         already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #
                #     #             wf_start=already_written_samples,
                #     #             length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss1_begin),  #
                #     #             name='Gauss1_MW')
                #     #
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             length_mus=E.round_length_mus_full_sample(pi_dur - (opt_pi_dur - gauss1_begin)),  #
                #     #             name='MW_end')
                #     #
                #     #         self.mcas.asc(length_mus=optical_delay - (opt_pi_dur+pi_dur - (opt_pi_dur - gauss1_begin)),
                #     #                       name='wait_3')  # 14.5ns wait before second optical pi pulse
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #             length_mus=opt_pi_dur,  # 0.04008333333333333 ns Second EOM pulse starts
                #     #             name='Gauss2')
                #     #         self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #     #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #     #
                #     #     elif aom_delay + aom_Ex_dur < tau < aom_delay + aom_Ex_dur +opt_pi_dur \
                #     #             and aom_delay + aom_Ex_dur +optical_delay < tau + pi_dur:
                #     #         # !!!!!! THIS PART IS USED
                #     #
                #     #         gauss1_begin = tau - (aom_delay + aom_Ex_dur)
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #             length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #     #             name='Gauss1_begin')  # First EOM Pulse
                #     #         already_written_samples = np.around(gauss1_begin * __SAMPLE_FREQUENCY__).astype(int)
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #
                #     #             wf_start=already_written_samples,
                #     #             length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss1_begin),  #
                #     #             name='Gauss1_MW')
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             length_mus=E.round_length_mus_full_sample(optical_delay - opt_pi_dur),  #
                #     #             name='MW')
                #     #
                #     #         gauss2_begin =E.round_length_mus_full_sample(pi_dur - (opt_pi_dur - gauss1_begin + optical_delay - opt_pi_dur))
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #             length_mus=gauss2_begin,  # 0.04008333333333333 ns Second EOM pulse starts
                #     #             name='Gauss2_MW')
                #     #         already_written_samples = np.around(gauss2_begin * __SAMPLE_FREQUENCY__).astype(int)
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #
                #     #             wf_start=already_written_samples,
                #     #             length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss2_begin),  #
                #     #             name='Gauss2_end')
                #     #
                #     #
                #     #
                #     #         if 'tau_bell' in self.kwargs.keys():
                #     #             self.mcas.asc(length_mus=E.round_length_mus_full_sample(0.075917),
                #     #                           name='wait_before_MW')  # 100ns
                #     #             tau_bell = self.kwargs['tau_bell']
                #     #             self.mcas.asc(
                #     #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_pihalf_ampl]),
                #     #                 length_mus=E.round_length_mus_full_sample(tau_bell),
                #     #                 name='tau bell')  # 13.5ns. First pi/2 pulse
                #     #
                #     #
                #     #
                #     #
                #     #
                #     #         self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #     #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                #     #
                #     #     elif aom_delay + aom_Ex_dur + optical_delay > tau > aom_delay + aom_Ex_dur + opt_pi_dur :
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #             length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #     #             name='Gauss1_begin')  # First EOM Pulse
                #     #
                #     #         self.mcas.asc(length_mus=tau - (aom_delay + aom_Ex_dur + opt_pi_dur),
                #     #                       name='wait_3')  # 14.5ns wait before second optical pi pulse
                #     #
                #     #         # pd2g1 = dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             length_mus=E.round_length_mus_full_sample(aom_delay + aom_Ex_dur + optical_delay - tau),  #
                #     #             name='MW_end')
                #     #
                #     #         gauss2_begin = pi_dur - (aom_delay + aom_Ex_dur + optical_delay - tau)
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #             length_mus=gauss2_begin,  # 0.04008333333333333 ns Second EOM pulse starts
                #     #             name='Gauss2_MW')
                #     #         already_written_samples = np.around(gauss2_begin * __SAMPLE_FREQUENCY__).astype(int)
                #     #
                #     #         self.mcas.asc(
                #     #             pd2g2=dict(
                #     #                 type='gauss',
                #     #                 inv_fwhm=1,
                #     #                 amplitudes=[eom_ampl]),
                #     #
                #     #             wf_start=already_written_samples,
                #     #             length_mus=E.round_length_mus_full_sample(opt_pi_dur - gauss2_begin),  #
                #     #             name='Gauss')
                #     #
                #     #         self.mcas.asc(length_mus=self.laser_dur, name='wait_before_memory')  # 100ns
                #     #         self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')  # 160ns
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == '2opt_withMW_pi':
                #     pi_dur = self.kwargs['pi_dur']
                #     mw_amplitude = self.kwargs['mw_amplitude']
                #     mw_freq = self.frequencies[0]
                #     mw_delay = self.kwargs['mw_delay']#delay betweenn first optical pulse and MW pulse (measured from aom_Ex open)
                #     optical_delay = self.kwargs['optical_delay'] #delay between optical pulses aka interferometer length
                #     aom_Ex_dur = 0.015#0.02
                #     aom_delay = 0.155#0.137
                #     opt_pi_dur = 481 * 1. / __SAMPLE_FREQUENCY__
                #
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter
                #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_1')
                #     self.mcas.asc(length_mus=optical_delay - aom_Ex_dur, name='wait_1')
                #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_2')
                #     self.mcas.asc(length_mus=aom_delay-aom_Ex_dur-(optical_delay - aom_Ex_dur), name='wait_2')
                #
                #
                #     self.mcas.asc(
                #         pd2g2=dict(
                #             type='gauss',
                #             inv_fwhm=1,
                #             amplitudes=[self.kwargs['eom_ampl']]),
                #         length_mus=E.round_length_mus_full_sample(mw_delay-aom_Ex_dur-aom_delay),
                #         name='Gauss1')
                #
                #     already_written_samples = np.around((mw_delay-aom_Ex_dur-aom_delay) * __SAMPLE_FREQUENCY__).astype(int)
                #     remaining_optical = opt_pi_dur - (mw_delay-aom_Ex_dur-aom_delay)
                #     self.mcas.asc(
                #         pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #         wf_start=already_written_samples,
                #
                #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #         length_mus=remaining_optical,
                #         name='Gauss1_MW')
                #
                #     self.mcas.asc(
                #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #         length_mus=E.round_length_mus_full_sample(pi_dur - remaining_optical),
                #         name='MW_pi_residual')
                #
                #     self.mcas.asc(length_mus=optical_delay+aom_Ex_dur+aom_delay-(mw_delay+pi_dur), name='wait_3')
                #     self.mcas.asc(
                #         pd2g2=dict(
                #             type='gauss',
                #             inv_fwhm=1,
                #             amplitudes=[self.kwargs['eom_ampl']]),
                #         length_mus=481 * 1. / __SAMPLE_FREQUENCY__,
                #         name='Gauss2')
                #
                #     self.mcas.asc(length_mus=self.laser_dur,name='wait_4')
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory')
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'entanglement_for_tests':
                #
                #     eom_ampl = self.kwargs['eom_ampl']
                #
                #
                #
                #     pihalf_dur =self.kwargs['pihalf_dur'] #0.0135
                #     hahn_echo_tau = 0.075 # temp thing to make pi instead of first pi/2
                #
                #     pi_dur = self.kwargs['pi_dur'] #0.027
                #     mw_amplitude = self.kwargs['mw_amplitude']
                #     mw_freq = self.frequencies[0]
                #     mw_delay = self.kwargs['mw_delay']#213ns (was 180ns) delay betweenn first optical pulse and MW pulse (measured from aom_Ex open)
                #     optical_delay = self.kwargs['optical_delay'] #56ns (was 125ns) delay between optical pulses aka interferometer length
                #
                #     aom_Ex_dur = 0.02#0.02
                #     aom_delay = 0.137#0.137
                #     opt_pi_dur = 481 * 1. / __SAMPLE_FREQUENCY__
                #     gauss1_begin = (optical_delay - pi_dur) / 2 #14.5ns - time between first opt pi begin and mw pi begin
                #     remaining_optical = opt_pi_dur - (gauss1_begin) # 0.025583333333333333 ns
                #     remaining_mw_dur = pi_dur - remaining_optical
                #     wait2 = hahn_echo_tau-gauss1_begin # 60.5ns
                #
                #     wait1 = 0.007 # 0.007000000000000018 ns delay between second aom_Ex and MW pi/2
                #     wait2 = aom_delay - (optical_delay-aom_Ex_dur) - aom_Ex_dur - wait1 - pihalf_dur
                #
                #
                #     # wait3 = gauss1_begin #14.5ns
                #     wait4 = hahn_echo_tau-gauss1_begin-opt_pi_dur #0.020416666666666666
                #
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #
                #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_1')  #20 ns. AOM for the first pulse
                #
                #     self.mcas.asc(length_mus=optical_delay-aom_Ex_dur, name='wait_1.1')# 36ns ns. Delay between first and second AOM_Ex pulses
                #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True,
                #                   name='Ex_aom_2')  # 20 ns. AOM for the first puls
                #
                #     self.mcas.asc(length_mus=E.round_length_mus_full_sample(0.007), name='wait_1') #7ns
                #
                #
                #     self.mcas.asc(
                #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #         length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #         name='MW_pihalf')#13.5ns. First pi/2 pulse
                #
                #     self.mcas.asc(length_mus=0.0605, name='wait_2')
                #
                #     self.mcas.asc(
                #         pd2g2=dict(
                #             type='gauss',
                #             inv_fwhm=1,
                #             amplitudes=[eom_ampl]),
                #         length_mus=E.round_length_mus_full_sample(opt_pi_dur),
                #         name='Gauss1') #14.5 ns. First EOM Pulse
                #
                #
                #     self.mcas.asc(length_mus=optical_delay - opt_pi_dur, name='wait_3') #14.5ns wait before second optical pi pulse
                #
                #
                #     self.mcas.asc(
                #         pd2g2=dict(
                #             type='gauss',
                #             inv_fwhm=1,
                #             amplitudes=[eom_ampl]),
                #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #
                #         length_mus=pi_dur, # 0.04008333333333333 ns Second EOM pulse starts
                #         name='Gauss2_MW')
                #
                #     already_written_samples = np.around(pi_dur * __SAMPLE_FREQUENCY__).astype(int)
                #
                #     self.mcas.asc(
                #         pd2g2=dict(
                #             type='gauss',
                #             inv_fwhm=1,
                #             amplitudes=[eom_ampl]),
                #
                #         wf_start = already_written_samples,
                #         length_mus=opt_pi_dur-pi_dur, # 0.013083333333333332 ns Second EOM pulse starts
                #         name='Gauss2end')
                #
                #
                #     self.mcas.asc(length_mus= 0.1165 - (opt_pi_dur-pi_dur), name='wait4')#111.91666666666664 ns
                #
                #     if 'tau_bell' in self.kwargs.keys():
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq,
                #                        amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(self.kwargs['tau_bell']),
                #             name='tau_bell')  # 14.5ns. Second pi/2 pulse
                #
                #
                #     self.mcas.asc(length_mus=self.laser_dur,name='wait_before_memory') #100ns
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory') #160ns
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'entanglement':
                #     pihalf_dur =self.kwargs['pihalf_dur'] #0.0135
                #     hahn_echo_tau = 0.075 # self.kwargs['hahn_echo_tau'] #373ns
                #
                #     pi_dur = self.kwargs['pi_dur'] #0.027
                #     mw_amplitude = self.kwargs['mw_amplitude']
                #     mw_freq = self.frequencies[0]
                #     mw_delay = self.kwargs['mw_delay']#190ns (was 180ns) delay betweenn first optical pulse and MW pulse (measured from aom_Ex open)
                #     optical_delay = self.kwargs['optical_delay'] #56ns (was 125ns) delay between optical pulses aka interferometer length
                #
                #     aom_Ex_dur = 0.02#0.02
                #     aom_delay = 0.137#0.137
                #     opt_pi_dur = 481 * 1. / __SAMPLE_FREQUENCY__
                #     gauss1_begin = (optical_delay - pi_dur) / 2 #14.5ns - time between first opt pi begin and mw pi begin
                #     remaining_optical = opt_pi_dur - (gauss1_begin) # 0.025583333333333333 ns
                #     remaining_mw_dur = pi_dur - remaining_optical
                #     wait2 = hahn_echo_tau-gauss1_begin # 60.5ns
                #     wait1 = aom_delay-optical_delay-wait2-pihalf_dur # 0.007000000000000018 ns delay between second aom_Ex and MW pi/2
                #     wait3 = gauss1_begin #14.5ns
                #     wait4 = hahn_echo_tau-gauss1_begin-opt_pi_dur #0.020416666666666666
                #
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_1')  #20 ns. AOM for the first pulse
                #     self.mcas.asc(length_mus=optical_delay-aom_Ex_dur, name='wait_1.1')# 56ns ns. Delay between first and second AOM_Ex pulses
                #     self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_2')  #20 ns. AOM for the first puls
                #
                #     self.mcas.asc(length_mus=E.round_length_mus_full_sample(wait1), name='wait_1') #7ns
                #
                #
                #     self.mcas.asc(
                #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #         length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #         name='MW_pihalf')#13.5ns. First pi/2 pulse
                #
                #     self.mcas.asc(length_mus=wait2, name='wait_2')
                #
                #
                #
                #
                #     self.mcas.asc(
                #         pd2g2=dict(
                #             type='gauss',
                #             inv_fwhm=1,
                #             amplitudes=[self.kwargs['eom_ampl']]),
                #         length_mus=E.round_length_mus_full_sample(gauss1_begin),
                #         name='Gauss1_begin') #14.5 ns. First EOM Pulse
                #
                #     already_written_samples = np.around((gauss1_begin) * __SAMPLE_FREQUENCY__).astype(int) # 174samples
                #     self.mcas.asc(
                #         pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #         wf_start=already_written_samples,
                #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #         length_mus=remaining_optical, #0.025583333333333333 ns. MW pi starts, first optical pi finishes
                #         name='Gauss1_end_MW')
                #
                #     self.mcas.asc(
                #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #         length_mus=E.round_length_mus_full_sample(remaining_mw_dur), # 00.0014166666666666668 MW pi ends
                #         name='remaining_mw')
                #
                #     self.mcas.asc(length_mus=wait3, name='wait_3') #14.5ns wait before second optical pi pulse
                #
                #
                #     self.mcas.asc(
                #         pd2g2=dict(
                #             type='gauss',
                #             inv_fwhm=1,
                #             amplitudes=[self.kwargs['eom_ampl']]),
                #
                #         length_mus=opt_pi_dur, # 0.04008333333333333 ns Second EOM pulse starts
                #         name='Gauss2')
                #
                #
                #     self.mcas.asc(length_mus=wait4, name='wait4')#111.91666666666664 ns
                #
                #     if 'readout_state' in self.kwargs.keys():
                #         if self.kwargs['readout_state']:
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(3*pihalf_dur),
                #                 name='_MW_3pihalf_2')  # 43.5ns. Second pi/2 pulse
                #         else:
                #             self.mcas.asc(
                #                 pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #                 length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #                 name='_MW_pihalf_2')  # 14.5ns. Second pi/2 pulse
                #
                #     else:
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #             name='MW_pihalf_2')  # 14.5ns. Second pi/2 pulse
                #
                #     self.mcas.asc(length_mus=self.laser_dur,name='wait_before_memory') #100ns
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory') #160ns
                #
                #
                #
                #     # pihalf_dur =self.kwargs['pihalf_dur'] #0.0135
                #     # hahn_echo_tau = 0.148 # self.kwargs['hahn_echo_tau'] #373ns
                #     #
                #     # pi_dur = self.kwargs['pi_dur'] #0.027
                #     # mw_amplitude = self.kwargs['mw_amplitude']
                #     # mw_freq = self.frequencies[0]
                #     # mw_delay = self.kwargs['mw_delay']#190ns (was 180ns) delay betweenn first optical pulse and MW pulse (measured from aom_Ex open)
                #     # optical_delay = self.kwargs['optical_delay'] #56ns (was 125ns) delay between optical pulses aka interferometer length
                #     #
                #     # aom_Ex_dur = 0.015#0.02
                #     # aom_delay = 0.155#0.137
                #     # opt_pi_dur = 481 * 1. / __SAMPLE_FREQUENCY__
                #     #
                #     # self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #     # self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_1') #15 ns. AOM for the first pulse
                #     #
                #     #
                #     #
                #     #
                #     # #wait1_2 = hahn echo delay - Gauss1_begin - wait2 - Ex_aom_2 ##Names of blocks below
                #     # wait1_2 = hahn_echo_tau-(E.round_length_mus_full_sample(mw_delay-aom_Ex_dur-aom_delay))-(aom_delay-(optical_delay - aom_Ex_dur)-aom_Ex_dur)-aom_Ex_dur
                #     # # wait1_1 = delay_between_two_aoms - wait1_2 -pihalf_dur
                #     # wait1_1 = (optical_delay-aom_Ex_dur)-wait1_2 -pihalf_dur
                #     #
                #     # self.mcas.asc(length_mus=wait1_1, name='wait_1.1')# 13.5 ns. Delay between first AOM_Ex pulse and MW pi/2
                #     # self.mcas.asc(
                #     #     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #     length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #     #     name='MW_pihalf_1')#13.5ns. First pi/2 pulse
                #     # self.mcas.asc(length_mus=wait1_2, name='wait_1.2')#14 ns. Delay between MW pi/2 and the second AOM_Ex pulse
                #     #
                #     #
                #     #
                #     #
                #     # self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_2') #15 ns. The second AOM pulse
                #     # self.mcas.asc(length_mus=aom_delay-(optical_delay - aom_Ex_dur)-aom_Ex_dur, name='wait_2') #99ns
                #     #
                #     # self.mcas.asc(
                #     #     pd2g2=dict(
                #     #         type='gauss',
                #     #         inv_fwhm=1,
                #     #         amplitudes=[self.kwargs['eom_ampl']]),
                #     #     length_mus=E.round_length_mus_full_sample(mw_delay-aom_Ex_dur-aom_delay),
                #     #     name='Gauss1_begin') #20ns. First EOM Pulse
                #     #
                #     # already_written_samples = np.around((mw_delay-aom_Ex_dur-aom_delay) * __SAMPLE_FREQUENCY__).astype(int)
                #     # remaining_optical = opt_pi_dur - (mw_delay-aom_Ex_dur-aom_delay) # 20.083333333333342 ns
                #     # self.mcas.asc(
                #     #     pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #     #     wf_start=already_written_samples,
                #     #
                #     #     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #     length_mus=remaining_optical, #20.083333333333342 ns. MW pi starts, first optical pi finishes
                #     #     name='Gauss1_end_MW')
                #     # # print ('remaining_optical ',remaining_optical)
                #     # self.mcas.asc(
                #     #     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #     length_mus=E.round_length_mus_full_sample(pi_dur - remaining_optical), # 6.920000000000002 ???? for some reason was written this: 8.91666666666666ns MW pi finishes
                #     #     name='MW_pi_residual')
                #     # wait3_1 = optical_delay+aom_Ex_dur+aom_delay-(mw_delay+pi_dur)
                #     # self.mcas.asc(length_mus=wait3_1, name='wait_3_1') #9ns for some reason was written 7ns
                #     # self.mcas.asc(
                #     #     pd2g2=dict(
                #     #         type='gauss',
                #     #         inv_fwhm=1,
                #     #         amplitudes=[self.kwargs['eom_ampl']]),
                #     #     length_mus=481 * 1. / __SAMPLE_FREQUENCY__, #40ns. Second EOM pulse
                #     #     name='Gauss2')
                #     #
                #     # wait3_2 = hahn_echo_tau - wait3_1 - opt_pi_dur
                #     # self.mcas.asc(length_mus=wait3_2, name='wait3_2')#98.917ns
                #     #
                #     # if 'readout_state' in self.kwargs.keys():
                #     #     if self.kwargs['readout_state']:
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             length_mus=E.round_length_mus_full_sample(3*pihalf_dur),
                #     #             name='_MW_3pihalf_2')  # 14.5ns. Second pi/2 pulse
                #     #     else:
                #     #         self.mcas.asc(
                #     #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #             length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #     #             name='_MW_pihalf_2')  # 14.5ns. Second pi/2 pulse
                #     #
                #     # else:
                #     #     self.mcas.asc(
                #     #         pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #         length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #     #         name='MW_pihalf_2')  # 14.5ns. Second pi/2 pulse
                #     #
                #     # self.mcas.asc(length_mus=self.laser_dur,name='wait_4') #100ns
                #     # self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory') #160ns
                #
                #     # self.mcas.asc(
                #     #     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #     length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #     #     name='MW_pihalf_1',
                #     # )
                #     # self.mcas.asc(length_mus=0.033, name='wait_0')# 33.5ns
                #     # self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #     # self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_1') #20ns
                #     # self.mcas.asc(length_mus=optical_delay - aom_Ex_dur, name='wait_1')#105ns
                #     # self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_2')#20ns
                #     # self.mcas.asc(length_mus=aom_delay-aom_Ex_dur-(optical_delay - aom_Ex_dur), name='wait_2') #12ns
                #     #
                #     #
                #     # self.mcas.asc(
                #     #     pd2g2=dict(
                #     #         type='gauss',
                #     #         inv_fwhm=1,
                #     #         amplitudes=[self.kwargs['eom_ampl']]),
                #     #     length_mus=E.round_length_mus_full_sample(mw_delay-aom_Ex_dur-aom_delay), #23ns
                #     #     name='Gauss1')
                #     #
                #     # already_written_samples = np.around((mw_delay-aom_Ex_dur-aom_delay) * __SAMPLE_FREQUENCY__).astype(int)
                #     # remaining_optical = opt_pi_dur - (mw_delay-aom_Ex_dur-aom_delay) #17ns
                #     # self.mcas.asc(
                #     #     pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #     #     wf_start=already_written_samples,
                #     #
                #     #     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #     length_mus=remaining_optical, #17ns
                #     #     name='Gauss1_MW')
                #     #
                #     # self.mcas.asc(
                #     #     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #     length_mus=E.round_length_mus_full_sample(pi_dur - remaining_optical), #12ns
                #     #     name='MW_pi_residual')
                #     #
                #     # self.mcas.asc(length_mus=optical_delay+aom_Ex_dur+aom_delay-(mw_delay+pi_dur), name='wait_3') #73ns
                #     # self.mcas.asc(
                #     #     pd2g2=dict(
                #     #         type='gauss',
                #     #         inv_fwhm=1,
                #     #         amplitudes=[self.kwargs['eom_ampl']]),
                #     #     length_mus=481 * 1. / __SAMPLE_FREQUENCY__, #40ns
                #     #     name='Gauss2')
                #     #
                #     # self.mcas.asc(length_mus=self.laser_dur,name='wait_4') #100ns
                #     # self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory') #160ns
                #     # self.mcas.asc(
                #     #     pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #     #     length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #     #     name='MW_pihalf_2',
                #     # )
                # elif 'nuc' in self.kwargs.keys() and self.kwargs['nuc'] == 'HOM':
                #
                #     pihalf_dur =self.kwargs['pihalf_dur']
                #     hahn_echo_tau = 0.148#self.kwargs['hahn_echo_tau'] #373ns
                #
                #     pi_dur = self.kwargs['pi_dur']
                #     mw_amplitude = self.kwargs['mw_amplitude']
                #     mw_freq = self.frequencies[0]
                #     mw_delay = self.kwargs['mw_delay']#190ns (was 180ns) delay betweenn first optical pulse and MW pulse (measured from aom_Ex open)
                #     optical_delay = self.kwargs['optical_delay'] #56ns (was 125ns) delay between optical pulses aka interferometer length
                #
                #     aom_Ex_dur = 0.015#0.02
                #     aom_delay = 0.155#0.137
                #     opt_pi_dur = 481 * 1. / __SAMPLE_FREQUENCY__
                #
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # 160ns Gated counter
                #
                #     for i in range(self.kwargs['n_repetitions']):
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_1') #15 ns. AOM for the first pulse
                #
                #         #wait1_2 = hahn echo delay - Gauss1_begin - wait2 - Ex_aom_2 ##Names of blocks below
                #         wait1_2 = hahn_echo_tau-(E.round_length_mus_full_sample(mw_delay-aom_Ex_dur-aom_delay))-(aom_delay-(optical_delay - aom_Ex_dur)-aom_Ex_dur)-aom_Ex_dur
                #         # wait1_1 = delay_between_two_aoms - wait1_2 -pihalf_dur
                #         wait1_1 = (optical_delay-aom_Ex_dur)-wait1_2 -pihalf_dur
                #
                #         self.mcas.asc(length_mus=wait1_1, name='wait_1.1')# ns. Delay between first AOM_Ex pulse and MW pi/2
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(pihalf_dur),
                #             name='MW_pihalf_1')#14.5ns. First pi/2 pulse
                #         self.mcas.asc(length_mus=wait1_2, name='wait_1.2')#14 ns. Delay between MW pi/2 and the second AOM_Ex pulse
                #
                #         self.mcas.asc(length_mus=aom_Ex_dur, aom_Ex=True, name='Ex_aom_2') #15 ns. The second AOM pulse
                #         self.mcas.asc(length_mus=aom_delay-(optical_delay - aom_Ex_dur)-aom_Ex_dur, name='wait_2') #99ns
                #
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[self.kwargs['eom_ampl']]),
                #             length_mus=E.round_length_mus_full_sample(mw_delay-aom_Ex_dur-aom_delay),
                #             name='Gauss1_begin') #20ns. First EOM Pulse
                #
                #         already_written_samples = np.around((mw_delay-aom_Ex_dur-aom_delay) * __SAMPLE_FREQUENCY__).astype(int)
                #         remaining_optical = opt_pi_dur - (mw_delay-aom_Ex_dur-aom_delay) # 20.083333333333342 ns
                #         self.mcas.asc(
                #             pd2g2=dict(type='gauss', inv_fwhm=1, amplitudes=[self.kwargs['eom_ampl']]),
                #             wf_start=already_written_samples,
                #
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=remaining_optical, #20.083333333333342 ns. MW pi starts, first optical pi finishes
                #             name='Gauss1_end_MW')
                #         # print ('remaining_optical ',remaining_optical)
                #         self.mcas.asc(
                #             pd2g1=dict(type='sine', frequencies=mw_freq, amplitudes=[mw_amplitude]),
                #             length_mus=E.round_length_mus_full_sample(pi_dur - remaining_optical), # 8.91666666666666ns MW pi finishes
                #             name='MW_pi_residual')
                #         wait3_1 = optical_delay+aom_Ex_dur+aom_delay-(mw_delay+pi_dur)
                #         self.mcas.asc(length_mus=wait3_1, name='wait_3_1') #7ns
                #         self.mcas.asc(
                #             pd2g2=dict(
                #                 type='gauss',
                #                 inv_fwhm=1,
                #                 amplitudes=[self.kwargs['eom_ampl']]),
                #             length_mus=481 * 1. / __SAMPLE_FREQUENCY__, #40ns. Second EOM pulse
                #             name='Gauss2')
                #         self.mcas.asc(length_mus=0.1, name='wait3_2')
                #
                #
                #     self.mcas.asc(length_mus=self.laser_dur,name='wait_4') #100ns
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True, name='memory') #160ns

                ### ===============================
                ### Conventional repetitive readout
                ### ===============================
                else:
                    # print('snipets_else')
                    self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, gate=True, name='gate1')  # Gated counter

                    self.mcas.asc(length_mus=self.dur_step[alt_step][5], green=True, name='Laser', **aa)

                self.mcas.asc(length_mus=self.dur_step[alt_step][6], name='Count', **aa)

                # if self.gate_or_trigger != 'trigger':
                #     print('self.gate_or_trigger != trigger')
                #     pass
                #     self.mcas.asc(length_mus=__TT_TRIGGER_LENGTH__, memory=True)

                if 'buffer_time' in self.kwargs.keys():
                    self.mcas.asc(length_mus=self.kwargs['buffer_time'], name = 'Buffer')




def ssr(mcas,queue,**kwargs):
    s = SSR(mcas = mcas, queue=queue, **kwargs)
    s.compile()
    if not kwargs.get("discard",False):
        if not 'step_idx' in kwargs : #I know this is horrible coding. fix it if you have time
            raise Exception('SSR step index must be given, or the gated counter wont know how to readout and treat the data.')
        if kwargs['step_idx'] is not None:
            queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][3] = s.repetitions * s.number_of_alternating_steps
            queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][5] = s.number_of_alternating_steps
            if queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][5] != 1 and queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][2] == 'auto':
                queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][2] = 0

def protected_ssr(mcas,queue,**kwargs):
    s = SSR(mcas = mcas, queue=queue,protected_readout=True, **kwargs)
    s.compile()
    if not kwargs.get("discard",False):
        if not 'step_idx' in kwargs : #I know this is horrible coding. fix it if you have time
            raise Exception('SSR step index must be given, or the gated counter wont know how to readout and treat the data.')
        if kwargs['step_idx'] is not None:
            queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][3] = s.repetitions * s.number_of_alternating_steps
            queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][5] = s.number_of_alternating_steps
            if queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][5] != 1 and queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][2] == 'auto':
                queue._gated_counter.trace.analyze_sequence[kwargs['step_idx']][2] = 0

def long_ssr(mcas,queue,**kwargs):
    pass


def wait(mcas,total_wait,segment_length= 20 ):
        loops, correction_mus = shared.calculate_loop_count(total_wait, segment_length)
        # print("loops:", loops)
        if loops != 0:
            mcas.start_new_segment(name='wait', loop_count=loops)
            mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(segment_length))

        mcas.start_new_segment(name='wait', loop_count=1)
        mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(correction_mus))

def wait_no_new_segment(mcas,total_wait,**kwargs):
        print(kwargs)
        mcas.asc(name="wait",length_mus=E.round_length_mus_to_x_multiple_ps(total_wait),**kwargs)

        

wfpd_standard = collections.OrderedDict(
    [
        ('+++',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h01m45s17crot10_20_30_t10.00n80FN5.32e-01\\MW.dat'),
        ('++-',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h02m45s50crot10_20_31_t10.00n80FN5.29e-01\\MW.dat'),
        ('+-+',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h03m46s26crot10_21_30_t10.00n80FN5.11e-01\\MW.dat'),
        ('+--',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h04m46s59crot10_21_31_t10.00n80FN5.26e-01\\MW.dat'),
        ('0++',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h05m47s31crot11_20_30_t10.00n80FN5.26e-01\\MW.dat'),
        ('0+-',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h06m48s06crot11_20_31_t10.00n80FN5.13e-01\\MW.dat'),
        ('0-+',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h07m48s50crot11_21_30_t10.00n80FN5.21e-01\\MW.dat'),
        ('0--',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h08m49s23crot11_21_31_t10.00n80FN5.38e-01\\MW.dat'),
        ('-++',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h09m49s58crot12_20_30_t10.00n80FN5.15e-01\\MW.dat'),
        ('-+-',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h10m50s29crot12_20_31_t10.00n80FN5.11e-01\\MW.dat'),
        ('--+',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h11m50s58crot12_21_30_t10.00n80FN5.23e-01\\MW.dat'),
        ('---',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h12m51s29crot12_21_31_t10.00n80FN5.33e-01\\MW.dat'),
        ('nn+',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h14m18s27crot1012_201_30_t10.00n100FN1.24e+00\\MW.dat'),
        ('+',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h14m41s19crot10_t1.00n100FN6.57e-02\\MW.dat'),
        ('n+',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h14m43s07crot1012_20_t2.50n100FN7.63e-01\\MW.dat'),
        ('nn-',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h14m49s43crot1012_201_31_t10.00n100FN1.24e+00\\MW.dat'),
        ('n-',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h15m43s39crot1012_21_t2.50n100FN7.75e-01\\MW.dat'),
        ('0',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h19m13s56crot11_t1.00n100FN7.75e-02\\MW.dat'),
        ('-',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h21m14s57crot12_t1.00n100FN5.70e-02\\MW.dat')
    ]
)

wfpd_all_but_standard = collections.OrderedDict(
    [
        ('+++',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h01m45s11crotall_but10_20_30_t10.00n80FN5.10e-01\\MW.dat'),
        ('++-',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h02m45s47crotall_but10_20_31_t10.00n80FN5.10e-01\\MW.dat'),
        ('+-+',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h03m46s19crotall_but10_21_30_t10.00n80FN5.09e-01\\MW.dat'),
        ('+--',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h04m46s54crotall_but10_21_31_t10.00n80FN5.09e-01\\MW.dat'),
        ('0++',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h05m47s27crotall_but11_20_30_t10.00n80FN5.11e-01\\MW.dat'),
        ('0+-',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h06m48s04crotall_but11_20_31_t10.00n80FN5.10e-01\\MW.dat'),
        ('0-+',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h07m48s36crotall_but11_21_30_t10.00n80FN5.10e-01\\MW.dat'),
        ('0--',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h08m49s05crotall_but11_21_31_t10.00n80FN5.10e-01\\MW.dat'),
        ('-++',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h09m49s33crotall_but12_20_30_t10.00n80FN5.09e-01\\MW.dat'),
        ('-+-',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h10m49s59crotall_but12_20_31_t10.00n80FN5.09e-01\\MW.dat'),
        ('--+',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h11m50s26crotall_but12_21_30_t10.00n80FN5.09e-01\\MW.dat'),
        ('---',
        '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssrn80\\20180825-h12m50s55crotall_but12_21_31_t10.00n80FN5.10e-01\\MW.dat'),
        ('+',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h15m41s54crotall_but10_t1.00n100FN3.81e-02\\MW.dat'),
        ('0',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h20m14s30crotall_but11_t1.00n100FN7.12e-02\\MW.dat'),
        ('-',
         '\\\\PI3-PC161\\d\\Python\\pi3diamond\\UserScripts\\Robust\\pulses_ssr\\pulses_ssr_single_spin\\batch3\\20180902-h21m52s06crotall_but12_t1.00n100FN5.34e-02\\MW.dat')
    ]
)

# def ssr_single_state(mcas, state, **kwargs):
#     if (len(state) == 1 and state !='qutrit') or len(state) == len(state.lstrip('n')) == 3:
#         wave_file_kwargs = kwargs.pop(
#             'wave_file_kwargs',
#             [
#                 dict(
#                     filepath=kwargs.get('wfpd', wfpd_standard)[state],
#                     rp=pi3d.tt.rp('e_rabi', mixer_deg=-90)
#                 ),
#                 dict(
#                     filepath=kwargs.get('wfpd_all_but', wfpd_all_but_standard)[state],
#                     rp=pi3d.tt.rp('e_rabi', mixer_deg=-90)
#                 ),
#             ]
#         )
#         if (len(state) == 1 and state !='qutrit'):
#             nuc = '14n'
#         else:
#             nuc = '13c90'
#     else:
#         if state == 'qutrit':
#             nuc = '14n'
#             wfksl = ['+', '0', '-']
#         else:
#             nuc = '13c414' if len(state) == 2 else '13c90'
#             wfksl = [state.lstrip('n')]
#             wfksl.append({'+': '-', '-': '+'}[wfksl[0]])
#         if 'wave_file_kwargs' in kwargs:
#             wave_file_kwargs = kwargs.pop('wave_file_kwargs')
#         else:
#             wave_file_kwargs =[
#                 dict(
#                     filepath=kwargs.get('wfpd', wfpd_standard)[wfks],
#                     rp=pi3d.tt.rp('e_rabi', mixer_deg=-90)
#                 ) for wfks in wfksl]
#     ssr(mcas,
#         transition='left',
#         robust=True,
#         laser_dur=kwargs.pop('laser_dur', __LASER_DUR_DICT__.get(state, __LASER_DUR_DICT__['single_state'])),
#         mixer_deg=-90,
#         nuc=kwargs.pop('nuc', nuc),
#         frequencies=kwargs.pop('frequencies', [pi3d.tt.mfl({'14n': [0]}) for i in range(len(wave_file_kwargs))]),
#         wave_file_kwargs=wave_file_kwargs, **kwargs
#     )


# def DDRF(mcas,
#          global_mw_phase,
#          second_mw_phase,
#          rf_phase_increment,
#          rotation_axis,
#          pi_dur,
#          pi2_dur,
#          detuning,
#          bath_freq,
#          tau,
#          n_rep_ddrf,
#          ddrft,
#          mw_freq,
#          mw_amp,
#          rf_amp,
#          MW_phase_increment=0.,
#          pi2_1=True,
#          pi2_2=True,
#          constant_phase_offset=False,
#          padding=False,
#          MW_open=0.256,
#          optimze_rf_usage=False,
#          include_pi_dur_in_tau=True,
#          rf_phase_dict=None,
#          rf_phase_offset=None
#          ):

#     def awg_time(length):
#         return E.round_length_mus_to_x_multiple_ps(length, 1)

#     def erabi(mcas, freq, length, amp, phase=0.0):
#         electron_rabi(mcas,
#                        name='electron rabi',
#                        length_mus=awg_time(length),
#                        amplitudes=[amp],
#                        frequencies=[freq],
#                        phases=np.rad2deg(phase),
#                        new_segment=False,
#                        gateMW=True,
#                        gateRF=True,
#                        mixer_deg=-90,
#                        pulseshape='sinehermite')

#     def nrabi(mcas, freq, length, amp, phase=0.0):
#         mcas.asc(length_mus=awg_time(length),
#                  name='nuc',
#                  gateRF=True,
#                  pd2g2={"type": "sinehermite_rf",
#                         "frequencies": [freq],
#                         "amplitudes": [amp],
#                         "phases": [np.rad2deg(phase)],
#                         "phase_offset_type": 'coherent'})

#     # -------------------------------------------------------------------------
#     # RF phase settings
#     # -------------------------------------------------------------------------

#     if rf_phase_dict is None:
#         rf_phase_dict = {}

#     if rf_phase_offset is None:
#         rf_phase_offset = rf_phase_increment / 2

#     def get_rf_phase(rf_index):
#         default_phase = (
#             rotation_axis
#             + rf_index * rf_phase_increment
#             + (rf_index > 0) * rf_phase_offset
#         )

#         return rf_phase_dict.get(rf_index, default_phase)

#     # -------------------------------------------------------------------------
#     # Phases
#     # -------------------------------------------------------------------------

#     phases_dict = sc.pd()
#     phases = [*phases_dict.ddp[ddrft]] * n_rep_ddrf

#     # -------------------------------------------------------------------------
#     # Basic timing quantities
#     # -------------------------------------------------------------------------

#     nuc_drive_freq = bath_freq + detuning
#     rf_period = abs(1 / nuc_drive_freq)

#     MW_open_awg = awg_time(MW_open)
#     pi_dur_awg = awg_time(pi_dur)

#     if include_pi_dur_in_tau:
#         tau_1_target = tau - pi_dur_awg
#     else:
#         tau_1_target = tau

#     if tau_1_target <= 0:
#         raise ValueError(
#             f"tau is too short: tau={tau}, "
#             f"pi_dur={pi_dur_awg}, "
#             f"include_pi_dur_in_tau={include_pi_dur_in_tau}"
#         )

#     # -------------------------------------------------------------------------
#     # 1 tau timing
#     # -------------------------------------------------------------------------

#     rf_periods_1 = int(np.floor(tau_1_target / rf_period + 1e-12))

#     while rf_periods_1 > 0:
#         rf_tau_1 = rf_periods_1 * rf_period
#         rest_1 = tau_1_target - rf_tau_1

#         if rest_1 >= MW_open:
#             break

#         rf_periods_1 -= 1

#     if rf_periods_1 <= 0:
#         raise ValueError(
#             f"Not enough time for MW_open in 1-tau interval: "
#             f"tau_1_target={tau_1_target}, MW_open={MW_open}"
#         )

#     rf_tau_1 = rf_periods_1 * rf_period
#     rest_1 = tau_1_target - rf_tau_1

#     if padding:
#         padding_1 = rest_1 - MW_open
#         tau_1_actual = rf_tau_1 + padding_1 + MW_open
#     else:
#         padding_1 = 0.
#         tau_1_actual = rf_tau_1 + MW_open

#     # -------------------------------------------------------------------------
#     # 2 tau timing
#     # -------------------------------------------------------------------------

#     tau_2_target = 2 * tau_1_actual

#     if optimze_rf_usage:
#         rf_periods_2 = int(np.floor((tau_2_target - MW_open) / rf_period + 1e-12))
#     else:
#         rf_periods_2 = 2 * rf_periods_1

#     if rf_periods_2 <= 0:
#         raise ValueError(
#             f"Not enough time for MW_open in 2-tau interval: "
#             f"tau_2_target={tau_2_target}, MW_open={MW_open}"
#         )

#     rf_tau_2 = rf_periods_2 * rf_period
#     rest_2 = tau_2_target - rf_tau_2

#     if rest_2 < MW_open - 1e-12:
#         raise ValueError(
#             f"2-tau RF block leaves insufficient MW opening time: "
#             f"rest_2={rest_2}, MW_open={MW_open}"
#         )

#     if padding:
#         padding_2 = rest_2 - MW_open
#         tau_2_actual = rf_tau_2 + padding_2 + MW_open
#     else:
#         padding_2 = 0.
#         tau_2_actual = rf_tau_2 + MW_open

#     # -------------------------------------------------------------------------
#     # AWG-rounded timing
#     # -------------------------------------------------------------------------

#     rf_tau_1_awg = awg_time(rf_tau_1)
#     rf_tau_2_awg = awg_time(rf_tau_2)

#     padding_1_awg = awg_time(padding_1) if padding else 0.
#     padding_2_awg = awg_time(padding_2) if padding else 0.

#     tau_1_awg = rf_tau_1_awg + padding_1_awg + MW_open_awg
#     tau_2_awg = rf_tau_2_awg + padding_2_awg + MW_open_awg

#     if include_pi_dur_in_tau:
#         tau_1_center_awg = tau_1_awg + pi_dur_awg
#         tau_2_center_awg = tau_2_awg + pi_dur_awg
#     else:
#         tau_1_center_awg = tau_1_awg
#         tau_2_center_awg = tau_2_awg

#     # -------------------------------------------------------------------------
#     # Timing diagnostics
#     # -------------------------------------------------------------------------

#     print(
#         "================ DDRF timing ================",
#         f"RF period                  = {rf_period}",
#         f"requested tau              = {tau}",
#         f"pi duration (AWG)          = {pi_dur_awg}",
#         f"tau_1 target RF+rest       = {tau_1_target}",
#         f"tau_1 RF periods           = {rf_periods_1}",
#         f"tau_1 RF duration          = {rf_tau_1}",
#         f"tau_1 rest                  = {rest_1}",
#         f"tau_1 padding               = {padding_1}",
#         f"tau_1 actual                = {tau_1_actual}",
#         f"tau_2 target                = {tau_2_target}",
#         f"tau_2 RF periods           = {rf_periods_2}",
#         f"tau_2 RF duration          = {rf_tau_2}",
#         f"tau_2 rest                  = {rest_2}",
#         f"tau_2 padding               = {padding_2}",
#         f"tau_2 actual                = {tau_2_actual}",
#         f"tau_2 / tau_1              = {tau_2_actual / tau_1_actual}",
#         f"MW_open                    = {MW_open}",
#         f"MW_open (AWG)              = {MW_open_awg}",
#         f"RF tau_1 (AWG)             = {rf_tau_1_awg}",
#         f"RF tau_2 (AWG)             = {rf_tau_2_awg}",
#         f"padding_1 (AWG)            = {padding_1_awg}",
#         f"padding_2 (AWG)            = {padding_2_awg}",
#         f"1-tau interval (AWG)       = {tau_1_awg}",
#         f"2-tau interval (AWG)       = {tau_2_awg}",
#         f"2*tau_1 (AWG)              = {2 * tau_1_awg}",
#         f"center spacing 1-tau       = {tau_1_center_awg}",
#         f"center spacing 2-tau       = {tau_2_center_awg}",
#         f"optimze_rf_usage           = {optimze_rf_usage}",
#         f"padding                    = {padding}",
#         f"include_pi_dur_in_tau      = {include_pi_dur_in_tau}",
#         f"rf_phase_increment         = {rf_phase_increment}",
#         f"rf_phase_offset            = {rf_phase_offset}",
#         f"rf_phase_dict              = {rf_phase_dict}",
#         "==============================================",
#         sep="\n"
#     )

#     # -------------------------------------------------------------------------
#     # Helper: add delay before next MW pulse
#     # -------------------------------------------------------------------------

#     def add_interval_padding(padding_time):
#         if padding:
#             wait_no_new_segment(mcas, awg_time(padding_time), gate_RF=True)

#         wait_no_new_segment(mcas, MW_open_awg, gate_RF=True, gate_MW=True)

#     # -------------------------------------------------------------------------
#     # RF block counter
#     #
#     # RF block 0 = first 1-tau RF block
#     # RF block 1 = first 2-tau RF block
#     # RF block 2 = second 2-tau RF block
#     # ...
#     # RF block N = final 1-tau RF block
#     # -------------------------------------------------------------------------

#     rf_index = 0

#     # -------------------------------------------------------------------------
#     # Initial pi/2
#     # -------------------------------------------------------------------------

#     if pi2_1:
#         wait_no_new_segment(mcas, MW_open_awg, gate_RF=False, gate_MW=True)

#         print(mw_freq, pi2_dur, mw_amp, global_mw_phase)

#         erabi(mcas, mw_freq, pi2_dur, mw_amp, global_mw_phase)

#     # -------------------------------------------------------------------------
#     # First 1-tau RF evolution
#     # -------------------------------------------------------------------------

#     rf_phase = get_rf_phase(rf_index)

#     print("RF index:", rf_index, "phase:", rf_phase)
#     print(nuc_drive_freq, rf_tau_1, rf_amp, rf_phase)

#     nrabi(mcas, nuc_drive_freq, rf_tau_1, rf_amp, phase=rf_phase)

#     rf_index += 1

#     # -------------------------------------------------------------------------
#     # Intermediate pi pulses + 2-tau RF blocks
#     # -------------------------------------------------------------------------

#     for i, phase in enumerate(phases[:-1]):

#         add_interval_padding(padding_1 if i == 0 else padding_2)

#         mw_phase = (
#             phase
#             + global_mw_phase
#             + MW_phase_increment * i
#         )

#         print(mw_freq, pi_dur, mw_amp, mw_phase)

#         erabi(mcas, mw_freq, pi_dur, mw_amp, mw_phase)

#         # -------------------------------------------------------------
#         # 2-tau RF evolution
#         # -------------------------------------------------------------

#         rf_phase = get_rf_phase(rf_index)

#         print("RF index:", rf_index, "phase:", rf_phase)
#         print(nuc_drive_freq, rf_tau_2, rf_amp, rf_phase)

#         nrabi(mcas, nuc_drive_freq, rf_tau_2, rf_amp, phase=rf_phase)

#         rf_index += 1

#     # -------------------------------------------------------------------------
#     # Last pi pulse
#     # -------------------------------------------------------------------------

#     add_interval_padding(padding_2)

#     last_phase = (
#         phases[-1]
#         + global_mw_phase
#         + MW_phase_increment * (len(phases) - 1)
#     )

#     print(mw_freq, pi_dur, mw_amp, last_phase)

#     erabi(mcas, mw_freq, pi_dur, mw_amp, last_phase)

#     # -------------------------------------------------------------------------
#     # Final 1-tau RF evolution
#     # -------------------------------------------------------------------------

#     rf_phase = get_rf_phase(rf_index)

#     print("RF index:", rf_index, "phase:", rf_phase)
#     print(nuc_drive_freq, rf_tau_1, rf_amp, rf_phase)

#     nrabi(mcas, nuc_drive_freq, rf_tau_1, rf_amp, phase=rf_phase)

#     rf_index += 1

#     # -------------------------------------------------------------------------
#     # Padding before final pi/2
#     # -------------------------------------------------------------------------

#     if pi2_2:

#         if padding:
#             wait_no_new_segment(mcas, awg_time(padding_1), gate_RF=True)

#         print(mw_freq, pi2_dur, mw_amp, global_mw_phase + second_mw_phase)

#         wait_no_new_segment(mcas, MW_open_awg, gate_RF=False, gate_MW=True)

#         erabi(mcas,
#               mw_freq,
#               pi2_dur,
#               mw_amp,
#               global_mw_phase + second_mw_phase)

def DDRF(mcas,
         global_mw_phase,
         second_mw_phase,
         rf_phase_increment,
         rotation_axis,
         pi_dur,
         pi2_dur,
         detuning,
         bath_freq,
         tau,
         n_rep_ddrf,
         ddrft,
         mw_freq,
         mw_amp,
         rf_amp,
         MW_phase_increment=0.,
         pi2_1=True,
         pi2_2=True,
         constant_phase_offset=False,
         padding=False,
         MW_open=0.256,
         optimze_rf_usage=False,
         include_pi_dur_in_tau=True,
         rf_phase_dict=None,
         rf_phase_offset=None,
         measurement=None
         ):

    def awg_time(length):
        return E.round_length_mus_to_x_multiple_ps(length, 1)

    def erabi(mcas, freq, length, amp, phase=0.0):
        electron_rabi(mcas,
                       name='electron rabi',
                       length_mus=awg_time(length),
                       amplitudes=[amp],
                       frequencies=[freq],
                       phases=np.rad2deg(phase),
                       new_segment=False,
                       gateMW=True,
                       gateRF=True,
                       mixer_deg=-90,
                       pulseshape='sinehermite')

    def nrabi(mcas, freq, length, amp, phase=0.0):
        mcas.asc(length_mus=awg_time(length),
                 name='nuc',
                 gateRF=True,
                 pd2g2={"type": "sinehermite_rf",
                        "frequencies": [freq],
                        "amplitudes": [amp],
                        "phases": [np.rad2deg(phase)],
                        "phase_offset_type": 'coherent'})

    # -------------------------------------------------------------------------
    # RF phase settings
    # -------------------------------------------------------------------------

    if rf_phase_dict is None:
        rf_phase_dict = {}

    if rf_phase_offset is None:
        rf_phase_offset = rf_phase_increment / 2

    def get_rf_phase(rf_index):
        default_phase = (
            rotation_axis
            + rf_index * rf_phase_increment
            + (rf_index > 0) * rf_phase_offset
        )

        return rf_phase_dict.get(rf_index, default_phase)

    # -------------------------------------------------------------------------
    # Phases
    # -------------------------------------------------------------------------

    phases_dict = sc.pd()
    phases = [*phases_dict.ddp[ddrft]] * n_rep_ddrf

    # -------------------------------------------------------------------------
    # Basic timing quantities
    # -------------------------------------------------------------------------

    nuc_drive_freq = bath_freq + detuning
    rf_period = abs(1 / nuc_drive_freq)

    MW_open_awg = awg_time(MW_open)
    pi_dur_awg = awg_time(pi_dur)

    if include_pi_dur_in_tau:
        tau_1_target = tau - pi_dur_awg
    else:
        tau_1_target = tau

    if tau_1_target <= 0:
        raise ValueError(
            f"tau is too short: tau={tau}, "
            f"pi_dur={pi_dur_awg}, "
            f"include_pi_dur_in_tau={include_pi_dur_in_tau}"
        )

    # -------------------------------------------------------------------------
    # 1 tau timing
    # -------------------------------------------------------------------------

    rf_periods_1 = int(np.floor(tau_1_target / rf_period + 1e-12))

    while rf_periods_1 > 0:
        rf_tau_1 = rf_periods_1 * rf_period
        rest_1 = tau_1_target - rf_tau_1

        if rest_1 >= MW_open:
            break

        rf_periods_1 -= 1

    if rf_periods_1 <= 0:
        raise ValueError(
            f"Not enough time for MW_open in 1-tau interval: "
            f"tau_1_target={tau_1_target}, MW_open={MW_open}"
        )

    rf_tau_1 = rf_periods_1 * rf_period
    rest_1 = tau_1_target - rf_tau_1

    if padding:
        padding_1 = rest_1 - MW_open
        tau_1_actual = rf_tau_1 + padding_1 + MW_open
    else:
        padding_1 = 0.
        tau_1_actual = rf_tau_1 + MW_open

    # -------------------------------------------------------------------------
    # 2 tau timing
    # -------------------------------------------------------------------------

    tau_2_target = 2 * tau_1_actual

    if optimze_rf_usage:
        rf_periods_2 = int(
            np.floor((tau_2_target - MW_open) / rf_period + 1e-12)
        )
    else:
        rf_periods_2 = 2 * rf_periods_1

    if rf_periods_2 <= 0:
        raise ValueError(
            f"Not enough time for MW_open in 2-tau interval: "
            f"tau_2_target={tau_2_target}, MW_open={MW_open}"
        )

    rf_tau_2 = rf_periods_2 * rf_period
    rest_2 = tau_2_target - rf_tau_2

    if rest_2 < MW_open - 1e-12:
        raise ValueError(
            f"2-tau RF block leaves insufficient MW opening time: "
            f"rest_2={rest_2}, MW_open={MW_open}"
        )

    if padding:
        padding_2 = rest_2 - MW_open
        tau_2_actual = rf_tau_2 + padding_2 + MW_open
    else:
        padding_2 = 0.
        tau_2_actual = rf_tau_2 + MW_open

    # -------------------------------------------------------------------------
    # AWG-rounded timing
    # -------------------------------------------------------------------------

    rf_tau_1_awg = awg_time(rf_tau_1)
    rf_tau_2_awg = awg_time(rf_tau_2)

    padding_1_awg = awg_time(padding_1) if padding else 0.
    padding_2_awg = awg_time(padding_2) if padding else 0.

    tau_1_awg = rf_tau_1_awg + padding_1_awg + MW_open_awg
    tau_2_awg = rf_tau_2_awg + padding_2_awg + MW_open_awg

    if include_pi_dur_in_tau:
        tau_1_center_awg = tau_1_awg + pi_dur_awg
        tau_2_center_awg = tau_2_awg + pi_dur_awg
    else:
        tau_1_center_awg = tau_1_awg
        tau_2_center_awg = tau_2_awg

    # -------------------------------------------------------------------------
    # Timing diagnostics
    # -------------------------------------------------------------------------

    print(
        "================ DDRF timing ================",
        f"RF period                  = {rf_period}",
        f"requested tau              = {tau}",
        f"pi duration (AWG)          = {pi_dur_awg}",
        f"tau_1 target RF+rest       = {tau_1_target}",
        f"tau_1 RF periods           = {rf_periods_1}",
        f"tau_1 RF duration          = {rf_tau_1}",
        f"tau_1 rest                  = {rest_1}",
        f"tau_1 padding               = {padding_1}",
        f"tau_1 actual                = {tau_1_actual}",
        f"tau_2 target                = {tau_2_target}",
        f"tau_2 RF periods           = {rf_periods_2}",
        f"tau_2 RF duration          = {rf_tau_2}",
        f"tau_2 rest                  = {rest_2}",
        f"tau_2 padding               = {padding_2}",
        f"tau_2 actual                = {tau_2_actual}",
        f"tau_2 / tau_1              = {tau_2_actual / tau_1_actual}",
        f"MW_open                    = {MW_open}",
        f"MW_open (AWG)              = {MW_open_awg}",
        f"RF tau_1 (AWG)             = {rf_tau_1_awg}",
        f"RF tau_2 (AWG)             = {rf_tau_2_awg}",
        f"padding_1 (AWG)            = {padding_1_awg}",
        f"padding_2 (AWG)            = {padding_2_awg}",
        f"1-tau interval (AWG)       = {tau_1_awg}",
        f"2-tau interval (AWG)       = {tau_2_awg}",
        f"2*tau_1 (AWG)              = {2 * tau_1_awg}",
        f"center spacing 1-tau       = {tau_1_center_awg}",
        f"center spacing 2-tau       = {tau_2_center_awg}",
        f"optimze_rf_usage           = {optimze_rf_usage}",
        f"padding                    = {padding}",
        f"include_pi_dur_in_tau      = {include_pi_dur_in_tau}",
        f"rf_phase_increment         = {rf_phase_increment}",
        f"rf_phase_offset            = {rf_phase_offset}",
        f"rf_phase_dict              = {rf_phase_dict}",
        f"measurement                = {measurement}",
        "==============================================",
        sep="\n"
    )

    # -------------------------------------------------------------------------
    # Measurement settings
    #
    # Example:
    # measurement={3: {"fraction": 0.4, "phase": np.pi/2}}
    #
    # RF block 3:
    #   - evolve for 40% of the RF block
    #   - apply MW pi/2 with phase pi/2
    #   - terminate sequence
    # -------------------------------------------------------------------------

    if measurement is not None:

        if not isinstance(measurement, dict):
            raise TypeError(
                "measurement must be a dictionary, e.g. "
                "{3: {'fraction': 0.4, 'phase': np.pi/2}}"
            )

        if len(measurement) != 1:
            raise ValueError(
                "Only one measurement point can be specified because "
                "the sequence terminates after the measurement."
            )

        measurement_rf_index, measurement_settings = next(
            iter(measurement.items())
        )

        if not isinstance(measurement_rf_index, (int, np.integer)):
            raise TypeError(
                "The measurement RF block index must be an integer."
            )

        if not isinstance(measurement_settings, dict):
            raise TypeError(
                "Measurement settings must be a dictionary containing "
                "'fraction' and 'phase'."
            )

        if "fraction" not in measurement_settings:
            raise ValueError(
                "Measurement settings must contain 'fraction'."
            )

        if "phase" not in measurement_settings:
            raise ValueError(
                "Measurement settings must contain 'phase'."
            )

        measurement_fraction = measurement_settings["fraction"]
        measurement_phase = measurement_settings["phase"]

        if not 0 <= measurement_fraction <= 1:
            raise ValueError(
                "Measurement fraction must be between 0 and 1."
            )

        if measurement_rf_index < 0:
            raise ValueError(
                "Measurement RF block index must be >= 0."
            )

    else:
        measurement_rf_index = None
        measurement_fraction = None
        measurement_phase = None

    # -------------------------------------------------------------------------
    # Helper: perform measurement inside an RF block
    # -------------------------------------------------------------------------

    def perform_measurement(rf_index, rf_duration, rf_phase):
        if measurement is None:
            return False

        if rf_index != measurement_rf_index:
            return False

        measurement_duration = awg_time(
            measurement_fraction * rf_duration
        )

        print(
            "================ DDRF measurement ===========",
            f"RF index                   = {rf_index}",
            f"requested fraction        = {measurement_fraction}",
            f"requested RF duration     = {rf_duration}",
            f"measurement RF duration   = {measurement_duration}",
            f"RF phase                  = {rf_phase}",
            f"MW pi/2 phase             = {measurement_phase}",
            "==============================================",
            sep="\n"
        )

        # -------------------------------------------------------------
        # Evolve through the requested fraction of the RF block
        # -------------------------------------------------------------

        if measurement_duration > 0:
            nrabi(
                mcas,
                nuc_drive_freq,
                measurement_duration,
                rf_amp,
                phase=rf_phase
            )

        # -------------------------------------------------------------
        # Open MW gate before measurement pulse
        # -------------------------------------------------------------

        wait_no_new_segment(
            mcas,
            MW_open_awg,
            gate_RF=False,
            gate_MW=True
        )

        # -------------------------------------------------------------
        # Measurement MW pi/2 pulse
        #
        # IMPORTANT:
        # measurement_phase is used directly here.
        # It is not combined with the RF phase.
        # -------------------------------------------------------------

        print(
            "Measurement pi/2:",
            mw_freq,
            pi2_dur,
            mw_amp,
            measurement_phase
        )

        erabi(
            mcas,
            mw_freq,
            pi2_dur,
            mw_amp,
            measurement_phase
        )

        # -------------------------------------------------------------
        # Stop the sequence immediately after the measurement pulse
        # -------------------------------------------------------------

        return True

    # -------------------------------------------------------------------------
    # Helper: add delay before next MW pulse
    # -------------------------------------------------------------------------

    def add_interval_padding(padding_time):
        if padding:
            wait_no_new_segment(
                mcas,
                awg_time(padding_time),
                gate_RF=True
            )

        wait_no_new_segment(
            mcas,
            MW_open_awg,
            gate_RF=True,
            gate_MW=True
        )

    # -------------------------------------------------------------------------
    # RF block counter
    #
    # RF block 0 = first 1-tau RF block
    # RF block 1 = first 2-tau RF block
    # RF block 2 = second 2-tau RF block
    # ...
    # RF block N = final 1-tau RF block
    # -------------------------------------------------------------------------

    rf_index = 0

    # -------------------------------------------------------------------------
    # Initial pi/2
    # -------------------------------------------------------------------------

    if pi2_1:
        wait_no_new_segment(
            mcas,
            MW_open_awg,
            gate_RF=True,
            gate_MW=True
        )

        print(
            mw_freq,
            pi2_dur,
            mw_amp,
            global_mw_phase
        )

        erabi(
            mcas,
            mw_freq,
            pi2_dur,
            mw_amp,
            global_mw_phase
        )

    # -------------------------------------------------------------------------
    # First 1-tau RF evolution
    # -------------------------------------------------------------------------

    rf_phase = get_rf_phase(rf_index)

    print(
        "RF index:",
        rf_index,
        "phase:",
        rf_phase
    )

    print(
        nuc_drive_freq,
        rf_tau_1,
        rf_amp,
        rf_phase
    )

    # -------------------------------------------------------------
    # Measurement can occur inside RF block 0
    # -------------------------------------------------------------

    if perform_measurement(
        rf_index,
        rf_tau_1,
        rf_phase
    ):
        return

    nrabi(
        mcas,
        nuc_drive_freq,
        rf_tau_1,
        rf_amp,
        phase=rf_phase
    )

    rf_index += 1

    # -------------------------------------------------------------------------
    # Intermediate pi pulses + 2-tau RF blocks
    # -------------------------------------------------------------------------

    for i, phase in enumerate(phases[:-1]):

        add_interval_padding(
            padding_1 if i == 0 else padding_2
        )

        mw_phase = (
            phase
            + global_mw_phase
            + MW_phase_increment * i
        )

        print(
            mw_freq,
            pi_dur,
            mw_amp,
            mw_phase
        )

        erabi(
            mcas,
            mw_freq,
            pi_dur,
            mw_amp,
            mw_phase
        )

        # -------------------------------------------------------------
        # 2-tau RF evolution
        # -------------------------------------------------------------

        rf_phase = get_rf_phase(rf_index)

        print(
            "RF index:",
            rf_index,
            "phase:",
            rf_phase
        )

        print(
            nuc_drive_freq,
            rf_tau_2,
            rf_amp,
            rf_phase
        )

        # -------------------------------------------------------------
        # Measurement can occur inside this 2-tau RF block
        # -------------------------------------------------------------

        if perform_measurement(
            rf_index,
            rf_tau_2,
            rf_phase
        ):
            return

        nrabi(
            mcas,
            nuc_drive_freq,
            rf_tau_2,
            rf_amp,
            phase=rf_phase
        )

        rf_index += 1

    # -------------------------------------------------------------------------
    # Last pi pulse
    # -------------------------------------------------------------------------

    add_interval_padding(padding_2)

    last_phase = (
        phases[-1]
        + global_mw_phase
        + MW_phase_increment * (len(phases) - 1)
    )

    print(
        mw_freq,
        pi_dur,
        mw_amp,
        last_phase
    )

    erabi(
        mcas,
        mw_freq,
        pi_dur,
        mw_amp,
        last_phase
    )

    # -------------------------------------------------------------------------
    # Final 1-tau RF evolution
    # -------------------------------------------------------------------------

    rf_phase = get_rf_phase(rf_index)

    print(
        "RF index:",
        rf_index,
        "phase:",
        rf_phase
    )

    print(
        nuc_drive_freq,
        rf_tau_1,
        rf_amp,
        rf_phase
    )

    # -------------------------------------------------------------
    # Measurement can occur inside the final RF block
    # -------------------------------------------------------------

    if perform_measurement(
        rf_index,
        rf_tau_1,
        rf_phase
    ):
        return

    nrabi(
        mcas,
        nuc_drive_freq,
        rf_tau_1,
        rf_amp,
        phase=rf_phase
    )

    rf_index += 1

    # -------------------------------------------------------------------------
    # Padding before final pi/2
    # -------------------------------------------------------------------------

    if pi2_2:

        if padding:
            wait_no_new_segment(
                mcas,
                awg_time(padding_1),
                gate_RF=True
            )

        print(
            mw_freq,
            pi2_dur,
            mw_amp,
            global_mw_phase + second_mw_phase
        )

        wait_no_new_segment(
            mcas,
            MW_open_awg,
            gate_RF=False,
            gate_MW=True
        )

        erabi(
            mcas,
            mw_freq,
            pi2_dur,
            mw_amp,
            global_mw_phase + second_mw_phase
        )




def ddrf(mcas,
         global_mw_phase,
         second_mw_phase,
         rf_phase_increment,
         rotation_axis,
         pi_dur,
         pi2_dur,
         detuning,
         bath_freq,
         tau,
         n_rep_ddrf,
         ddrft,
         mw_freq,
         mw_amp,
         rf_amp,
         MW_phase_increment=0.,
         pi2_1 = True,
         pi2_2 = True,
         constant_phase_offset = False,
         padding=False,
         rf_phase_offset=0,
         measurements=[],
         phase_dict={},
         conditional = True,
         ):
    pi2 = sc.Rabi(t_rabi=pi2_dur,
                  omega=1 / pi2_dur*4,
                  phase=0.0,
                  control_field='mw')
    pi2_phi = sc.Rabi(t_rabi=pi2_dur,
                      omega=1 / pi2_dur*4,
                      phase=second_mw_phase,
                      control_field='mw')
    ddrf = sc.DDRF(dd_type='{}_{}'.format(n_rep_ddrf,ddrft),
                    pi_dur=pi_dur,
                    pi2_dur=pi2_dur,
                    detuning = detuning,
                    bath_larmor = bath_freq,
                    rf_phase_increment = rf_phase_increment,
                    rotation_axis= rotation_axis,
                    tau=tau,
                    min_wait_dur = .256,
                    constant_phase_offset = constant_phase_offset,
                    rf_phase_offset=rf_phase_offset,
                    phase_dict=phase_dict,
                    conditional = True,
                    )
    sequence = []
    if pi2_1:
        sequence.append(pi2)
    sequence.append(ddrf)
    if pi2_2:
        sequence.append(pi2_phi)

    if len(sequence)>1:
        seq = sc.Concatenated(sequence, controls=['mw', 'rf', 'wait'])
    else:
        seq = ddrf
    waveform_ddrf(mcas,
             seq,
             global_mw_phase,
             mw_freq = mw_freq,
             rf_freq = bath_freq + detuning,
             mw_amp = mw_amp,
             rf_amp = rf_amp,
             MW_phase_increment=MW_phase_increment,
             real_tau=tau,
             padding=padding,
             measurements=measurements,
             )

    #return seq # for debugging

def waveform_ddrf(mcas,
                  seq,
                  global_mw_phase,
                  mw_freq,
                  rf_freq,
                  mw_amp,
                  rf_amp,
                  MW_phase_increment,
                  real_tau,
                  padding,
                  measurements,
                  ):
    def erabi(mcas, freq, length, amp, phase=0.0, name=""):
        electron_rabi(mcas,
                        name=name if name else 'electron rabi',
                        length_mus=E.round_length_mus_to_x_multiple_ps(length,1),
                        amplitudes=[amp],
                        frequencies=[freq],
                        phases=np.rad2deg(phase),
                        new_segment=False,
                        gateMW=True,
                        gateRF=True,
                        mixer_deg=-90,
                        pulseshape='sinehermite',
                        )
        
    def nrabi(mcas, freq, length, amp, phase=0.0, real_tau=None):
        real_tau*=[1,2][length>np.mean(rf[:,0])]
        #print("length",length,real_tau)
        mcas.asc(
            length_mus=E.round_length_mus_to_x_multiple_ps(length,1),
            name='nuc',
            gateRF = True,
            pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [np.rad2deg(phase)],
                    "phase_offset_type": 'coherent'}
        )

        if real_tau and padding:
            #print(wait[:,0])
            real_tau-=2*[wait[0,0],wait[2,0]][length>np.mean(rf[:,0])]

            if real_tau-E.round_length_mus_to_x_multiple_ps(length,1)>0:
                #print("adding ",real_tau-E.round_length_mus_to_x_multiple_ps(length,1))
                wait_no_new_segment(mcas,real_tau-E.round_length_mus_to_x_multiple_ps(length,1))
            else:
                print("padding does not work at this tau")

    mw = seq.times_fields_aphi('mw')
    rf = seq.times_fields_aphi('rf')
    wait = seq.times_fields_aphi('wait')
    #print("single tau ", real_tau, "actual tau", rf[:,0], "diff", rf[:,0]-real_tau)
    if real_tau-rf[0:0]<0:
        raise "some error to catch attention in ddrf, padding with 0s will not work"

    #print("DDRF")
    #print(mw)
    #print(rf)

    finish=False

    print("-----real phase-----\n",rf[:, 2])
    print(mw)
    
    for k, step in enumerate(seq.sequence_steps):
        idx = int(step[1]) - 1

        #print("idx",idx,MW_phase_increment)
        #print(step,mw[idx, 2])
        if step[0] == 'mw':  
            erabi(mcas,
                  freq=mw_freq,
                  length=mw[idx, 0],
                  amp=mw_amp,
                  phase=mw[idx, 2] + global_mw_phase+idx*MW_phase_increment,)
        elif step[0] == 'rf':

            length=rf[idx, 0]
            #print("rf idx",idx,MW_phase_increment)
            multiplier=1
            if measurements and measurements[0]==idx:
                multiplier=measurements[1]
                finish=True
                padding=False

            #print(multiplier)
            nrabi(mcas,
                  freq=rf_freq,
                  length=length*multiplier,
                  amp=rf_amp,
                  phase=rf[idx, 2],
                  real_tau=real_tau)

        if finish:
            #make final pi/2
            #print("finishing at idx", idx, "with MW", mw[-1, 0], mw[-1, 2])
            mcas.asc(length_mus = 0.128, gateMW = True, gateRF = False)
            erabi(mcas,name="finishing pi/2",
                              freq=mw_freq,
                              length=mw[-1, 0],
                              amp=mw_amp,
                              phase=mw[-1, 2])
            return

                    
        if step[0] == 'wait':
            mcas.asc(length_mus = wait[idx,0], gateMW = True, gateRF = True)

def sedor(mcas,
          probe_pi2_dur,
          n_rep_sedor,
          sedort,
          total_tau,
          probe_freq,
          probe_amp,
          target_freq,
          target_amp,
          target_dur,
          target_phase_shift = 0,
          pi2_1 = True,
          pi2_2 = False,
          phi_1 = 0.0,
          phi_2 = 0.0,
          shutter = 'open'
          ):
    rabi_period = probe_pi2_dur * 4
    pi2 = sc.Rabi(t_rabi=0.25 * rabi_period, omega=1 / rabi_period, phase=phi_1, control_field='mw')
    pi2_phi = sc.Rabi(t_rabi=0.25 * rabi_period, omega=1 / rabi_period, phase=phi_2, control_field='mw')
    dd = sc.DD(dd_type='{}_{}'.format(n_rep_sedor, sedort), rabi_period=rabi_period, total_tau=total_tau)

    sequence = []
    if pi2_1: # add first pi/2 if needed
        sequence.append(pi2)
    sequence.append(dd) # always add the dd which consists of taus and pi pulses
    if pi2_2: # add final pi/2 if needed
        sequence.append(pi2_phi)

    if len(sequence)>1:
        seq = sc.Concatenated(sequence, controls=['mw', 'wait'])
    else:
        seq = dd
    waveform_sedor(mcas,
                   seq,
                   probe_freq,
                   probe_amp,
                   probe_pi2_dur,
                   target_freq,
                   target_amp,
                   target_dur,
                   target_phase_shift,
                   total_tau,
                   shutter
                   )
def waveform_sedor(mcas,
                   seq,
                   probe_freq,
                   probe_amp,
                   probe_pi2_dur,
                   target_freq,
                   target_amp,
                   target_dur,
                   target_phase_shift,
                   total_tau,
                   shutter
                   ):
    def nrabi(mcas, freq, length, amp, phase=0.0, shutter = 'open'):

        if isinstance(freq, list):
            mcas.asc(
                length_mus=E.round_length_mus_to_x_multiple_ps(length,1),
                name='nuc',
                gateRF = True,
                shutter = False if shutter == 'open' else True,
                pd2g2={"type": "sinehermite_rf", "frequencies": freq, "amplitudes": amp, "phases": [np.rad2deg(phase)]*len(freq),
                        "phase_offset_type": 'coherent'}
            )
        else:
            mcas.asc(
                length_mus=E.round_length_mus_to_x_multiple_ps(length,1),
                name='nuc',
                gateRF = True,
                shutter = False if shutter == 'open' else True,
                pd2g2={"type": "sinehermite_rf", "frequencies": [freq], "amplitudes": [amp], "phases": [np.rad2deg(phase)],
                        "phase_offset_type": 'coherent'}
            )
    mw = seq.times_fields_aphi('mw') # actually RF (originates from variable name constrains)
    wait = seq.times_fields_aphi('wait')
    
    end_time = mcas.length_mus + total_tau
    RF_opening_time = 80 #ms
    first_wait_done = False
    shutter_ = True
    for k, step in enumerate(seq.sequence_steps):
        # open shutter when close to end of SEDOR
        idx = int(step[1]) - 1
        if step[0] == 'mw':
            step_duration = mw[idx, 0]
        else:
            step_duration = wait[idx, 0]
        time_left_after_step = end_time - mcas.length_mus - step_duration
        if ((time_left_after_step < 100000) and (shutter == 'opening')) or (shutter == 'open'):
            shutter_ = False
        
        # SEDOR

        if step[0] == 'mw':
            nrabi(mcas,
                  freq=probe_freq,
                  length=mw[idx, 0],
                  amp=probe_amp,
                  phase=mw[idx, 2],
                  shutter = shutter_
                  )
        if step[0] == 'wait':
            if first_wait_done:
                nrabi(mcas,
                      freq= target_freq,
                      length= target_dur,
                      amp= target_amp,
                      phase = mw[idx, 2]+target_phase_shift,
                      shutter = shutter_
                      )

                tau_wait = wait[idx, 0] - target_dur - (2 * probe_pi2_dur)
            else:
                tau_wait = wait[idx, 0] - probe_pi2_dur/2

            if tau_wait<0: # ie we will not do what we thik it should do
                raise Exception(f"WARNING IN SEDOR!!!!! tau wait is negative! the measurement will not behave as you expect. try increasing total tau or use shorter pi pulses.\nwait={wait[idx, 0]},target_dur={ target_dur},2*probe_pi2_dur={2 * probe_pi2_dur} -> tau wait={tau_wait}. setting tau wait to 0")
                tau_wait=0.0
                #pass

            loops = int(tau_wait/1000)
            rest = tau_wait%1000
            if tau_wait != 0:
                if loops  > 0:
                    mcas.start_new_segment('Tau', loop_count=loops)
                    mcas.asc(length_mus=1000, shutter = shutter_)
                mcas.start_new_segment('TauRest', loop_count=1)
                if rest - 0.512 > 0:
                    mcas.asc(length_mus=rest - 0.512, shutter = shutter_)  
                    mcas.asc(length_mus=0.512, gateRF = True, shutter = shutter_)
                else:
                    mcas.asc(length_mus=rest, gateRF = True, shutter = shutter_)  
            first_wait_done = True




def get_hardcoded_si1_values(state, larmor):
    #si1_freq = {'-3/2': 8.9920829,  '-1/2':4.1696871, '+1/2': 0.650141, '+3/2': 5.4666419}[state] #2086.7G
    #si1_freq = {'-3/2': -8.885062,  '-1/2':-4.062826, '+1/2': 0.7567408, '+3/2': 5.572578}[state] #1960.6G
    detuning =  {'-3/2': -7.22501493-0.0001508081074127082-2.084926823570443e-05+0.00013549502407628861, '-1/2':-2.40277893,  '+1/2': 2.41678787,  '+3/2': 7.23262507}[state]
    si1_freq = detuning + larmor

    #si1_freq =-14.564620373525031 #UNFUG
    #si1_freq=11.115610807188204+0.26241352614382996+0.005076610870571051

    si1_amp = 0.9
    # si1_pi = {'-3/2': 56.4,  '-1/2': 119.3, '+1/2': 1097, '+3/2': 98.6}[state]
    # si1_pi2 = {'-3/2': 29.3,  '-1/2':60.1, '+1/2': 514.6, '+3/2': 51.2}[state]
    # si1_pi = {'-3/2': 61.06,  '-1/2': 130.56, '+1/2': 1020.95, '+3/2': 105.69}[state]
    # si1_pi2 = {'-3/2': 32.77,  '-1/2':68.04, '+1/2': 515.29, '+3/2': 55.68}[state]

    si1_pi = {'-3/2': 60.1,  '-1/2': 127.619, '+1/2': 1091.95, '+3/2': 105.484+4}[state] #was used for Si8 in -3/2
    si1_pi2 = {'-3/2': 32.77-0.8,  '-1/2':68.04-0.9, '+1/2': 585.29, '+3/2': 55.68-1.9}[state]

    #si1_pi = {'-3/2': 30.69,  '-1/2': 105.21, '+1/2': 545, '+3/2':78.04}[state] # for Si5 at 2050G
    #si1_pi2 = {'-3/2': 16.484,  '-1/2':52.890, '+1/2': 585.29, '+3/2': 39.867}[state] # for Si5 at 2050G

    # si1_pi = {'-3/2': 104,  '-1/2': 127.619, '+1/2': 1091.95, '+3/2': 105.484}[state]
    # si1_pi2 = {'-3/2': 32.77,  '-1/2':68.04, '+1/2': 585.29, '+3/2': 55.68}[state]
    return si1_freq, si1_amp, si1_pi, si1_pi2

def get_hardcoded_e_values_for_control(trans, pulseshape = 'sinehermite',tt=None,fast=False,middle=False):
    trans_idx = trans[-1]
    # amp = 0.95
    # if pulseshape == 'sinehermite':
    #     if trans[0] == 'L':
    #         e_pi = {'1': .458, '2': .458}[trans_idx]
    #         e_pi2 = {'1': .245, '2': .245}[trans_idx]
    #     elif trans[0] == 'C':
    #         e_pi = {'1': .263, '2': .263}[trans_idx]
    #         e_pi2 = {'1': .17, '2': .17}[trans_idx]
    #     elif trans[0] == 'R':
    #         e_pi = {'1': .197, '2': .197}[trans_idx]
    #         e_pi2 = {'1': .13, '2': .13}[trans_idx]
    # elif pulseshape == 'sine':
    #     if trans[0] == 'L':
    #         e_pi = {'1': .296, '2': .315}[trans_idx]
    #         e_pi2 = {'1': .146, '2': .154}[trans_idx]
    #     elif trans[0] == 'C':
    #         e_pi = {'1': .300, '2': .293}[trans_idx]
    #         e_pi2 = {'1': .170, '2': .182}[trans_idx]
    #     elif trans[0] == 'R':
    #         e_pi = {'1': .178, '2': .153}[trans_idx]
    #         e_pi2 = {'1': .094, '2': .078}[trans_idx]

    #at 1962G
    # amp = 0.9
    # if pulseshape == 'sinehermite':
    #     if trans[0] == 'L':
    #         e_pi = {'1': .482, '2': .466}[trans_idx]
    #         e_pi2 = {'1': .273, '2': .267}[trans_idx]
    #     elif trans[0] == 'C':
    #         e_pi = {'1': .296, '2': .272}[trans_idx]
    #         e_pi2 = {'1': .183, '2': .167}[trans_idx]
    #     elif trans[0] == 'R':
    #         e_pi = {'1': .225, '2': .2}[trans_idx]
    #         e_pi2 = {'1': .144, '2': .129}[trans_idx]
    # elif pulseshape == 'sine':
    #     if trans[0] == 'L':
    #         e_pi = {'1': .296, '2': .315}[trans_idx]
    #         e_pi2 = {'1': .146, '2': .154}[trans_idx]
    #     elif trans[0] == 'C':
    #         e_pi = {'1': .300, '2': .293}[trans_idx]
    #         e_pi2 = {'1': .170, '2': .182}[trans_idx]
    #     elif trans[0] == 'R':
    #         e_pi = {'1': .178, '2': .153}[trans_idx]
    #         e_pi2 = {'1': .094, '2': .078}[trans_idx]

    # if not tt:
    #     if not fast:
    #         if pulseshape == 'sinehermite':
    #             if trans[0] == 'L':
    #                 amp=0.215
    #                 e_pi = {'1': .259, '2': .242}[trans_idx]
    #                 e_pi2 = {'1': .156, '2': .150}[trans_idx]
    #             elif trans[0] == 'C':
    #                 amp=0.360 #uncalibrated
    #                 e_pi = {'1': .296, '2': .272}[trans_idx]
    #                 e_pi2 = {'1': .183, '2': .167}[trans_idx]
    #             elif trans[0] == 'R':
    #                 amp=0.360
    #                 e_pi = {'1': .253, '2': .251}[trans_idx]
    #                 e_pi2 = {'1': .162, '2': .159}[trans_idx]
    #         elif pulseshape == 'sine': #uncalibrated
    #             if trans[0] == 'L':
    #                 e_pi = {'1': .296, '2': .315}[trans_idx]
    #                 e_pi2 = {'1': .146, '2': .154}[trans_idx]
    #             elif trans[0] == 'C':
    #                 e_pi = {'1': .300, '2': .293}[trans_idx]
    #                 e_pi2 = {'1': .170, '2': .182}[trans_idx]
    #             elif trans[0] == 'R':
    #                 e_pi = {'1': .178, '2': .153}[trans_idx]
    #                 e_pi2 = {'1': .094, '2': .078}[trans_idx]

    #     if fast:
    #         amp=1.
    #         if pulseshape == 'sinehermite':
    #             if trans[0] == 'L':
    #                 e_pi = {'1': .086, '2': .082}[trans_idx]
    #                 e_pi2 = {'1': .044, '2': .043}[trans_idx]
    #             elif trans[0] == 'C':
    #                 amp=1 #uncalibrated
    #                 e_pi = {'1': .296, '2': .272}[trans_idx]
    #                 e_pi2 = {'1': .073, '2': .073}[trans_idx]
    #             elif trans[0] == 'R':
    #                 e_pi = {'1': .135, '2': .135}[trans_idx]
    #                 e_pi2 = {'1': .073, '2': .069}[trans_idx]
    #         elif pulseshape == 'sine': #2 is uncalibrated
    #             if trans[0] == 'L':
    #                 e_pi = {'1': 0.043, '2': 0.043}[trans_idx]
    #                 e_pi2 = {'1': 0.021, '2': 0.021}[trans_idx]
    #             elif trans[0] == 'C':
    #                 e_pi = {'1': .300, '2': .293}[trans_idx]
    #                 e_pi2 = {'1': .170, '2': .182}[trans_idx]
    #             elif trans[0] == 'R':
    #                 e_pi = {'1': 0.071, '2': 0.071}[trans_idx]
    #                 e_pi2 = {'1': 0.035, '2': 0.035}[trans_idx]

    #     if middle: 
    #         amp=1.
    #         if pulseshape == 'sinehermite':
    #             if trans[0] == 'L':
    #                 e_pi = {'1': .070, '2': .072}[trans_idx]
    #                 e_pi2 = {'1': .045, '2': .043}[trans_idx]
    #             elif trans[0] == 'C':
    #                 amp=1 #uncalibrated
    #                 e_pi = {'1': .296, '2': .272}[trans_idx]
    #                 e_pi2 = {'1': .073, '2': .073}[trans_idx]
    #             elif trans[0] == 'R':
    #                 e_pi = {'1': .102, '2': .090}[trans_idx]
    #                 e_pi2 = {'1': .075, '2': .073}[trans_idx]

    #         elif pulseshape == 'sine': #2 is uncalibrated
    #             if trans[0] == 'L':
    #                 e_pi = {'1': 0.043, '2': 0.043}[trans_idx]
    #                 e_pi2 = {'1': 0.021, '2': 0.021}[trans_idx]
    #             elif trans[0] == 'C':
    #                 e_pi = {'1': .300, '2': .293}[trans_idx]
    #                 e_pi2 = {'1': .170, '2': .182}[trans_idx]
    #             elif trans[0] == 'R':
    #                 e_pi = {'1': 0.071, '2': 0.071}[trans_idx]
    #                 e_pi2 = {'1': 0.035, '2': 0.035}[trans_idx]

    # else:
    #     if "L" in trans:
    #         amp=0.215
    #     elif "R" in trans:
    #         amp=0.360
    #     elif "C" in trans: 
    #         amp=0.360 #uncalibrated!!!!!
        
    #     e_pi = tt.RP('e_rabi_ou350deg-90-'+trans, amp=amp).pi
    #     e_pi2 = tt.RP('e_rabi_ou350deg-90-'+trans, amp=amp).pi2

    #### at 1730G rouven amplifier
    # if pulseshape == 'sinehermite':
    #             if trans[0] == 'L':
    #                 amp=1
    #                 e_pi = {'1': .400, '2': .400}[trans_idx]
    #                 e_pi2 = {'1': .180, '2': .180}[trans_idx]
    #             elif trans[0] == 'C':
    #                 amp=1 #uncalibrated
    #                 e_pi = {'1': .296, '2': .272}[trans_idx]
    #                 e_pi2 = {'1': .183, '2': .167}[trans_idx]
    #             elif trans[0] == 'R':
    #                 amp=1
    #                 e_pi = {'1': .16, '2': .16}[trans_idx]
    #                 e_pi2 = {'1': .082, '2': .082}[trans_idx]

    if not tt:
        if not fast:
            if pulseshape == 'sinehermite':
                if trans[0] == 'L':
                    amp=0.215
                    e_pi = {'1': .259, '2': .242}[trans_idx]
                    e_pi2 = {'1': .156, '2': .150}[trans_idx]
                elif trans[0] == 'C':
                    amp=0.360 #uncalibrated
                    e_pi = {'1': .296, '2': .272}[trans_idx]
                    e_pi2 = {'1': .183, '2': .167}[trans_idx]
                elif trans[0] == 'R':
                    amp=0.360
                    e_pi = {'1': .253, '2': .251}[trans_idx]
                    e_pi2 = {'1': .162, '2': .159}[trans_idx]
            elif pulseshape == 'sine': #uncalibrated
                if trans[0] == 'L':
                    e_pi = {'1': .296, '2': .315}[trans_idx]
                    e_pi2 = {'1': .146, '2': .154}[trans_idx]
                elif trans[0] == 'C':
                    e_pi = {'1': .300, '2': .293}[trans_idx]
                    e_pi2 = {'1': .170, '2': .182}[trans_idx]
                elif trans[0] == 'R':
                    e_pi = {'1': .178, '2': .153}[trans_idx]
                    e_pi2 = {'1': .094, '2': .078}[trans_idx]

        if fast:
            amp=1.
            if pulseshape == 'sinehermite':
                if trans[0] == 'L':
                    # usedf on Si8MHz
                    # e_pi = {'1': .122, '2': .080}[trans_idx]
                    # e_pi2 = {'1': .057, '2': .039}[trans_idx] #+4 ns ?

                    # used on Si5
                    #e_pi = {'1': .085, '2': .080}[trans_idx]
                    #e_pi2 = {'1': .040, '2': .039}[trans_idx] #+4 ns ?

                    e_pi = {'1': .118, '2': .115}[trans_idx]
                    e_pi2 = {'1': .059, '2': .053}[trans_idx] #+4 ns ?
                    # e_pi = {'1': .133, '2': .110}[trans_idx]
                    # e_pi2 = {'1': .064, '2': .053}[trans_idx] #+4 ns ?

                    # e_pi = {'1': .096, '2': .096}[trans_idx]
                    # e_pi2 = {'1': .045, '2': .044}[trans_idx] #+4 ns ?
                    #e_pi = {'1': .088, '2': .088}[trans_idx]
                    #e_pi2 = {'1': .045*88/96, '2': .044*88/96}[trans_idx] #+4 ns ?

                    #e_pi = {'1': .140, '2': .140}[trans_idx]
                    #e_pi2 = {'1': .075, '2': .075}[trans_idx] #+4 ns ?

                    #from trying to optimize the pi pulses
                    # e_pi = {'1': .087, '2': .082}[trans_idx] #+2ns
                    # e_pi2 = {'1': .041, '2': .040}[trans_idx] 
                    # amp=amp-0.02

                elif trans[0] == 'C':
                    amp=1 #uncalibrated
                    e_pi = {'1': .150, '2': .150}[trans_idx]
                    e_pi2 = {'1': .113, '2': .083}[trans_idx]
                elif trans[0] == 'R':
                    e_pi = {'1': .156, '2': .156}[trans_idx]
                    e_pi2 = {'1': .092, '2': .092}[trans_idx]

                    #e_pi = {'1': .149, '2': .149}[trans_idx]
                    #e_pi2 = {'1': .082, '2': .082}[trans_idx]

                    e_pi = {'1': .133, '2': .133}[trans_idx]
                    e_pi2 = {'1': .094, '2': .094}[trans_idx]


            elif pulseshape == 'sine': #2 is uncalibrated
                if trans[0] == 'L':
                    e_pi = {'1': 0.043, '2': 0.043}[trans_idx]
                    e_pi2 = {'1': 0.021, '2': 0.021}[trans_idx]
                elif trans[0] == 'C':
                    e_pi = {'1': .300, '2': .293}[trans_idx]
                    e_pi2 = {'1': .170, '2': .182}[trans_idx]
                elif trans[0] == 'R':
                    e_pi = {'1': 0.071, '2': 0.071}[trans_idx]
                    e_pi2 = {'1': 0.035, '2': 0.035}[trans_idx]

        if middle: 
            amp=1.
            if pulseshape == 'sinehermite':
                if trans[0] == 'L':
                    e_pi = {'1': .070, '2': .072}[trans_idx]
                    e_pi2 = {'1': .045, '2': .043}[trans_idx]
                elif trans[0] == 'C':
                    amp=1 #uncalibrated
                    e_pi = {'1': .296, '2': .272}[trans_idx]
                    e_pi2 = {'1': .073, '2': .073}[trans_idx]
                elif trans[0] == 'R':
                    e_pi = {'1': .102, '2': .090}[trans_idx]
                    e_pi2 = {'1': .075, '2': .073}[trans_idx]

            elif pulseshape == 'sine': #2 is uncalibrated
                if trans[0] == 'L':
                    e_pi = {'1': 0.043, '2': 0.043}[trans_idx]
                    e_pi2 = {'1': 0.021, '2': 0.021}[trans_idx]
                elif trans[0] == 'C':
                    e_pi = {'1': .300, '2': .293}[trans_idx]
                    e_pi2 = {'1': .170, '2': .182}[trans_idx]
                elif trans[0] == 'R':
                    e_pi = {'1': 0.071, '2': 0.071}[trans_idx]
                    e_pi2 = {'1': 0.035, '2': 0.035}[trans_idx]

    else:
        if "L" in trans:
            amp=0.215
        elif "R" in trans:
            amp=0.360
        elif "C" in trans: 
            amp=0.360 #uncalibrated!!!!!
        
        e_pi = tt.RP('e_rabi_ou350deg-90-'+trans, amp=amp).pi
        e_pi2 = tt.RP('e_rabi_ou350deg-90-'+trans, amp=amp).pi2


    return amp, e_pi, e_pi2


def get_hardcoded_e_values_for_readout(trans_idx,weak=False):
    #### at 1962G
    # if not weak:
    #     L_amp = 0.90
    #     C_amp = {'1': .5, '2': .5}[trans_idx] # for pi flip within 468ns.
    #     R_amp = {'1': .327, '2': .327}[trans_idx] # for pi flip within 468ns.
    #     e_pi = {'1': .458, '2': .458}[trans_idx]
    #     e_pi2 = {'1': .245, '2': .245}[trans_idx]
    # else:
    #     L_amp = 0.70
    #     C_amp = {'1': .5, '2': .5}[trans_idx] # for pi flip within 468ns.
    #     R_amp = {'1': 0.27678, '2': .250}[trans_idx] # for pi flip within 468ns.
    #     e_pi = {'1': 0.597, '2': .564}[trans_idx]
    #     e_pi2 = {'1': 0.333, '2': .313}[trans_idx]

    #### at 2048G
    # if not weak:
    #     L_amp = 0.90
    #     C_amp = {'1': .5, '2': .5}[trans_idx] # for pi flip within 468ns.
    #     R_amp = {'1': .9*46/73, '2': .9*46/73}[trans_idx] # for pi flip within 73 ns.
    #     e_pi = {'1': .073, '2': .073}[trans_idx]
    #     e_pi2 = {'1': .036, '2': .036}[trans_idx]
    # else:

    #### rouven amp at 2048 G
    # L_amp = 0.0955 #0.15*.230/0.422*1.2
    # C_amp = {'1': .5, '2': .5}[trans_idx] # for pi flip within 468ns.
    # R_amp = {'1': 0.15, '2': 0.15}[trans_idx]*1.2 # for pi flip within 468ns.
    # e_pi = {'1': 0.422, '2': 0.422}[trans_idx]
    # e_pi2 = {'1': 0.422/2, '2': 0.422/2}[trans_idx]


    L_amp = 0.126 #0.15*.230/0.422*1.2
    C_amp = {'1': .5, '2': .5}[trans_idx] # for pi flip within 468ns.
    R_amp = {'1': 0.206, '2': 0.206}[trans_idx]*1.2 # for pi flip within 468ns.
    e_pi = {'1': 0.422, '2': 0.422}[trans_idx]
    e_pi2 = {'1': 0.422/2, '2': 0.422/2}[trans_idx]

    # # 8MHZ at 2050 G
    # if not weak:
    #     L_amp = 0.90
    #     C_amp = {'1': .5, '2': .5}[trans_idx] # for pi flip within 468ns.
    #     R_amp = {'1': .9*46/73, '2': .9*46/73}[trans_idx] # for pi flip within 73 ns.
    #     e_pi = {'1': .073, '2': .073}[trans_idx]
    #     e_pi2 = {'1': .036, '2': .036}[trans_idx]
    # else:
    #     L_amp = 0.2 #0.15*.230/0.422*1.2
    #     C_amp = {'1': .5, '2': .5}[trans_idx] # for pi flip within 468ns.
    #     R_amp = {'1': 0.4, '2': 0.4}[trans_idx] # for pi flip within 468ns.
    #     e_pi = {'1': 0.33, '2': 0.33}[trans_idx]
    #     e_pi2 = {'1': 0.422/2, '2': 0.422/2}[trans_idx]

    #### at 1730G rouven amplifier
    # if not weak:
    #     L_amp = 0.90
    #     C_amp = {'1': .5, '2': .5}[trans_idx] # for pi flip within 468ns.
    #     R_amp = {'1': .9*46/73, '2': .9*46/73}[trans_idx] # for pi flip within 73 ns.
    #     e_pi = {'1': .073, '2': .073}[trans_idx]
    #     e_pi2 = {'1': .036, '2': .036}[trans_idx]

    # else:
    #     R_amp = 0.232 #0.15*.230/0.422*1.2
    #     C_amp = {'1': 0.2155, '2': 0.2155}[trans_idx] # for pi flip within 468ns.
    #     L_amp = {'1': 0.966, '2': 0.966}[trans_idx] # for pi flip within 468ns.
    #     e_pi = {'1': 0.422, '2': 0.422}[trans_idx]
    #     e_pi2 = {'1': 0.422/2, '2': 0.422/2}[trans_idx]

    # else:
    #     L_amp = 0.09534 #0.15*.230/0.422*1.2
    #     C_amp = {'1': 0.2155, '2': 0.2155}[trans_idx] # for pi flip within 468ns.
    #     R_amp = {'1': 0.2155, '2': 0.2155}[trans_idx] # for pi flip within 468ns.
    #     e_pi = {'1': 0.422, '2': 0.422}[trans_idx]
    #     e_pi2 = {'1': 0.422/2, '2': 0.422/2}[trans_idx]

    # L_amp = 0.95
    # R_amp = {'1': .925, '2': .925}[trans_idx] # for pi flip within 468ns.
    # e_pi = {'1': .314, '2': .314}[trans_idx]
    # e_pi2 = {'1': .186, '2': .186}[trans_idx]

    
    return R_amp, L_amp, e_pi, e_pi2
            
