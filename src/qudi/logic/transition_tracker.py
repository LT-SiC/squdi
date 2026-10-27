# coding=utf-8
from __future__ import print_function, absolute_import, division
__metaclass__ = type
import warnings
import datetime
import shutil

import qudi.logic.misc as misc
from numbers import Number
import scipy.interpolate
from qudi.logic.qudip_enhanced.nv_hamilton import NVHam
from qudi.logic.qudip_enhanced.nv_hamilton import gamma
from qudi.logic.qudip_enhanced import sort_eigenvalues_standard_basis
from qudi.logic.qudip_enhanced.analyze import flipped_spin_numbers, single_quantum_transitions_non_hf_spins, get_transition_frequency
import qudi.logic.qudip_enhanced.lmfit_models
from itertools import product
import numpy as np
import pandas as pd
import os

import collections
import matplotlib.pyplot as plt
import logging
import builtins
from scipy.interpolate import interp1d

from PySide6.QtCore import Signal

from qutip import *
import numpy as np
from scipy.optimize import minimize

from PySide6 import QtCore

from qudi.core.module import LogicBase
from qudi.core.connector import Connector
from qudi.core.configoption import ConfigOption
import shutil

import lmfit

from natsort import natsorted
import math

####################################################################################################################
# single values
####################################################################################################################
# All paths are derived from the location of the qudi package, so nothing depends on where qudi is installed.
# This file lives in <...>/src/qudi/logic/, so QUDI_DIR is <...>/src/qudi.
# To keep the logs somewhere else, set the environment variable QUDI_LOG_DIR.
QUDI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_ROOT = os.environ.get('QUDI_LOG_DIR', os.path.join(QUDI_DIR, 'log'))
TT_LOG_DIR = os.path.join(LOG_ROOT, 'transition_tracker_log')

app_dir = QUDI_DIR
log_dir = LOG_ROOT + os.sep
log_archive_dir = os.path.join(LOG_ROOT, 'archive') + os.sep
log_single_val_dir = os.path.join(LOG_ROOT, 'single_values') + os.sep
log_tmp = os.path.join(LOG_ROOT, 'temp') + os.sep

__TIME_FORMAT_STR__ = '%Y%m%d-h%Hm%Ms%S'


def nowstr():
    return datetime.datetime.now().strftime('%Y%m%d-h%Hm%Ms%S')
###################################################################

def latest_file_fn(fn_no_date, folder):
    file_list = sorted(os.listdir((folder)))
    return [s for s in file_list if fn_no_date in s][-1]

def get_path_for_save_value_to_file(filename):
    now = datetime.datetime.now()
    full_path = log_single_val_dir + os.path.splitext(filename)[0] + '/' + now.strftime('%Y%m') + filename + '.dat'
    return full_path

def date_str_in(date_str, start_date_str=None, end_date_str=None):
    date = datetime.datetime.strptime(date_str, __TIME_FORMAT_STR__)
    start_date = datetime.datetime.min if start_date_str is None else datetime.datetime.strptime(start_date_str, __TIME_FORMAT_STR__) #
    end_date = datetime.datetime.now() if end_date_str is None else datetime.datetime.strptime(end_date_str, __TIME_FORMAT_STR__) #
    return start_date <= date <= end_date

def save_value_to_file(val, filename):
    """Appends a given value 'val' to a text file with filename 'yymmdd_filename' (e.g. 130101_temperature.dat) and adds the current date and time (format'yymmdd hhmmss) separated by a tab. '
    """
    full_path = get_path_for_save_value_to_file(filename)
    folder = os.path.dirname(full_path)
    if not os.path.isdir(log_single_val_dir):
        os.mkdir(log_single_val_dir)
    if not os.path.isdir(folder):
        os.mkdir(folder)
    now = datetime.datetime.now()
    fil = open(full_path, 'a')
    fil.write(now.strftime('%Y%m%d-h%Hm%Ms%S') + '\t' + str(val) + '\n')
    fil.close()

def save_values_to_file(val, filename, full_path=None):
    full_path = get_path_for_save_value_to_file(filename) if full_path is None else full_path
    folder = os.path.dirname(full_path)
    if not os.path.isdir(log_single_val_dir):
        os.mkdir(log_single_val_dir)
    if not os.path.isdir(folder):
        os.mkdir(folder)
    now = datetime.datetime.now()
    fil = open(full_path, 'a')
    fil.write(now.strftime('%Y%m%d-h%Hm%Ms%S') + '\t' + '\t'.join(str(v) for v in val) + '\n')
    fil.close()

def get_last_value_from_file(filename, flg_out_date=False):
    folder = os.path.dirname(get_path_for_save_value_to_file(filename))
    file_list = sorted(os.listdir((folder)))
    last_file_name = [s for s in file_list if filename in s][-1]
    fil = open(os.path.join(folder, last_file_name), 'r')
    line_str_list = fil.readlines()[-1].split('\t')
    fil.close()

    if 'fit_params' in filename or 'history' in filename:
        val = np.array(line_str_list[-1].rstrip('\n'))
    else:
        val = float(line_str_list[-1].rstrip('\n'))
    if flg_out_date == True:
        date = datetime.datetime.strptime(line_str_list[0], '%Y%m%d-h%Hm%Ms%S')
        return val, date
    return val

def get_last_values_from_file(filename, flg_out_date=False, full_path=None):
    if full_path is None:
        folder = os.path.dirname(get_path_for_save_value_to_file(filename))
        file_list = sorted(os.listdir((folder)))
        last_file_name = [s for s in file_list if filename in s][-1]
        full_path = os.path.join(folder,last_file_name)
    else:
        full_path = get_path_for_save_value_to_file(filename) if full_path is None else full_path
        full_path = get_path_for_save_value_to_file(filename) if full_path is None else full_path
    fil = open(full_path, 'r')

    line_str_list = fil.readlines()[-1].split('\t')
    line_str_list[-1].rstrip('\n')
    fil.close()
    val = []
    for i in line_str_list[1:]:
        try:
            val.append(float(i))
        except:
            val.append(i.rstrip('\n'))
    if flg_out_date is True:
        date = datetime.datetime.strptime(line_str_list[0], '%Y%m%d-h%Hm%Ms%S')
        return val, date
    return val

def get_values_time_span(filename, start_date_str, end_date_str=None):
    folder = os.path.dirname(get_path_for_save_value_to_file(filename))
    file_list = sorted(os.listdir(folder))
    result = {'dates': [], 'data': []}
    for fn in file_list:
        try:
            file_date_str = datetime.datetime.strptime(fn[0:6], '%Y%m').strftime(__TIME_FORMAT_STR__)
        except:
            file_list.remove(fn)
            continue
        with open("{}/{}".format(folder, fn), 'r') as f:
            for l in f:
                l = l.rstrip('\n').split('\t')

                if date_str_in(l[0], start_date_str, end_date_str):
                    result['dates'].append(datetime.datetime.strptime(l[0], __TIME_FORMAT_STR__))
                    result['data'].append(l[1:])
    result['data'] = np.array(result['data'])
    return result

def plot_single_values(filename, start_date_str, end_date_str=None, grating='m'):
    values = get_values_time_span(filename=filename, start_date_str=start_date_str, end_date_str=end_date_str)
    if end_date_str is None:
        end_date_str = datetime.datetime.now()
    else:
        end_date_str = datetime.datetime.strptime(end_date_str, __TIME_FORMAT_STR__)
    grating_dict = {'h': 1. / 60. / 60., 'm': 1. / 60., 's': 1.}
    labeldict = {'magnet_gradients': ['x', 'y'], 'confocal_pos': ['x', 'y', 'z'], 'magnet_pos': ['x', 'y', 'z', 'phi'], 'current_local_oscillator_freq': 'local oscillator'}
    legenddict = {'magnet_gradients': 'MHz/mu m', 'confocal_pos': 'mu m', 'magnet_pos': 'mu m', 'current_local_oscillator_freq': 'MHz'}
    precisiondict = {'magnet_gradients': 6, 'confocal_pos': 4, 'magnet_pos': 4, 'current_local_oscillator_freq': 3}
    tdelta = np.array([(values['dates'][i] - end_date_str).total_seconds() for i in range(len(values['dates']))]) * grating_dict['{}'.format(grating)]
    num_single_values = len(values['data'][0])
    num_dp = len(tdelta)
    data = dict()
    for num in range(num_single_values):
        data[num] = np.array([values['data'][i][num] for i in range(num_dp)]).astype(float)
    import matplotlib.pyplot as plt
    import matplotlib.ticker
    fig, axes = plt.subplots(num_single_values)
    fig.suptitle(filename + ' since ' + '{}'.format(values['dates'][0].strftime('%Y%m%d-h%Hm%Ms%S')))
    if num_single_values != 1:
        for sv in range(num_single_values):
            axes[sv].plot(tdelta, data[sv], 'o-', label=labeldict[filename][sv])
            axes[sv].yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter('%.{}f'.format(precisiondict[filename])))
            axes[sv].legend()
            axes[sv].set_ylabel(legenddict[filename])
            axes[sv].set_xlabel('time [{}]'.format(grating))
    else:
        axes.plot(tdelta, data[0], 'o-', label=labeldict[filename])
        axes.legend()
        axes.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter('%.{}f'.format(precisiondict[filename])))
        axes.set_ylabel(legenddict[filename])
        axes.set_xlabel('time [s]')
    plt.show()

# def recompile_ui_file():
#     fold = "{}/qtgui".format(os.path.dirname(__file__))
#     name = "transition_tracker"
#     uipath = r"{}/{}.ui".format(fold, name)
#     pypath = r"{}/{}_gui.py".format(fold, name)
#     with open(pypath, 'w') as f:
#         compileUi(uipath, f)
#     reload(transition_tracker_gui)
# class Wrapper():# this is there because our rabi is slightly offseted by a phase
#     def __init__(self,rp):
#         self.pi=rp.pi-rp.phi/(2*np.pi*rp.omega*2) #pi in µs -> f in MHz
#         self.pi2=rp.pi2-rp.phi/(2*np.pi*rp.omega*2)
#         self.amp=rp.amp
#         self.omega=rp.omega
#         self.period=rp.period
#         self.phi=rp.phi
#         self.rp=rp

class RPWrapper:
    def __init__(self, rp):
        self.rp = rp
        self.Phi_dict = rp.phi_dict
        self.phi=rp.phi
        try: #if neither amp, or period, or omega is given to the rp, it doesn't calculate the pi and pi/2
            self.amp=rp.amp
            self.omega=rp.omega
            self.period=rp.period
            self.pi=self.get_corrected_pi() #pi in µs -> f in MHz
            self.pi2=self.get_corrected_pi2()
        except:
            print("Could not crate RPWrapper in tt.\nCan a 22pF capacitor kill you?") #just joking, it doesn't


    def _get_phi_for_amp(self):
        #d = self.Phi_dict
        d = pd.DataFrame(list(self.Phi_dict.items()), columns=["amp", "phi"]).astype(float)

        #print(d)
        amps = np.array(d['amp'])
        phis = np.array(d['phi'])
        order = np.argsort(amps)
        #print(amps,phis)
        return np.interp(self.amp, amps[order], phis[order])

    
    def get_corrected_pi(self):
        phi_corr = self._get_phi_for_amp()
        #freq=self._get_freq_for_amp()
        #print("corrected phi:",phi_corr,self.amp)
        omega = self.rp.omega
        target=np.pi
        return (target-phi_corr)/(omega*2*np.pi)

    def get_corrected_pi2(self):
        phi_corr = self._get_phi_for_amp()
        #freq=self._get_freq_for_amp()
        omega = self.rp.omega
        target=np.pi/2

        start = .100  # start of transition
        end = .150    # end of transition

        t2=(target-phi_corr)/(omega*2*np.pi)

        def function1(t1,t2,ttot,start,end):
            if ttot < start:
                t = t1
            elif ttot > end:
                t = t2
            else:
                # linear interpolation 	between t1 and t2
                alpha = (ttot - start) / (end - start)  # 0 at start, 1 at end
                t = t1 * (1 - alpha) + t2 * alpha
            return t
        
        return function1(self.pi/2,t2,self.pi,start,end)
    

class RabiParametersStatic:
    def __init__(self, filepath, transition_name=None):
        self.filepath = filepath
        self.transition_name = transition_name

    @property
    def filename(self):
        return os.path.splitext(os.path.basename(self.filepath))[0]

    def __deepcopy__(self, memo):
        return self

    @property
    def filepath(self):
        return self._filepath

    @filepath.setter
    def filepath(self, val):
        if hasattr(self, '_filepath'):
            raise Exception('The filepath must not be be set after instantiation.')
        elif not isinstance(val, str):
            raise Exception('filepath must be string')
        else:
            self._filepath = val
            self.set_data_array()

    def read_file_data(self, fp=None):
        fp = self.filepath if fp is None else fp
        return np.genfromtxt(fp, dtype=str, delimiter='\t')

    def update_file(self, data):
        self.archive_file()
        data.to_csv(self.filepath, "\t", index=False)
        self.set_data_array()

    def generate_linear_file(self, maxfreq_l):
        if type(maxfreq_l) is float:
            maxfreq_l = [maxfreq_l]
        import qudi.logic.mcas.elements as E
        n = 11
        arr = np.array(
            list(
                product(
                    *([map(lambda x: "{:.6f}".format(x), E.round_to_amplitude_granularity(np.linspace(0., 1., n)))] * len(maxfreq_l))
                )
            )
        )
        arr = [np.insert(arr, [len(maxfreq_l)], str(idx), axis=1) for idx, item in enumerate(maxfreq_l)]
        arr = [np.hstack([item, o * item[:, idx].astype(float).reshape(-1, 1)]) for idx, (item, o) in enumerate(zip(arr, maxfreq_l))]
        arr = np.vstack(arr)
        arr = np.insert(arr, [len(maxfreq_l) + 2], pd.to_datetime('now').__str__(), axis=1)
        d = collections.OrderedDict()
        for key, val in zip(["amp{}".format(i) for i in range(len(maxfreq_l))] + ['transition', 'omega', 'date'], arr.T):
            d[key] = val
        self.update_file(pd.DataFrame.from_dict(d))

    def replace_data(self):
        pass

    def archive_file(self):
        filename = os.path.splitext(os.path.basename(self.filepath))[0]
        fil = os.path.join(TT_LOG_DIR, 'rabi_parameters_archive', filename)
        date = datetime.datetime.fromtimestamp(os.path.getmtime(self.filepath)).strftime('%Y%m%dh%Hm%Ms%S')
        if not os.path.isdir(fil):
            os.makedirs(fil)
        shutil.copy(self.filepath, os.path.join(fil, '{}-{}_{}.dat'.format(date, nowstr(), filename)))

    def file_header(self, tnf,add_phi=False):
        if add_phi:
            return ["amp{}".format(i) for i in range(tnf)] + ['transition', 'omega',"phi", 'date']
        else:
            return ["amp{}".format(i) for i in range(tnf)] + ['transition', 'omega', 'date']

    def data_dataframe(self, fp=None):
        fp = self.filepath if fp is None else fp
        fd = self.read_file_data(fp=fp)
        self.tnf = len([i for i in list(fd[0]) if 'amp' in i])
        ecn = self.file_header(self.tnf,add_phi=True)
        cn = list(fd[0])
        #print("-------------------------")
        #print(fd,ecn,cn,sep="\n")
        if cn != ecn:
            ecn = self.file_header(self.tnf,add_phi=False)
            if cn != ecn:
                raise Exception('File column names not allowed. expected {}, found{}'.format(ecn, cn))
            
        df=pd.DataFrame(data=fd[1:, :], columns=fd[0, :])
        #print(fd,ecn,cn,sep="\n")
        self.df=df
        if "phi" in df.columns:
            #print("new phi")
            self.phi_dict={row["amp0"]:row["phi"] for i,row in df.iterrows()} #You should not use any function with "iter" in its name for more than a few thousand rows or you will have to get used to a lot of waiting.
            self.phi=np.mean(df.phi.unique().astype(float)) #I know this is a terrible way to solve the problem of getting access to phi in the rabi parameter file. If you know a better way, do it! (and tell me)
        else:
            self.phi_dict={row["amp0"]:0 for i,row in df.iterrows()} #You should not use any function with "iter" in its name for more than a few thousand rows or you will have to get used to a lot of waiting.
            self.phi=0

        #print("DF_______________",df)
        return df

    def set_data_array(self):
        out = self.data_dataframe().values
        if '' in out:
            raise Exception("Error while loading file '{}'".format(self.filepath))
        else:
            self.data_array = out

    @property
    def amp_rabi_freq(self):
        nonlinear_params = np.delete(self.data_array, [self.tnf, self.data_array.shape[1] - 1], axis=1)
        val = np.array(nonlinear_params[:, :self.tnf], dtype=float), np.array(nonlinear_params[:, self.tnf:2 * self.tnf], dtype=float)
        if self.tnf == 1:
            val = tuple([np.squeeze(i, 1) for i in val])
        return val

    def calc_omegas(self, amplitude):
        amp, rabi_freq = self.amp_rabi_freq
        return np.array(scipy.interpolate.griddata(amp, rabi_freq, amplitude, method='linear'))

    def calc_amplitudes(self, omega):
        amp, rabi_freq = self.amp_rabi_freq
        return np.array(scipy.interpolate.griddata(rabi_freq, amp, omega, method='linear'))

    def amplitude(self, **kwargs):
        key, val, tni = self.parse(**kwargs)
        if 'amplitude' in kwargs:
            val = kwargs['amplitude']
        else:
            val = self.calc_amplitudes(self.omega(**kwargs))
        self.check_amplitudes(val, **kwargs)
        return self.deparse(tni, val)

    def check_amplitudes(self, val, **kwargs):
        try:
            anynan = np.any(np.isnan(val))
        except:
            try:
                isstr = np.array(val).dtype.kind == str
            except:
                raise Exception('The given ampitudes {} neither could be tested for np.nan nor are they some kind of string type: {}'.format(val, type(val)))
            if not isstr:
                raise Exception('I DONT KNOW WHATS GOING ON .Amplitudes: {}, kwargs: {}'.format(val, kwargs))
        if anynan:
            raise Exception('For at least one of given parameters, no valid amplitude could be obtained which resulted in the value NaN. Amplitudes: {}, kwargs: {}'.format(val, kwargs))

    def omega(self, **kwargs):
        key, val, tni = self.parse(**kwargs)
        fd = {'omega': (lambda x: x),
              'period': (lambda x: 1. / x),
              'pi': (lambda x: .5 / x),
              'pi2': (lambda x: .25 / x),
              'amplitude': (lambda x: self.calc_omegas(amplitude=self.amplitude(amplitude=x)))}
        return self.deparse(tni, fd[key](val))

    def period(self, **kwargs):
        return 1. / self.omega(**kwargs)

    def pi(self, **kwargs):
        return 0.5 / self.omega(**kwargs)

    def pi2(self, **kwargs):
        return 0.25 / self.omega(**kwargs)

    def is_valid_input(self, val):
        ctnf1shape1 = self.tnf == 1 and len(val.shape) == 1
        ctnf1shape2 = self.tnf == 1 and len(val.shape) == 2 and val.shape[1] == 1
        ctnf2shape1 = self.tnf == 2 and len(val.shape) == 2 and val.shape[1] == 2
        if ctnf1shape1 or ctnf1shape2 or ctnf2shape1:
            return val
        else:
            raise ValueError('Combination is not allowed: val.shape: {}, tnf: {}'.format(val.shape, self.tnf))

    def parse(self, **kwargs):
        tni, kwargs = self.pop_tni(**kwargs)
        key, val = list(kwargs.items())[0]
        val = np.array(val)
        if len(val.shape) > 2:
            raise Exception('Arrays must be 1D or 2D. Given shape is {}'.format(val.shape))
        elif len(val.shape) == 2:
            if val.shape[1] > self.tnf:
                raise ValueError(
                    'Too many columns. Maybe you need to transpose the input matrix? The input matrix has shape {} but'
                    ' the input rabi file includes only {} transition(s).'.format(val.shape, self.tnf))
            if val.shape[1] > len(tni):
                raise ValueError('variable tni assumes maximally {} columns in input value. Found {}'.format(len(tni), val.shape[1]))
            out = np.zeros([val.shape[0], self.tnf])
            for i, vali in enumerate(tni):
                out[:, vali] = val[:, i]
            val = out
        elif len(val.shape) == 1:
            if self.tnf != 1:
                raise ValueError('Input can only be 1D, if file contains one single transition')
        elif len(val.shape) == 0:
            raise Exception('Arrays must be 1D or 2D. Given shape is {}'.format(val.shape))
        self.is_valid_input(val)
        return key, val, tni

    def deparse(self, tni, val):
        if len(val.shape) == 2:
            val = val[:, tni]
        return val

    def pop_tni(self, **kwargs):
        if len(kwargs) == 2:
            tni = kwargs.pop('tni')
        elif len(kwargs) == 1:
            tni = None
        elif len(kwargs) == 0:
            if len(kwargs) != 1:
                raise ValueError('Not allowed')
        if tni is None:
            tni = np.arange(self.tnf)
        tni = np.array(tni)


        if len(tni.shape) != 1:
            raise Exception("shape of 'transition_number' must be 1D (list or np.ndarray)")
        if (tni >= 0).all() and (tni < self.tnf).all():
            return tni, kwargs
        else:
            raise ValueError('Something is wrong either with the given value for tni. val: {}, tnf: {}'.format(tni, self.tnf))

    def plot(self, **kwargs):
        sample_amp = np.linspace(0.01, 1., 100)
        mino = 0.
        maxo = self.omega(amplitude=[1.0])[0]
        sample_omega = np.linspace(mino, maxo, 100)
        arf, orf = self.amp_rabi_freq
        eorf = self.omega(amplitude=sample_amp)
        earf = self.amplitude(omega=sample_omega)
        if len(kwargs) == 0:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(1, 2)
            ax0 = ax[0]
            ax1 = ax[1]
            fig.canvas.set_window_title(self.transition_name)
            fig.suptitle(self.filename)
        elif len(kwargs) == 2:
            ax0 = kwargs['ax0']
            ax1 = kwargs['ax1']
        else:
            raise Exception('Error: {}'.format(kwargs))
        ax0.set_title("{}, {}".format(self.filename, self.transition_name))
        ax0.set_xlabel('rabi frequency [MHz]')
        ax0.set_ylabel('amplitude [a.u.]')
        ax1.set_xlabel('amplitude [a.u.]')
        ax1.set_ylabel('rabi frequency [MHz]')
        ax1.set_title("{}, {}".format(self.filename, self.transition_name))
        ax0.plot(orf, arf, 'o', sample_omega, earf, '-')
        ax1.plot(arf, orf, 'o', sample_amp, eorf, '-')
        if len(kwargs) == 0:
            plt.show()

class RabiParametersSingle(object):
    def __init__(self, rp, tni=None, **kwargs):
        self.rp = rp #rabi parameters
        self.is_valid_input(**kwargs)
        self.set_statics(tni=tni, **kwargs)

    def set_statics(self, tni=None, round_to_full_sample=True, **kwargs):
        key, val = list(kwargs.items())[0]
        val = np.array(val)
        zero_d_input = False
        if len(val.shape) == 0:
            zero_d_input = True
            val = np.array([val])
            if self.rp.tnf == 2:
                val = np.array([val])
        elif len(val.shape) == 1:
            if self.rp.tnf == 2:
                val = np.array([val])
        if key == 'amp':
            kwargs = {'amplitude': val}
        else:
            kwargs[key] = val
        amp = getattr(self.rp, 'amplitude')(tni=tni, **kwargs)
        omega = getattr(self.rp, 'omega')(tni=tni, **kwargs)
        try:
            self.phi=self.rp.phi
            self.phi_dict=self.rp.phi_dict
        except Exception as e:
            print("Rabi Parameters not working!",e)
        if zero_d_input:
            amp = amp[0]
            omega = omega[0]
            if self.rp.tnf == 2:
                amp = amp[0]
                omega = omega[0]
        else:
            if self.rp.tnf == 2:
                amp = amp[0]
                omega = omega[0]
        self.amp = amp
        if round_to_full_sample:
            self.period = np.around(12e3 / (omega)) / 12e3
            self.omega = 1 / self.period
            self.pi = np.around(12e3 / (2 * omega)) / 12e3
            self.pi2 = np.around(12e3 / (4 * omega)) / 12e3
        elif not round_to_full_sample:
            self.period = 1. / omega
            self.omega = omega
            self.pi = 0.5 / omega
            self.pi2 = 0.25 / omega

    def is_valid_input(self, **kwargs):
        if len(kwargs) != 1:
            raise ValueError('Exactly one input must be given. (Instead of {})'.format(len(kwargs)))
        val = np.array(list(kwargs.values())[0])
        if len(val.shape) not in [0, 1]:
            raise ValueError('Input value must be 0D or 1D but was {}'.format(len(val.shape)))
        if len(val.shape) == 1 and val.shape[0] > self.rp.tnf:
            raise ValueError('Input value is too large for given rabi file. ({}, tnf: {}'.format(val.shape[0], self.rp.tnf))
        if list(kwargs.keys())[0] not in ['amp', 'omega', 'period']:
            raise Exception("input parameter names must be in ['amp', 'omega', 'period'], but {} was given".format(list(kwargs.keys())[0]))
        return kwargs

class Transition:
    def __init__(self, name, parent=None, current_frequency=None):
        self.parent = parent
        if current_frequency is not None:
            self.current_frequency = current_frequency
        self.name = name
        self.set_meta()
    
    name = misc.ret_property_typecheck('name', str)
    ms_state = misc.ret_property_list_element('ms_state', [1.5, 0.5,-0.5, -1.5]) # FIXME how to get the _spin_number from TransitionTracker here?
    print("ms state in Transition:\n", ms_state)
    spin_type = misc.ret_property_list_element('spin_type', ['14n', '13c','29si'])
    current_frequency = misc.ret_property_typecheck('current_frequency', Number)

    @property
    def start_level(self):
        return np.argwhere(np.array(self.angular_momentum_arr)==self.start_angular_momentum)[0,0]

    @property
    def end_level(self):
        return np.argwhere(np.array(self.angular_momentum_arr)==self.end_angular_momentum)[0,0]

    @property
    def angular_momentum_arr(self):
        if self.spin_type == '14n':
            return np.array([+1, 0, -1])
        else:
            return np.array([.5, -.5])

    def set_meta(self):
        name = TransitionTracker.correct_transition_name(self.name)
        self.nuc, ms = name.split(' ')
        self.ms_state = float(ms[2:])
        self.spin_type = '14n' if '14n' in self.nuc else '13c' #Fixme should be 29si?
        if self.spin_type == '14n':
            self.start_angular_momentum, self.end_angular_momentum = sorted([0, int(self.nuc[-2:])])
        else:
            self.start_angular_momentum = -.5
            self.end_angular_momentum = +.5

class Couplings():
    def __init__(self):
        # Load data into dfs and get list of spins
        if os.path.exists(os.path.join(TT_LOG_DIR, "couplings_df_m32_live.hdf")):
            df_long_m32 = pd.read_hdf(os.path.join(TT_LOG_DIR, "couplings_df_m32_live.hdf"), key='data')
            # Pivot to square
            spins_m32 = natsorted(set(df_long_m32['spin_i']) | set(df_long_m32['spin_j']))
        elif os.path.exists(os.path.join(TT_LOG_DIR, "couplings_df_m32_backup.hdf")):
            df_long_m32 = pd.read_hdf(os.path.join(TT_LOG_DIR, "couplings_df_m32_backup.hdf"), key='data')
            # Pivot to square
            spins_m32 = natsorted(set(df_long_m32['spin_i']) | set(df_long_m32['spin_j']))
        if os.path.exists(os.path.join(TT_LOG_DIR, "couplings_df_p32_live.hdf")):
            df_long_p32 = pd.read_hdf(os.path.join(TT_LOG_DIR, "couplings_df_p32_live.hdf"), key='data')
            # Pivot to square
            spins_p32 = natsorted(set(df_long_p32['spin_i']) | set(df_long_p32['spin_j']))
        elif os.path.exists(os.path.join(TT_LOG_DIR, "couplings_df_p32_backup.hdf")):
            df_long_p32 = pd.read_hdf(os.path.join(TT_LOG_DIR, "couplings_df_p32_backup.hdf"), key='data')
            # Pivot to square
            spins_p32 = natsorted(set(df_long_p32['spin_i']) | set(df_long_p32['spin_j']))

        # combine spins if different spins in m32 and p32 dataframes
        self.spins = []
        for spin in spins_m32 + spins_p32:
            if spin not in self.spins:
                self.spins.append(spin)

        # create new dataframe consisting of all spins
        # fill up the larger dataframe with values from the respective smaller dataframes
        self.df_m3_2 = pd.DataFrame(index=self.spins, columns=self.spins, dtype=np.float64)
        for spin_i in self.spins:
            for spin_j in self.spins:
                try:
                    self.df_m3_2.at[spin_i, spin_j] = float(df_long_m32.loc[(df_long_m32.spin_i ==spin_i) & (df_long_m32.spin_j ==spin_j)].coupling)
                except (ValueError, TypeError):
                    self.df_m3_2.at[spin_i, spin_j] = np.nan

        self.df_p3_2 = pd.DataFrame(index=self.spins, columns=self.spins, dtype=np.float64)
        for spin_i in self.spins:
            for spin_j in self.spins:
                try:
                    self.df_p3_2.at[spin_i, spin_j] = float(df_long_p32.loc[(df_long_p32.spin_i ==spin_i) & (df_long_p32.spin_j ==spin_j)].coupling)
                except (ValueError, TypeError) as e:
                    print("error with creating df p3/2:",e)
                    self.df_p3_2.at[spin_i, spin_j] = np.nan


    # def save_to_hdf(self):
    #     print("Save hdf in tt")
    #     # Convert to long format, suppress pandas FutureWarning
    #     with warnings.catch_warnings():
    #         warnings.simplefilter('ignore', FutureWarning)
    #         stacked = self.df.stack(dropna=False)
    #     df_long = stacked.reset_index()
    #     df_long.columns = ['spin_i', 'spin_j', 'coupling']
    #     df_long['coupling'] = df_long['coupling'].astype('float64')
    #     # Save
    #     df_long.to_hdf(os.path.join(TT_LOG_DIR, "couplings_df_live.hdf"), key='data', mode='w', format='table')

    # def save_backup_hdf(self):
    #     print("Save backup hdf in tt")
    #     # Convert to long format, suppress pandas FutureWarning
    #     with warnings.catch_warnings():
    #         warnings.simplefilter('ignore', FutureWarning)
    #         stacked = self.df.stack(dropna=False)
    #     df_long = stacked.reset_index()
    #     df_long.columns = ['spin_i', 'spin_j', 'coupling']
    #     df_long['coupling'] = df_long['coupling'].astype('float64')
    #     # Save
    #     df_long.to_hdf(os.path.join(TT_LOG_DIR, "couplings_df_backup.hdf"), key='data', mode='w', format='table')

    def get_coupling(self, spin1, spin2,subspace="m32"):
        if (subspace=="m32") or (subspace=='-3/2'):
            df=self.df_m3_2
        elif (subspace=="p32") or (subspace=='+3/2'):
            df=self.df_p3_2

        c1 = df.loc[spin1, spin2]
        c2 = df.loc[spin2, spin1]
        return np.nanmean([c1,c2])
    
    def build_graph_from_df(self,subspace="-3/2", threshold: float = 0.5):
        """
        Build adjacency dictionary from coupling DataFrame:
        Only include edges with known coupling > threshold.

        Returns:
            adj: dict node -> list of neighbor nodes
            get_coupling(u,v): function returning coupling (float) or None
        """
        df=[self.df_m3_2,self.df_p3_2][subspace=="+3/2"]

        nodes = list(df.index)
        adj = {node: [] for node in nodes}
        for i in nodes:
            for j in nodes:
                if i == j:
                    continue
                try:
                    v = df.at[i, j]
                except Exception:
                    v = float('nan')
                if pd.notna(v) and float(v) > threshold:
                    adj[i].append(j)

        def get_coupling(u, v):
            # Try both orders for robustness
            val = None
            if u in df.index and v in df.columns:
                val = df.at[u, v]
            if pd.isna(val):
                if v in df.index and u in df.columns:
                    val = df.at[v, u]
            return float(val) if pd.notna(val) else None

        return adj, get_coupling


    def find_all_simple_paths_to_target(self, adj, target, max_len=None,allowed_starts=None, avoid_spins=None):

        avoid_spins = set(avoid_spins or [])

        if target not in adj:
            return []

        nodes = list(adj.keys())
        max_len = max_len or len(nodes)
        paths = []

        # pick start nodes
        if allowed_starts is not None and len(allowed_starts) > 0:
            start_nodes = [s for s in allowed_starts if s in adj]
        else:
            start_nodes = nodes

        def dfs(current, visited, path):
            if len(path) > max_len:
                return
            if current == target:
                paths.append(path.copy())
                return
            for nb in adj.get(current, []):
                if nb in visited:
                    continue
                if nb in avoid_spins:
                    continue
                visited.add(nb)
                path.append(nb)
                dfs(nb, visited, path)
                path.pop()
                visited.remove(nb)

        for start in start_nodes:
            if start == target:
                continue
            if start in avoid_spins:
                continue
            if not adj.get(start):
                continue
            dfs(start, {start}, [start])

        # remove duplicates
        unique = []
        seen = set()
        for p in paths:
            key = tuple(p)
            if key in seen:
                continue
            seen.add(key)
            unique.append(p)

        unique.sort(key=lambda x: (len(x), x))
        return unique

    def chain_couplings_and_expected_time(self,path: list, get_coupling):
        """
        For a given path (list of nodes), return:
            couplings: list of floats for consecutive node pairs
            expected_time_s: expected measurement time in seconds (float)
        If any required coupling is missing, return (None, None)
        """
        couplings = []
        for a, b in zip(path[:-1], path[1:]):
            c = get_coupling(a, b)
            if c is None:
                return None, None
            couplings.append(float(c))

        inv_sum = sum(1.0 /(c) for c in couplings)
        if inv_sum <= 0:
            expected_time_s = float('inf')
        else:
            expected_time_s = inv_sum/2
        return couplings, expected_time_s


    def fmt_hz(self,hz: float):
        #"""Format coupling as '10Hz' if >=1, otherwise with 2 decimals '0.45Hz'"""
        if hz >= 0:
            return f"{round(hz,2)}Hz"
        else:
            return f"{hz:.2f}Hz"


    def format_chain_result(self,path, couplings, expected_time_s):
        """Return the human-readable string exactly like your example."""
        couplings_str = "-".join(self.fmt_hz(c) for c in couplings)
        if expected_time_s is None:
            time_str = "N/A"
        elif math.isinf(expected_time_s):
            time_str = "Inf"
        else:
            time_str = f"{expected_time_s * 1000.0:.2f} ms"
        chain_form = "-".join(path)
        return f"Chain: {chain_form}, {couplings_str}, Expected measurement time = {time_str}"

NA = np.nan  # compatible with older pandas

HDF_LIVE = os.path.join(TT_LOG_DIR, "register_df_live.hdf")
HDF_BACKUP = os.path.join(TT_LOG_DIR, "register_df_backup.hdf")
HDF_LOG_DIR = os.path.join(TT_LOG_DIR, "register_log")

def nowstr():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


class Register(object):
    """
    Pure logic / data class. Keeps DataFrame and provides:
      - calculate_transitions_from_detuning(bfield)
      - get_spin(spin_name, subspace, dd_method)
      - save_to_hdf() and save_backup_hdf()
    """

    def __init__(self):
        # Load existing or create default
        self.g_factors = gamma
        self.create_error=False
        self.df = None
        self._load_or_create()

        # Ensure string columns for keys (important for consistent filtering)
        for c in ['spin_name', 'subspace', 'dd_method']:
            if c in self.df.columns:
                # Keep NaNs but coerce non-null values to str
                self.df[c] = self.df[c].astype(object).where(self.df[c].isnull(), self.df[c].astype(str))


        # Ensure sensible dtypes for numeric-ish columns (but keep object fallback)
        self._ensure_working_dtypes()
        self.df = self.df.fillna('').astype(str)
        self.tau_optimizer = TauOptimizer(os.path.join(TT_LOG_DIR, "corrected_plot_data.csv"))
        self.save_imediatly=True #set to false in console to make many changes at a time and not having to wait each time.

    def _load_or_create(self):
        # Attempt live, then backup, otherwise create defaults (kept from original)
        print("LOADING FROM LIVE:", HDF_LIVE)
        print("LOADING FROM BACKUP:", HDF_BACKUP)
        if os.path.exists(HDF_LIVE):
            try:
                self.df = pd.read_hdf(HDF_LIVE, key="data")
            except Exception:
                self.df = pd.read_hdf(HDF_BACKUP, key="data") if os.path.exists(HDF_BACKUP) else pd.DataFrame()
        elif os.path.exists(HDF_BACKUP):
            self.df = pd.read_hdf(HDF_BACKUP, key="data")
        else:
            # Create default sample dataset (kept similar to your original initial population)
            # Minimal example to keep same columns and typical structure.
            # If you want the large default payload from your original file, paste it here.
            data = {
                'spin_name': ['C1', 'C1', 'C1', 'C1'],
                'subspace': ['3/2', '1/2', '-1/2', '-3/2'],
                'dd_method': ['knillpi'] * 4,
                'trans': [2.267683080, 2.24519308, 2.22394308, 2.201943],
                'Azz': [0.02175] * 4,
                'Aperp': [0.02363] * 4,
                'ddrf_tau': [20] * 4,
                'ddrf_amp': [NA, NA, NA, 0.4],
                'ddrf_phase_inc': [NA, NA, NA, 0.72],
                'ddrf_phase_init': [NA, NA, NA, 0.72],
                'ddrf_phase_read': [NA, NA, NA, 0.72],
            }
            self.df = pd.DataFrame(data)

    def _ensure_working_dtypes(self):
        # Convert obvious numeric columns to numeric where possible.
        # But keep object for columns that can't be converted.
        for col in self.df.columns:
            # Skip key text columns
            if col in ('spin_name', 'subspace', 'dd_method'):
                continue
            series = self.df[col]
            # If largely numeric, convert to float
            # Use pandas.to_numeric with errors='coerce' to avoid exceptions
            coerced = pd.to_numeric(series, errors='coerce')
            # If at least one non-NaN after coercion, adopt float dtype; else keep object
            if coerced.notnull().any():
                self.df[col] = coerced.astype(float)
            else:
                # keep as object/string series but keep NaNs
                self.df[col] = series.astype(object)

    def _normalize_dtypes_for_storage(self, df_in):
        df_save = df_in.copy()

        for col in df_save.columns:
            # Try convert to numeric
            converted = pd.to_numeric(df_save[col], errors='coerce')

            # If at least one real number exists → treat column as float
            if converted.notnull().any():
                df_save[col] = converted.astype('float64')
            else:
                # store as string (object)
                df_save[col] = df_save[col].astype(str)

        return df_save


    def save_to_hdf(self,way=None):
        """
        Persist the live DataFrame to HDF (overwrites live file).
        """
        if self.create_error:
            sdjfd

        if way==None:
            way=HDF_LIVE

        print("SAVING TO:", way)

        try:
            df_save = self._normalize_dtypes_for_storage(self.df)
            df_save.to_hdf(path_or_buf=way, key='data', mode='w', format='table')
        except Exception as exc:
            # Be resilient: try to at least write a backup copy
            print("FAILED saving to LIVE:", exc)
            try:
                df_save.to_hdf(path_or_buf=HDF_BACKUP, key='data', mode='w', format='table')
            except Exception:
                # Last resort: raise error for caller to handle/log
                raise exc

    def save_backup_hdf(self):
        """
        Save a backup and timestamped log copy.
        """
        df_save = self._normalize_dtypes_for_storage(self.df)
        try:
            df_save.to_hdf(path_or_buf=HDF_BACKUP, key='data', mode='w', format='table')
        except Exception:
            pass
        try:
            if not os.path.exists(HDF_LOG_DIR):
                os.makedirs(HDF_LOG_DIR)
            log_path = os.path.join(HDF_LOG_DIR, "register_df_log" + nowstr() + ".hdf")
            df_save.to_hdf(path_or_buf=log_path, key='data', mode='w', format='table')
        except Exception:
            pass

    def get_spin(self, spin_name, subspace, dd_method,Tau_finder=False,comment=None):
        """
        Returns filtered DataFrame for a spin. Signature preserved.
        If subspace or dd_method == '_none_' the filter is ignored.
        """

        if 'spin_name' not in self.df.columns:
            return pd.DataFrame()

        df2 = self.df[self.df['spin_name'] == str(spin_name)].copy()

        if subspace != '_none_':
            df2 = df2[df2['subspace'] == str(subspace)]

        if dd_method != '_none_':
            df2 = df2[df2['dd_method'] == str(dd_method)]

        if Tau_finder and comment:
            print("choosing comment over Tau finder argument")
            pattern=comment
        elif comment:
            pattern=comment
        elif Tau_finder:
            pattern="reserved_for_tau_finder"

        if Tau_finder or comment:
            df2 = df2[df2['comment'] == pattern]

        

        # --- Convert numeric-like columns back to float ---
        for col in df2.columns:
            if col in ['spin_name', 'subspace', 'dd_method']:
                continue

            converted = pd.to_numeric(df2[col], errors='coerce')

            # Only convert column if at least one real number exists
            if converted.notnull().any():
                df2[col] = converted.astype(float)

            

        return df2.reset_index(drop=True)

        
    def add_column(self, name):
        if name in self.df.columns:
            return

        self.df[name] = ''


    def calculate_transitions_from_detuning(self, bfield):
        """
        Assign transition frequencies from measured detuning (in-place).
        Signature preserved.
        """
        def safe_float(val):
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        si_bath = bfield * self.g_factors['29si']
        c_bath = bfield * self.g_factors['13c']

        def row_trans(row):
            det = safe_float(row.get('detuning'))
            if det is None:
                return NA
            # Choose Si or C bath depending on spin name containing 'C'
            bath = c_bath if ('C' in str(row.get('spin_name'))) else si_bath
            return det + bath

        # Use .apply to preserve indices and avoid broadcasting rules surprises
        if 'detuning' in self.df.columns:
            self.df['trans'] = self.df.apply(row_trans, axis=1)
        else:
            # no detuning column, nothing to compute
            pass

    def set_value(
        self,
        spin_name,
        subspace,
        dd_method,
        column,
        value,
        row_number=0
    ):
        """
        Modify a value programmatically.

        Parameters
        ----------
        spin_name : str
        subspace : str
        dd_method : str
        column : str
            Column to modify.
        value : any
            Will be stored as string internally.
        row_number : int
            Index within the filtered result (0-based).
        """

        if column not in self.df.columns:
            raise ValueError(f"Column '{column}' does not exist.")

        mask = (
            (self.df['spin_name'] == str(spin_name)) &
            (self.df['subspace'] == str(subspace)) &
            (self.df['dd_method'] == str(dd_method))
        )

        filtered_indices = self.df.index[mask].tolist()

        if not filtered_indices:
            raise ValueError("No matching rows found.")

        if row_number >= len(filtered_indices):
            raise IndexError(
                f"row_number {row_number} out of range "
                f"(only {len(filtered_indices)} rows match)"
            )

        df_index = filtered_indices[row_number]

        # Always store as string (GUI stability rule)
        self.df.at[df_index, column] = str(value)

        if self.save_imediatly:
            print("call from set_value")
            self.save_to_hdf()

    def update_filtered(self, mask, column, value):
        """mask = (
    (register.df['spin_name'] == "xy") &
    (register.df['subspace'] == "bc") &
    (register.df['dd_method'] == "za"))"""
        
        print("matching:", np.sum(mask))
        indices = self.df.index[mask]
        self.df.loc[indices, column] = str(value)
        if self.save_imediatly:
            print("call from update_filtered")
            self.save_to_hdf()




class TauOptimizer: #for DDRF tau

    def __init__(self, dd_csv_path=None):
        self.dd_interp_y1 = None
        self.dd_interp_y2 = None
        self.dd_data = None
        self.DD_avrg = None

        if dd_csv_path is not None:
            data = pd.read_csv(dd_csv_path)
            self.dd_data = data

            # x/2 because DDRF uses a different tau definition than DD
            tau_vals = data.iloc[:, 0].values/2
            y1_vals  = data.iloc[:, 1].values
            y2_vals  = data.iloc[:, 2].values

            
            self.dd_interp_y1 = interp1d(
                tau_vals, y1_vals,
                kind='linear',
                bounds_error=False,
                fill_value="extrapolate"
            )
            self.dd_interp_y2 = interp1d(
                tau_vals, y2_vals,
                kind='linear',
                bounds_error=False,
                fill_value="extrapolate"
            )

            self.DD_avrg = np.mean([*y1_vals, *y2_vals])

    def _dd_lookup(self, tau):
        """
        Return (y1, y2, dd_score) for a given tau value.
        dd_score = min(|y1 - 0.5|, |y2 - 0.5|): distance from bad region,
        higher is better.
        Returns (None, None, None) if interpolators are unavailable.
        """
        if self.dd_interp_y1 is None:
            return None, None, None
        try:
            y1 = float(self.dd_interp_y1(tau))
            y2 = float(self.dd_interp_y2(tau))
            dd_score = min(abs(y1 - 0.45), abs(y2 - 0.45))
            return y1, y2, dd_score
        except Exception:
            return None, None, None

    def _score(self, physics_error_raw, drive_error, dd_score,
               w_phys, w_drive, w_dd, use_dd_weight):
        """Unified scoring: lower is better."""
        s = w_phys * physics_error_raw + w_drive * drive_error
        if use_dd_weight and dd_score is not None:
            # Linear: subtract distance from bad region.
            # Further from 0.5 -> higher dd_score -> lower total score -> preferred.
            s -= w_dd * dd_score
        return s

    def _compute_candidate(self, k, n, wL, Azz, N, drive_freq,
                            w_phys, w_drive, w_dd, use_dd_weight):
        tau1 = k * np.pi / wL
        tau2 = (np.pi * n) / (N * Azz)

        tau_raw  = 0.5 * (tau1 + tau2)
        tau_disc = int(tau_raw * drive_freq) / drive_freq

        physics_error_raw = abs(tau1 - tau2)
        drive_error       = abs(tau_disc - tau_raw)

        # DD lookup at the quantised tau
        y1_disc, y2_disc, dd_score_disc = self._dd_lookup(tau_disc)

        # DD lookup at the physical (unquantised) tau
        y1_raw, y2_raw, dd_score_raw = self._dd_lookup(tau_raw)

        # scores
        score_disc = self._score(physics_error_raw, drive_error,
                                 dd_score_disc, w_phys, w_drive, w_dd, use_dd_weight)

        # Physical solution has no quantisation penalty by definition
        score_raw  = self._score(physics_error_raw, 0.0,
                                 dd_score_raw,  w_phys, w_drive, w_dd, use_dd_weight)

        return {
            # shared
            "tau1":               tau1,
            "tau2":               tau2,
            "k":                  k,
            "n":                  n,
            "physics_error_raw":  physics_error_raw,

            # quantised variant
            "tau_disc":           tau_disc,
            "drive_error":        drive_error,
            "y1_disc":            y1_disc,
            "y2_disc":            y2_disc,
            "dd_score_disc":      dd_score_disc,
            "score_disc":         score_disc,

            # physical (unquantised) variant
            "tau_raw":            tau_raw,
            "y1_raw":             y1_raw,
            "y2_raw":             y2_raw,
            "dd_score_raw":       dd_score_raw,
            "score_raw":          score_raw,
        }

    @staticmethod
    def _parse_solution_number(solution_number):
        """Accept int or iterable; always return a 1-based list."""
        if isinstance(solution_number, int):
            return [solution_number]
        indices = list(solution_number)
        if indices and indices[0] == 0:          # caller passed range(N)
            indices = [i + 1 for i in indices]
        return indices

    def get_best_tau(self,
                     spin_name,
                     N,
                     wL,
                     Azz,
                     drive_freq,
                     solution_number,
                     tau_max=40,
                     k_max=20000,
                     w_phys=1.0,
                     w_drive=1.0,
                     w_dd=1.0,
                     use_dd_weight=True):
        """
        Returns
        -------
        tau_disc_list : list of dicts, best quantised solutions in ranked order
        tau_raw_list  : list of dicts, best physical solutions in ranked order

        Both lists are ranked independently using the same scoring formula;
        the physical list simply has drive_error = 0 (no quantisation shift)
        and its DD lookup is evaluated at tau_raw rather than tau_disc.

        Parameters
        ----------
        w_phys  : weight on physics_error_raw  (|tau1 - tau2|)
        w_drive : weight on drive_error         (quantisation shift, disc only)
        w_dd    : weight on DD penalty          (linear, subtracted; higher dd_score = better)
        solution_number : int or iterable of 1-based indices
        """

        drive_freq = abs(drive_freq)
        candidates = []

        for k in range(-k_max, k_max + 1):
            if k == 0:
                continue

            tau1 = k * np.pi / wL
            if tau1 <= 0 or tau1 > tau_max:
                continue

            n_float = tau1 * N * Azz / (2 * np.pi)

            for n in [int(np.floor(n_float)), int(np.ceil(n_float))]:
                if n == 0:
                    continue

                c = self._compute_candidate(
                    k, n, wL, Azz, N, drive_freq,
                    w_phys, w_drive, w_dd, use_dd_weight
                )

                if c["tau_disc"] <= 0 or c["tau_disc"] > tau_max:
                    continue
                if c["tau_raw"]  <= 0 or c["tau_raw"]  > tau_max:
                    continue

                candidates.append(c)

        if not candidates:
            raise ValueError("No valid candidates found.")

        # ------------------------------------------------------------------
        # Deduplicate and rank QUANTISED solutions (key = tau_disc)
        # ------------------------------------------------------------------
        best_disc = {}
        for c in candidates:
            key = round(c["tau_disc"], 6)
            if key not in best_disc or c["score_disc"] < best_disc[key]["score_disc"]:
                best_disc[key] = c

        unique_disc = builtins.sorted(best_disc.values(), key=lambda x: x["score_disc"])

        # ------------------------------------------------------------------
        # Deduplicate and rank PHYSICAL solutions (key = tau_raw)
        # ------------------------------------------------------------------
        best_raw = {}
        for c in candidates:
            key = round(c["tau_raw"], 6)
            if key not in best_raw or c["score_raw"] < best_raw[key]["score_raw"]:
                best_raw[key] = c

        unique_raw = builtins.sorted(best_raw.values(), key=lambda x: x["score_raw"])

        # ------------------------------------------------------------------
        # Select requested solutions
        # ------------------------------------------------------------------
        indices = self._parse_solution_number(solution_number)

        tau_disc_list = []
        tau_raw_list  = []

        for idx in indices:
            if idx < 1 or idx > len(unique_disc):
                raise ValueError(
                    f"Requested solution #{idx} but only "
                    f"{len(unique_disc)} quantised solutions available."
                )
            if idx < 1 or idx > len(unique_raw):
                raise ValueError(
                    f"Requested solution #{idx} but only "
                    f"{len(unique_raw)} physical solutions available."
                )
            tau_disc_list.append(unique_disc[idx - 1])
            tau_raw_list.append(unique_raw[idx  - 1])

        #self._plot_results(spin_name, tau_disc_list, tau_raw_list)

        return tau_disc_list, tau_raw_list

    def _plot_results(self, spin_name, tau_disc_list, tau_raw_list):
        if self.dd_data is None:
            return

        tau_vals = self.dd_data.iloc[:, 0].values
        y1_vals  = self.dd_data.iloc[:, 1].values
        y2_vals  = self.dd_data.iloc[:, 2].values

        plt.figure(figsize=(10, 6))
        plt.plot(tau_vals, y1_vals, label="y1 (phase=0)",  color="black")
        plt.plot(tau_vals, y2_vals, label="y2 (phase=pi)", color="dimgray", linestyle="--")

        color_cycle = [
            "tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple",
            "tab:brown", "tab:pink",  "tab:gray",  "tab:olive","tab:cyan",
        ]

        for i, sol in enumerate(tau_disc_list):
            color = color_cycle[i % len(color_cycle)]
            plt.axvline(
                sol["tau_disc"], linestyle='-', color=color,
                label=f"#{i+1} disc={sol['tau_disc']:.4f} (score={sol['score_disc']:.4f})"
            )

        for i, sol in enumerate(tau_raw_list):
            color = color_cycle[i % len(color_cycle)]
            plt.axvline(
                sol["tau_raw"], linestyle='--', color=color, alpha=0.5,
                label=f"#{i+1} raw={sol['tau_raw']:.4f}  (score={sol['score_raw']:.4f})"
            )

        plt.axhline(0.5, linestyle=':', color="red", label="bad region (y=0.5)")

        plt.xlabel("Tau")
        plt.ylabel("DD signal")
        plt.title(f"Tau solutions for {spin_name}")
        plt.legend(fontsize=7)
        plt.grid()
        plt.show()


class TransitionTracker(LogicBase):
    #_hist = ConfigOption('hist', {'click_channel': 1, 'start_channel': 5, 'binwidth': 1000, 'number_of_bins': 1000})
    _spin_number = ConfigOption('spin_number', 1.5)
    _current_spins = ConfigOption('current_spins', default = '')
    _e_gate_dur = ConfigOption('e_gate_dur', default = 0.128)
    c13_list = []#'13c5']#['13c414', '13c90', '13c13', '13c6', '13c-5', '13c-6']
    si29_list = [] ######          THIS MUST BE LOWERCASE !!!!!!!!!!!!!!!!!!!!!!!!
    transitions = misc.ret_property_array_like_typ('transitions', Transition)
    
    mcas_dict_holder         = Connector(interface ='McasDictHolderInterface', optional = True) # This is only needed to check the AWG output amplitude
    ple_logic                = Connector(interface = 'LaserScannerLogic', optional = True) #ok for refocus
    powerstabilization_logic = Connector(interface = 'PowerStabilizationLogic', optional = True) #ok for refocus
    
    update_tt_nuclear_gui = Signal()
    update_tt_electron_gui = Signal() #is it connected?
    strong_spins_list=['14N', '13C414', '13C90','29Si8', '29Si8.00',"29Si2.2","29Si8.74"]

    def _optional_module(self, name):
        """Return the connected module, or None (with a warning) if it is not in the config."""
        try:
            module = getattr(self, name)()
        except Exception:
            module = None
        if module is None:
            self.log.warning("Optional module '{}' is not connected in the config; "
                            "scripts that need it will not work.".format(name))
        return module

    def __init__(self,config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        self.load_current_spin()
        self._awg = self._optional_module('mcas_dict_holder')
        self._ple_logic= self._optional_module('ple_logic')
        self._powerstabilization_logic= self._optional_module('powerstabilization_logic')

        self.g_factors = gamma # import from NVHam
        self.connect_signals()  # todo
        self.register=Register()
        self.couplings=Couplings()
        self.reload_nuclear_parameters()
        self.mw_mixing_frequency_L = get_last_value_from_file('mw_mixing_frequency_L')
        self.mw_mixing_frequency_C = get_last_value_from_file('mw_mixing_frequency_C')
        self.mw_mixing_frequency_R = get_last_value_from_file('mw_mixing_frequency_R')
        self.ple_A2 = get_last_value_from_file('ple_A2')
        self.ple_A2_fit_params = get_last_value_from_file('ple_A2_fit_params')
        self.interferometer_fit_params = get_last_value_from_file('interferometer_fit_params')
        self.interferometer_history = get_last_value_from_file('interferometer_history')
        self.ple_A1 = get_last_value_from_file('ple_A1')
        self.ple_A1_fit_params = get_last_value_from_file('ple_A1_fit_params')
        self.ple_repump = get_last_value_from_file('ple_repump') # we are not using itm  right?

        # self.xyz = pi3d.get_last_values_from_file('xyz')
        self.current_local_oscillator_freq = 0. # get_last_value_from_file('current_local_oscillator_freq') #also not using it.
        self.zero_field_splitting = get_last_value_from_file('zfs')
        self.e_transitions = np.arange(-1*self._spin_number,self._spin_number+1,1)
        self.e_transitions = [str(spin_state) if spin_state < 0 else "+" + str(spin_state) for spin_state in self.e_transitions]
        self.transition_name_list = [self.e_transitions] + [['+0.5', '-0.5']] * (len(self.c13_list)+len(self.si29_list))
        self.states_list = [range(len(i)) for i in self.transition_name_list]
        self.spin_name_list = ['e'] + self.c13_list + self.si29_list
        self.set_h_diag()
        self.set_ntd() #nuclear transition dict
        self.load_transitions()
        if not self._awg.mcas_dict.debug_mode:
            self.load_rabi_parameters()
        else:
            print("TT: AWG in debug mode")
        self.update_stuff()
        
        # changed gammas on 26.10.2026 from 28031.6 to value from NVHam: -28031.67956263535.
        # Note the difference in the sign.
        self.register.calculate_transitions_from_detuning((self.mw_mixing_frequency_L+self.mw_mixing_frequency_R)/(2*self.g_factors['e']))
        self.si_bath = self.g_factors['29si'] * (self.mw_mixing_frequency_L+self.mw_mixing_frequency_R)/(2*self.g_factors['e'])
        self.c_bath = self.g_factors['13c'] * (self.mw_mixing_frequency_L+self.mw_mixing_frequency_R)/(2*self.g_factors['e'])

    def on_deactivate(self):
        pass

    def load_current_spin(self):
        #File = TT_LOG_DIR+"\current_n_spins.csv"
        #spins= np.loadtxt(File,dtype=str).tolist()
        if len(self._current_spins)>0:
            for spin in self._current_spins.split(','):
                spin=str(spin)
                if "si" in spin.lower():
                    self.si29_list.append(spin.lower())
                else:
                    self.c13_list.append(spin.lower())
                self.strong_spins_list.append(spin.replace("si","Si").replace("c","C"))


    def create_spins(self,spin_names,P_Couplings,O_Couplings):
        spins=[]
        for spin_name in spin_names:
            if "_" in spin_name:
                print("warning: underscores are dangerous in spin names, prefer '.' or something similar,\n did not create any spin files.")
                return
            spins.append(spin_name.replace("si","Si").replace("c","C").replace("MHz",""))

        folder=r"log\transition_tracker_log"
        File=folder+r"\current_n_spins.csv"
        np.savetxt(File,spins,fmt="%s")
        for i,spin_name in enumerate(spins):
            hf_p_file=folder+r"\hf_"+spin_name+".dat"
            hf_o_file=folder+r"\hf_perp_"+spin_name+".dat"

            t=nowstr()
            txt_o=t+"\t"+str(O_Couplings[i])
            txt_p=t+"\t"+str(P_Couplings[i])

            np.savetxt(hf_o_file,[txt_o],fmt="%s")
            np.savetxt(hf_p_file,[txt_p],fmt="%s")

            #create the nuclear rabi files, they are just copies of one example, in order to not get an error on startup of qudi, so no real data
            for i in np.arange(-1.5,2.5,1):
                original=f"13c5 ms{i}_rabi.dat"
                copy=f"{spin_name} ms{i}_rabi.dat"
                if "ms-" not in original:
                    original=original.replace("ms","ms+")
                    copy=copy.replace("ms","ms+")

                shutil.copy(os.path.join(folder,original),os.path.join(folder,copy))
        
        script_folder=r"C:/src/squdi/src/qudi/notebooks/UserScripts"
        shutil.copytree(os.path.join(script_folder,"29Si5"),os.path.join(script_folder,f"{str(spin_names).replace('.',',')}"[2:-2]))
        print("you need to restart qudi for the transition tracker to update")


    def update_register_tau(self,Spin=None,subspace="-3/2",dd_method="knillpi",sol_number=1,sol="raw"): #experimental
        "sol= raw or disc"
        ddt_N={"knillpi":5}
        tmp=self.register.save_imediatly

        self.register.save_imediatly=False

        if Spin==None:
            for Spin in self.register.df.spin_name.unique():
                try:
                    mask = (
                        (self.register.df['spin_name'] == str(Spin)) &
                        (self.register.df['subspace'] == str(subspace)) &
                        (self.register.df['dd_method'] == str(dd_method)) &
                        (self.register.df['comment'] == "reserved_for_tau_finder")
                    )

                    df=self.register.get_spin(Spin, subspace.replace('+',''), dd_method.lower())
                    n_rep_ddrf = int(df.n_rep_ddrf.iloc[0]) #this assumes only one reserved entry per spin
                    bath=[self.c_bath,self.si_bath]["Si" in Spin]

                    sol_disc,sol_raw=self.register.tau_optimizer.get_best_tau(Spin,N=ddt_N[dd_method]*n_rep_ddrf, wL=bath, Azz=df.Azz.iloc[0],drive_freq= df.trans.iloc[0], solution_number=[sol_number])

                    tau= sol_disc[sol_number][f"tau_{sol}"] #or tau_disc

                    self.register.update_filtered(mask,"ddrf_tau",tau)
                    df = self.register.get_spin(Spin, subspace.replace('+',''), dd_method.lower())
                    if np.sum(mask):
                            print(f"\n========== SOLUTION #{sol_number} ==========")

                            for k, v in sol_disc.items():
                                print(f"  {k:25s}: {v}")

                except Exception as e:
                    print(f"error at spin {Spin}:", e)
        else:
                mask = (
                    (self.register.df['spin_name'] == str(Spin)) &
                    (self.register.df['subspace'] == str(subspace)) &
                    (self.register.df['dd_method'] == str(dd_method)) &
                    (self.register.df['comment'] == "reserved_for_tau_finder") 
                )

                df=self.register.get_spin(Spin, subspace.replace('+',''), dd_method.lower())

                n_rep_ddrf = int(df.n_rep_ddrf.iloc[0])
                bath=[self.c_bath,self.si_bath]["Si" in Spin]

                sol_disc,sol_raw=self.register.tau_optimizer.get_best_tau(Spin,N=ddt_N[dd_method]*n_rep_ddrf, wL=bath, Azz=df.Azz.iloc[0],drive_freq= df.trans.iloc[0], solution_number=[sol_number])

                tau= sol_disc[0][f"tau_{sol}"] #or tau_disc

                self.register.update_filtered(mask,"ddrf_tau",tau)
                print("new_tau=",tau)

        self.register.save_imediatly=tmp
        print("call from update_tau")
        self.register.save_to_hdf()

    def do_nothing(self,*args,**kwargs):
        print("done nothing\n", "args are:\n",args)
        pass

    def update_ple(self,freqs=""):
        print("Updating PLE freq in TT...")
        # FIXME: PLE data should return a list, not a string. Alternatively a wavemeterlogger could be used
        if len(freqs.split(';')) == 3: # when PLE data has two peaks
            self.ple_A2 = float(freqs.split(';')[1])
            self.ple_A1 = float(freqs.split(';')[0])
        elif len(freqs.split(';')) < 3: # If only one peak is fitted to PLE data
            #self.ple_A1 = float(freqs.split(';')[0])
            self.ple_A2 = float(freqs.split(';')[0])
        else:
            print("Too many PLE peaks, dont know how to assign it in Transition Tracker.")

    # def fit_nuc_transitions(self,trans_list,correct_nuc_trans, use_electron_trans=True):
    #     def transitions(All=None,Aperp=None,trans_list=[]):
    #         """Works only if you use the subspace transitions of one spin"""
            
    #         l=[]
    #         Spins=[]
    #         for trans in trans_list:
    #             spin=trans.split(" ")[0]
    #             if spin in Spins:
    #                 continue
    #             else:
    #                 Spins.append(spin)
    #             if All!= None and Aperp!= None:
    #                 self.hf_para_n[spin]=All
    #                 self.hf_perp_n[spin]=Aperp
                
    #         self.update_stuff()
    #         for trans in trans_list: 
    #             l.append(self.t(trans).current_frequency)

    #         if use_electron_trans:    
    #             transit={i:[-0.5, .5] for i in [*self.si29_list,*self.c13_list]}

    #             L_trans=list(self.mfl(transit, ms_trans='L')) 
    #             R_trans=list(self.mfl(transit, ms_trans='R'))
            
    #             l.extend(L_trans)
    #             l.extend(R_trans)
    #         #print(l)
            
    #         return l
        
    #     def to_minimize(params,trans_list):
    #         Aperp=params["Aperp"]
    #         All=params["All"]
    #         t=transitions(All,Aperp,trans_list)
            
    #         return np.array(t)-np.array(Transitions)
            

    #     #trans_list=['29si8 ms+1.5','29si8 ms-1.5','29si8 ms+0.5','29si8 ms-0.5']
    #     electron_trans=transitions()
    #     #correct_nuc_trans=[
    #     #-14.155565538125302+0.252,
    #     #11.824924117495357-0.238,
    #     #-5.474830544320412+0.079,
    #     #3.185657792474558-0.081]
    #     if use_electron_trans:  
    #         Transitions=correct_nuc_trans+electron_trans
    #     else:
    #         Transitions=correct_nuc_trans

        

    #     spin=trans_list[0].split(" ")[0]
    #     params = lmfit.Parameters()
    #     params.add("All", value=self.hf_para_n[spin], min=-90, max=90)
    #     params.add("Aperp", value=self.hf_perp_n[spin], min=-90, max=90)

    #     res=lmfit.minimize(to_minimize,params=params,kws={"trans_list":trans_list})
    #     #print(res.params)

    #     folder=r"log\transition_tracker_log"

    #     hf_p_file=folder+r"\hf_"+spin+".dat"
    #     hf_o_file=folder+r"\hf_perp_"+spin+".dat"

    #     P_Couplings,O_Couplings=[res.params[i].value for i in res.params]

    #     t=nowstr()#str(datetime.datetime.now())
    #     #print(P_Couplings,O_Couplings)

    #     txt_p=np.loadtxt(hf_p_file,dtype=str,delimiter=",")
    #     txt_o=np.loadtxt(hf_o_file,dtype=str,delimiter=",")

    #     txt_o=np.append(txt_o,t+"\t"+str(O_Couplings))
    #     txt_p=np.append(txt_p,t+"\t"+str(P_Couplings))

    #     np.savetxt(hf_o_file,[txt_o],fmt="%s",delimiter="\n")
    #     np.savetxt(hf_p_file,[txt_p],fmt="%s",delimiter="\n")

    #     #print("before")
    #     #print(Transitions)
    #     #print("after")
    #     #print(trans_list)
    #     #print(transitions(None,None,trans_list=trans_list))

    def connect_signals(self):
        #self._rabi_logic.sigFitPerformed.connect(self.update_rabi)
        if self._ple_logic: 
            self._ple_logic.sigFitPerformed.connect(self.update_ple)
        else:
            print("No PLE logic connected to TransitionTracker.")
        #self._powerstabilization_logic.SigPowerCalibrationFinished.connect(self.update_power_calibration)

        #self.update_tt_nuclear_gui.connect(self.update_gui_nuclear)
        #self.update_tt_electron_gui.connect(self.update_gui_electron)

    def nuclear_transition_name(self, transition):
        """
        this transitions is for the nuclear spin.
        """

        ms = self.transition_name_list[0][transition[0][0]]
        fsn = flipped_spin_numbers(transition)[0]
        nuc = self.spin_name_list[fsn] #nuc = 29si8 ms = +1.5
        if ms == '0' and '13c' in nuc: # no there is never happens here. basically all are at larmor.
            return '13c ms0'
        else:
            if fsn == 1 and '14n' in nuc: #if it is nuclear spin flipped. (nitrogen, I assume?)
                if transition[0][1] == 0: #initial transition is '+1'
                    mn = '+1'
                elif transition[1][1] == 2: #initial transition is '0'
                    mn = '-1'
                nuc += mn

            #here is not used??
            return "{} ms{}".format(nuc, ms)

    def set_ntd(self):
        ntd = {}
        c13ms0_added = False
        for t in single_quantum_transitions_non_hf_spins(self.states_list, hf_spin_list=[0]):
            name = self.nuclear_transition_name(t)
            if name == '13c ms0':
                if c13ms0_added:
                    continue
                else:
                    c13ms0_added = True
            ntd[name] = t
        self.ntd = ntd

    def reload_nuclear_parameters(self):
        
        # 14N is just an example. 
        self.g_factors['14n'] = get_last_values_from_file(filename='gamma_14n.dat', full_path=os.path.join(self.log_folder,'gamma_14n.dat'))[0]#r"{}\gamma_14n.dat".format(self.log_folder))[0]
        self.qp = {'14n': get_last_values_from_file(filename='qp_14n.dat', full_path=os.path.join(self.log_folder,'qp_14n.dat'))[0]}#r"{}\qp_14n.dat".format(self.log_folder))[0]}
        self.hf_para_n = {'14n': get_last_values_from_file(filename='hf_14n.dat',
                                                           full_path=os.path.join(self.log_folder,'hf_14n.dat'))[0]
                          }#r"{}\hf_14n.dat".format(self.log_folder))[0]}
        self.hf_perp_n = {'14n': get_last_values_from_file(filename='hf_perp_14n.dat', full_path=os.path.join(self.log_folder,'hf_perp_14n.dat'))[0]}#r"{}\hf_perp_14n.dat".format(self.log_folder))[0]}
        for key in self.c13_list:
            print(key)
        for key in self.si29_list:
            print(key)
        self.hf_para_n.update(dict([(key, 
                                     get_last_values_from_file(filename='hf_{}.dat'.format(key),
                                                               full_path=os.path.join(
                                                                   self.log_folder,'hf_{}.dat'.format(key)))[0]
                                                                   ) for key in self.c13_list+self.si29_list]))
        self.hf_perp_n.update(dict([(key, 
                                     get_last_values_from_file(filename='hf_perp_{}.dat'.format(key),
                                                               full_path=os.path.join(
                                                                   self.log_folder,'hf_perp_{}.dat'.format(key)))[0]
                                                                   ) for key in self.c13_list+self.si29_list]))

    def set_h_diag(self):
        self.nvham = NVHam(magnet_field={'z': self.current_magnetic_field},
                           n_type=None, nitrogen_levels=[],
                           electron_levels=[0,1,2,3],
                        #    electron_levels=range(len(self.e_transitions)),
                           gamma=self.g_factors,
                           qp=self.qp, hf_para_n=self.hf_para_n,
                           hf_perp_n=self.hf_perp_n)
        for c13 in self.c13_list:
            self.nvham.add_spin(np.matrix(np.diag([self.hf_perp_n[c13], self.hf_perp_n[c13], self.hf_para_n[c13]])), 
                                self.nvham.h_13c(), [0, 1])

        for si29 in self.si29_list:
            self.nvham.add_spin(
                hft=np.matrix(np.diag([self.hf_perp_n[si29], self.hf_perp_n[si29], self.hf_para_n[si29]])),
                h_ns=self.nvham.h_29si(),
                nslvl_l=[0, 1])

        eval_evec = self.nvham.h_nv.eigenstates()
        # *np.linalg.eig(self.nvham.h_nv.data.todense())[::-1]
        self.h_diag = sort_eigenvalues_standard_basis(self.nvham.dims, eval_evec[1], eval_evec[0])

    def load_transitions(self):
        self.transitions = [] # nuclear transitions
        for key, val in self.ntd.items():
            self.transitions.append(
                Transition(
                    parent=self,
                    name=key,
                    current_frequency=-get_transition_frequency(h_diag=self.h_diag, dims=self.nvham.dims, transition=val) # fixme get it right
                )
            )

    def update_current_frequencies(self):
        for key, val in self.ntd.items():
            self.transition(key).current_frequency = -get_transition_frequency(h_diag=self.h_diag, dims=self.nvham.dims, 
                                                                               transition=val)
        
        self.register.calculate_transitions_from_detuning((self.mw_mixing_frequency_L+self.mw_mixing_frequency_R)/(2*self.g_factors['e']))
        self.update_tt_nuclear_gui.emit()

    def load_rabi_parameters(self):
        self.rabi_parameters = dict()
        for f in os.listdir(self.log_folder):
            if 'e_rabi_ou{:.0f}deg'.format(1000*self._awg.mcas_dict.awgs['2g'].ch[1].output_amplitude) in f:
                if len(f.split('.')) > 2:
                    raise Exception('Error: floating point values or any other reason to have points in the filename other than for the file extension may not a good idea. {}'.format(f))
                self.rabi_parameters[f.split('.')[0]] = RabiParametersStatic(filepath=os.path.join(self.log_folder, f), transition_name='e_rabi')
        for t in self.transitions:
            if any([n in t.name for n in ['13c13', '13c6', '13c-5', '13c-6']]) and not 'ms0' in t.name:
                t_name = "13c ms0"
            else:
                t_name = t.name
            self.rabi_parameters[t.name] = RabiParametersStatic(filepath=os.path.join(self.log_folder, "{}_rabi.dat".format(t_name)), transition_name=t.name)

    def plot_rabi_parameters(self):
        idx = 0
        c13ms0_shown=False
        for tn, rp in self.rabi_parameters.items():
            try:
                if 'ms+1' in tn:
                    continue

                if rp.filename == '13c ms0_rabi':
                    if c13ms0_shown:
                        continue
                    else:
                        c13ms0_shown = True
                idx += 1
            except:
                pass
        fig, axes = plt.subplots(idx, 2, figsize=(10, 6*(idx)))
        idx=0
        c13ms0_shown=False
        for tn, rp in self.rabi_parameters.items():
            try:
                if 'ms+1' in tn:
                    continue

                if rp.filename == '13c ms0_rabi':
                    if c13ms0_shown:
                        continue
                    else:
                        c13ms0_shown = True
                # rp.plot()
                rp.plot(ax0=axes[idx, 0], ax1=axes[idx, 1])
                idx += 1
            except:
                print('could not plot {}'.format(tn))

    @property
    def log_folder(self):
        return TT_LOG_DIR


    @property
    def current_local_oscillator_freq(self):
        return self._current_local_oscillator_freq

    @current_local_oscillator_freq.setter
    def current_local_oscillator_freq(self, val):
        self._current_local_oscillator_freq = misc.check_type(val, 'current_local_oscillator_freq', Number)
        self.update_stuff()

    @property
    def mw_mixing_frequency_L(self):
        return self._mw_mixing_frequency_L

    @mw_mixing_frequency_L.setter
    def mw_mixing_frequency_L(self, val):
        #print("TT:")
        #print(val)
        self._mw_mixing_frequency_L = misc.check_type(val, '_mw_mixing_frequency_L', Number)
        if getattr(self, '_mw_mixing_frequency_L', 0.0) != 0.0:
            save_value_to_file(self.mw_mixing_frequency_L, 'mw_mixing_frequency_L')
        self.update_stuff()

    @property
    def zero_field_splitting(self):
        return self._zero_field_splitting

    @zero_field_splitting.setter
    def zero_field_splitting(self, val):
        self._zero_field_splitting = misc.check_type(val, 'zero_field_splitting', Number)
        self.update_stuff()

    @property
    def mw_transition_frequency(self):
        return self.mw_mixing_frequency_L# + self.current_local_oscillator_freq


    @property
    def mw_mixing_frequency_R(self):
        return self._mw_mixing_frequency_R

    @property
    def mw_mixing_frequency_C(self):
        return self._mw_mixing_frequency_C

    @mw_mixing_frequency_C.setter
    def mw_mixing_frequency_C(self, val):
        #print("TT:")
        #print(val)
        self._mw_mixing_frequency_C = misc.check_type(val, '_mw_mixing_frequency_C', Number)
        if getattr(self, '_mw_mixing_frequency_L', 0.0) != 0.0:
            save_value_to_file(self.mw_mixing_frequency_C, 'mw_mixing_frequency_C')
        self.update_stuff()

    @mw_mixing_frequency_R.setter
    def mw_mixing_frequency_R(self, val):
        self._mw_mixing_frequency_R = misc.check_type(val, '_mw_mixing_frequency_R', Number)
        if getattr(self, '_mw_mixing_frequency_R', 0.0) != 0.0:
            save_value_to_file(self.mw_mixing_frequency_R, 'mw_mixing_frequency_R')
        self.update_stuff()
        angle = np.arctan(
            np.rad2deg(self.current_magnetic_field_vector[1]/self.current_magnetic_field_vector[0]))

    @property
    def mw_transition_frequency_p1(self):
        return self.current_local_oscillator_freq_p1 + self.mw_mixing_frequency_R #TODO local oscillator_p1 to local oscillator_R

    @property
    def current_local_oscillator_freq_p1(self):
        return self.current_local_oscillator_freq# + self.mw_mixing_frequency




    # @property
    # def mw_mixing_frequency_p1(self):
    #     return 2*self.zero_field_splitting - self.mw_mixing_frequency

    # @property
    # def mw_transition_frequency_p1(self):
    #     return self.current_local_oscillator_freq + self.mw_mixing_frequency_p1
    #
    # @property
    # def current_local_oscillator_freq_p1(self):
    #     return self.mw_transition_frequency_p1 + self.mw_mixing_frequency

    def update_stuff(self,PLE_only=False):
        print("updating stuff")
        for attr_name in ['_current_local_oscillator_freq', '_mw_mixing_frequency_L',
                          '_zero_field_splitting','mw_mixing_frequency_R','_ple_A2','_ple_A1','_ple_repump',
                          'ple_A2_fit_params','ple_A1_fit_params','interferometer_fit_params','interferometer_history']: #needs "ple_Ex", but where is this "ple_Ex" called?
            if not hasattr(self, attr_name):
                return
            
        self.update_tt_electron_gui.emit() #connect to the gui
        if PLE_only:
            return
        self.set_h_diag()
        if not hasattr(self, 'ntd'):
            return
        self.update_current_frequencies()
        self.si_bath = self.g_factors['29si'] * (self.mw_mixing_frequency_L+self.mw_mixing_frequency_R)/(2*self.g_factors['e'])
        self.c_bath = self.g_factors['13c'] * (self.mw_mixing_frequency_L+self.mw_mixing_frequency_R)/(2*self.g_factors['e'])

    # @property
    # def xyz(self):
    #     return self._xyz
    #
    # @xyz.setter
    # def xyz(self, vector):
    #     self._xyz = vector
    #     pi3d.save_values_to_file(self._xyz, 'xyz')

    @property
    def ple_repump(self):
        return self._ple_repump

    @ple_repump.setter
    def ple_repump(self, val):
        self._ple_repump = misc.check_type(val, 'ple_repump', Number)
        if getattr(self, '_ple_repump', 0.0) != 0.0:
            save_value_to_file(self.ple_repump, 'ple_repump')
        self.update_stuff(PLE_only=True)

    @property
    def ple_A2(self):
        return self._ple_A2

    @ple_A2.setter
    def ple_A2(self, val):
        self._ple_A2 = misc.check_type(val, 'ple_A2', (list,Number, np.ndarray))
        # if getattr(self, '_ple_A2', 0.0) != 0.0:
        if getattr(self, '_ple_A2', 0.0) is not None:

            save_value_to_file(self.ple_A2, 'ple_A2')
        self.update_stuff(PLE_only=True)

    @property
    def ple_A2_fit_params(self):
        return self._ple_A2_fit_params

    @ple_A2_fit_params.setter
    def ple_A2_fit_params(self, val):
        self._ple_A2_fit_params = misc.check_type(val, 'ple_A2_fit_params', (list, np.ndarray))
        if getattr(self, '_ple_A2_fit_params', 0.0) is not None:

            save_value_to_file(self.ple_A2_fit_params, 'ple_A2_fit_params')
        self.update_stuff(PLE_only=True)

    @property
    def ple_A1_fit_params(self):
        return self._ple_A1_fit_params

    @ple_A1_fit_params.setter
    def ple_A1_fit_params(self, val):
        self._ple_A1_fit_params = misc.check_type(val, 'ple_A1_fit_params', (list, np.ndarray))
        if getattr(self, '_ple_A1_fit_params', 0.0) is not None:

            save_value_to_file(self.ple_A1_fit_params, 'ple_A1_fit_params')
        self.update_stuff(PLE_only=True)

    @property
    def ple_A1(self):
        return self._ple_A1

    @ple_A1.setter
    def ple_A1(self, val):
        self._ple_A1 = misc.check_type(val, 'ple_A1', (list,Number, np.ndarray))
        # if getattr(self, '_ple_A1', 0.0) != 0.0:
        if getattr(self, '_ple_A1', 0.0) is not None:

                save_value_to_file(self.ple_A1, 'ple_A1')
        self.update_stuff(PLE_only=True)

    @property
    def interferometer_fit_params(self):
        return self._interferometer_fit_params

    @interferometer_fit_params.setter
    def interferometer_fit_params(self, val):
        self._interferometer_fit_params = misc.check_type(val, 'interferometer_fit_params', (list, np.ndarray))
        if getattr(self, '_interferometer_fit_params', 0.0) is not None:

            save_value_to_file(self.interferometer_fit_params, 'interferometer_fit_params')
        self.update_stuff()

    @property
    def interferometer_history(self):
        return self._interferometer_history


    @interferometer_history.setter
    def interferometer_history(self, val):
        self._interferometer_history = misc.check_type(val, 'interferometer_history', (list, np.ndarray,tuple))
        if getattr(self, '_interferometer_history', 0.0) is not None:

            save_value_to_file(self.interferometer_history, 'interferometer_history')
        self.update_stuff()

    @staticmethod
    def correct_transition_name(name):
        name = name.replace('13C', '13c').replace('14N', '14n').replace('mS', 'ms').replace('29Si','29si')
        if '13c' in name and 'ms0' in name:
            name = '13c ms0'
        if 'e_rabi' in name:
            name = name.replace('+1', 'right').replace('-1', 'left')
        return name

    def transition(self, name):
        name=self.correct_transition_name(name) 
        for transition in self.transitions:
            if str(transition.name) in name:
                return transition
        else:
            return None

    t = transition

    def change_transition_frequency(self, fd, current_magnetic_field=None, test_mode=False):
        """
        all transition frequencies are defined from lower to higher angular momentum, i.e. 14N+1 mS0 is transition from 14N0 to 14N+1 in ms0
        gamma = -zeeman/B
        """
        current_magnetic_field = self.current_magnetic_field if current_magnetic_field is None else current_magnetic_field
        fdc = dict([(self.correct_transition_name(name), val) for name, val in fd.items()])

        fd14n = dict([(name, val) for name, val in fdc.items() if '14n' in name])
        cfd = dict([(name, self.t(name).current_frequency) for name, val in fdc.items()])
        if len(fd14n) > 0:
            if not '14n+1 ms0' in fd14n and '14n-1 ms0' in fd14n:
                raise Exception('Error: {}'.format(fd14n))
            mod = qudi.logic.qudip_enhanced.lmfit_models.NVHam14NModel(fd14n, diag=True)
            params = mod.make_params()
            params['magnet_field'].value = self.current_magnetic_field
            params['magnet_field'].vary = False
            params['gamma_e'].value = self.g_factors['e']
            params['gamma_e'].vary = False
            params['gamma_n'].value = self.g_factors['14n']
            params['gamma_n'].min = 3.07
            params['gamma_n'].max = 3.08
            params['qp'].value = self.qp['14n']
            params['qp'].min = - 5.
            params['qp'].max = - 4.9
            params['hf_para_n'].value = self.hf_para_n['14n']
            # params['hf_para_n'].min = -2.17
            # params['hf_para_n'].max = -2.16
            params['hf_perp_n'].value = self.hf_perp_n['14n']
            # params['hf_perp_n'].min = -2.8
            # params['hf_perp_n'].max = -2.6
            # params['hf_perp_n'].vary = False
            if len(fd14n) <= 2:
                params['hf_para_n'].vary = False
            if len(fd14n) <=3:
                params['hf_perp_n'].vary = False
            # result = mod.fit(data=fd14n.values(), x=range(len(fd14n.keys())), params=params, method='lbfgsb', fit_kws=dict(options=dict(ftol=1e-17, gtol=1e-17, maxls=100, disp=True, maxiter=100, maxfun=10000)))
            result = mod.fit(data=fd14n.values(), x=range(len(fd14n.keys())), params=params, method='powell', fit_kws=dict(options=dict(ftol=1e-17, xtol=1e-17, disp=True)))
            # result = mod.fit(data=fd14n.values(), x=range(len(fd14n.keys())), params=params, method='powell', fit_kws=dict(options=dict(ftol=1e-17, xtol=1e-17, disp=True)))
            # result = mod.fit(data=fd14n.values(), x=range(len(fd14n.keys())), params=params, method='leastsqr', fit_kws=dict(ftol=1e-15, gtol=1e-15, maxfev=10000)) #https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.leastsq.html#scipy.optimize.leastsq
            cd = dict(transition_list=fd14n.keys(), nuc='14n', test_mode=test_mode)
            self.update_nuclear_parameter(val=result.params['gamma_n'].value,
                                          old_val=self.g_factors['14n'],
                                          filename='gamma_14n.dat',
                                          typ='gyromagnetic ratio',
                                          **cd)
            self.update_nuclear_parameter(val=result.params['qp'].value,
                                          old_val=self.qp['14n'],
                                          filename='qp_14n.dat',
                                          typ='quadrupole splitting',
                                          **cd)
            if len(fd14n) > 2:
                self.update_nuclear_parameter(val=result.params['hf_para_n'].value,
                                              old_val=self.hf_para_n['14n'],
                                              filename='hf_14n.dat',
                                              typ='hyperfine',
                                              **cd)
            if len(fd14n) > 3:
                self.update_nuclear_parameter(val=result.params['hf_perp_n'].value,
                                              old_val=self.hf_perp_n['14n'],
                                              filename='hf_perp_14n.dat',
                                              typ='perpendicular hyperfine',
                                              **cd)

        for name, new_freq in fdc.items():
            if '13c' in name and 'ms0' in name:
                nuc = name[:-4]
                self.update_nuclear_parameter(val=-new_freq / self.current_magnetic_field,
                                              old_val=self.g_factors['13c'],
                                              filename='gamma_13c.dat',
                                              typ='gyromagnetic ratio',
                                              nuc=nuc,
                                              transition_list=[name],
                                              test_mode=test_mode)
        for name, new_freq in fdc.items():
            if '13c' in name and not 'ms0' in name:
                ms = int(name[-2:])
                nuc = name[:-5]
                self.update_nuclear_parameter(val=ms * (self.g_factors['13c'] * current_magnetic_field + new_freq),
                                              old_val=self.hf_para_n[nuc],
                                              filename='hf_{}.dat'.format(nuc),
                                              typ='hyperfine',
                                              nuc=nuc,
                                              transition_list=[name],
                                              test_mode=test_mode)
        if test_mode and len(fd14n) >=2 :
            print("test_mode in TT:", result.eval(x=range(len(fd14n)), params=result.params))
        for t, target_frequency in fdc.items():
            previous_frequency = cfd[t]
            current_frequency = self.t(t).current_frequency
            logging.getLogger().info(
                'Frequency of {} changed from {} to {} (deviation from target_frequency: {}Hz).'.format(t, previous_frequency, current_frequency, (current_frequency-target_frequency)*1e6)
            )

    def update_nuclear_parameter(self, typ, val, old_val, transition_list, nuc, filename, test_mode=False):
        
        log_text = 'The {} of {} was changed from {} to {} from measurement of [{}].'.format(typ, nuc, old_val, val, ",".join(transition_list))
        if test_mode:
            #todo change loogger
            logging.getLogger().info('Test_mode!!!:            {}'.format(log_text))
        else:
            save_values_to_file(val=[val], full_path="{}/{}".format(self.log_folder, filename), filename=None)
            logging.getLogger().info(log_text)
            self.reload_nuclear_parameters()
            self.set_h_diag()
            self.update_current_frequencies()

    @staticmethod
    def frequency_fid(assumed_frequency, frequency_offset, measured_period, max_diff_factor=.2):
        delta_abs_f = np.abs(frequency_offset) - np.abs(1 / float(measured_period))
        max_delta_abs_f = max_diff_factor*np.abs(frequency_offset)
        if max_diff_factor is not None and delta_abs_f > max_delta_abs_f:
            raise Exception('The measured period indicates a frequency change of {} MHz (allowed:  {}) MHz.'.format(delta_abs_f, max_delta_abs_f))
        return assumed_frequency + frequency_offset - np.sign(frequency_offset)/measured_period

    # def change_transition_frequency_fid(self, name, frequency_offset, period):
    #     """
    #     updates the frequency of self.transition(name)
    #     :param name: str
    #         nuclear transition name
    #     :param frequency_offset: float
    #         frequency offset used for fid, usually 0.002 [MHz]
    #     :param period:
    #         fid period that was actually measured (for perfect frequency match its 1/frequency_offset
    #     :return:
    #     """
    #     new_freq = self.t(name).current_frequency + frequency_offset - 1 / period
    #     max_dif = 0.002
    #     if abs(new_freq - self.t(name).current_frequency) < max_dif:
    #         self.change_transition_frequency(name, new_freq)
    #     else:
    #         print("Not Possible. Frequency difference is larger than {} MHz.".format(max_dif))

    def update_zero_field_splitting(self, freq):
        """
        updates the zero_field_splitting considering current_local_oscillator_freq, mw_mixing_frequency
        :param freq: float
            local oscillator frequency ms 0 -> +1 for mixing frequency mw_mixing_frequency
        """
        self.zero_field_splitting = (self.mw_mixing_frequency_R-self.mw_mixing_frequency_L)/2
        #self.zero_field_splitting = (freq - self.current_local_oscillator_freq) / 2.0 + self.mw_mixing_frequency_L

    def get_rabi_parameter(self, name, **kwargs):
        name = self.correct_transition_name(name)
        # Javid added this to make sure we don't use wrong transition with old scripts
        # Or another bad case - one used old calibration sript, so that everything ws saved in wrong file
        if name =='e_rabi_ou350deg-90':
            warnings.warn('Specify if you want right or left transition \n-R or -L should be in file name'
                          '\nBy default left transition will be used')
        if '_left' in name:
            tni = [0]
            name = name.replace('_left', 'L')
        elif '_right' in name:
            tni = [1]
            name = name.replace('_right', 'R')
        else:
            tni = None
        if 'e_rabi' in name and not '_ou' in name:
            name = "{}_ou{:.0f}deg{}".format(name, 1000*self._awg.mcas_dict.awgs['2g'].ch[1].output_amplitude, #TODO connect to it
                                             kwargs['mixer_deg'])
            del kwargs['mixer_deg']
        return RabiParametersSingle(rp=self.rabi_parameters[name], tni=tni, **kwargs)

    def rp(self, name, **kwargs):
        if len(kwargs) == 0:
            return self.rabi_parameters[name]
        elif (len(kwargs) == 1 and 'mixer_deg' in kwargs):
            return self.rabi_parameters['e_rabi_ou{:.0f}deg{}'.format(
                1000*self._awg.mcas_dict.awgs['2g'].ch[1].output_amplitude,
                kwargs['mixer_deg'])]
        else:
            return self.get_rabi_parameter(name, **kwargs)
        
    def RP(self,name,**kwargs):
        rp=self.rp(name,**kwargs)
        wrapped=RPWrapper(rp)
        return wrapped

    @property
    def current_magnetic_field(self): #z field
        return self.current_magnetic_field_vector[0]

    @property
    def current_magnetic_field_vector(self):  # z and x field
        sx, sy, sz = jmat(self._spin_number)
        f1 = self.mw_mixing_frequency_L #MHz
        f2 = self.mw_mixing_frequency_C
        f3 = self.mw_mixing_frequency_R
        def H(B_z, B_x):
            print("TT: Hardcoded ZFS")
            D = 34.9 #MHz 
            gamma_e = self.g_factors['e']
            return D * sz ** 2 + gamma_e * B_z * sz + gamma_e * B_x * sx

        def odmr(B_z, B_x):
            energies = H(B_z, B_x).eigenenergies()
            return np.array([energies[1] - energies[0], 
                             energies[2]-energies[1],
                             energies[3]-energies[2]])

        def func(params):
            bz = params[0]
            bx = params[1]
            return (odmr(bz, bx)[0] - f1) ** 2 + (odmr(bz, bx)[1] - f2) ** 2 + (odmr(bz, bx)[2] - f3) ** 2 

        return minimize(fun =func,x0 = np.array([0.2,0.])).x

    def get_f(self, typ):
        if '_qp' in typ:
            return self.qp[typ.split('_')[0].lower()]
        elif '_hf' in typ:
            return self.hf_para_n[typ.split('_')[0].lower()]

    def mfl(self, td, mw_mixing_frequency_L=None, ms_trans='L'):
        #TODO: update ms from NV to V2
        """

        :param td: dict
            e.g. {'14N':[1], '13C90': '0.5'}
        :param mw_mixing_frequency: float
        :return: list
            e.g. [17.6750, 19.8350]

        """
        if mw_mixing_frequency_L is None: mwfm = self.mw_mixing_frequency_L

        if type(td) is str:
            td = td.replace('14n', '14N').replace('13c', '13C').replace('29si','29Si')
            if td == '14N_all':
                td = {'14N': [-1, 0, 1]}
            elif td == '14N+1':
                td = {'14N': [1]}
            elif td == '14N-1':
                td = {'14N': [-1]}
            elif td == '14N0':
                td = {'14N': [0]}
            elif td == '13C414_all':
                td = {'14N': [-1, 0, 1], '13C414': [-0.5, 0.5]}
            elif td == '13C414':
                td = {'14N': [-1, 0, 1], '13C414': [-0.5]}
            elif td == '13C414_left':
                td = {'14N': [-1, 0, 1], '13C414': [-0.5]}
            elif td == '13C414_right':
                td = {'14N': [-1, 0, 1], '13C414': [0.5]}
            elif td == '13C90_all':
                td = {'14N': [-1, 0, 1], '13C414': [-0.5, 0.5], '13C90': [-0.5, 0.5]}
            elif td == '13C90':
                td = {'14N': [-1, 0, 1], '13C414': [-0.5, 0.5], '13C90': [-0.5]}
            elif td == '13C90_left':
                td = {'14N': [-1, 0, 1], '13C414': [-0.5, 0.5], '13C90': [-0.5]}
            elif td == '13C90_right':
                td = {'14N': [-1, 0, 1], '13C414': [-0.5, 0.5], '13C90': [0.5]}
            else:
                raise Exception("{} is not and allowed value for td".format(td))
        # fix for now. if two original keys normalize to the same key,
        # the dictionary comprehension will overwrite one value.
        else:
            td = {
                key.replace('14n', '14N')
                .replace('13c', '13C')
                .replace('29si', '29Si'): val
                for key, val in td.items()
            }
        # else:
        #     for key, val in td.items():
        #         del td[key]
        #         td[key.replace('14n', '14N')
        #            .replace('13c', '13C')
        #            .replace('29si','29Si')] = val
        f = list()
        for key in td.keys():
            if key not in self.strong_spins_list:
                raise Exception("Key '{}' is not a valid nuclear spin".format(key))
        for i in [ll.replace("si","Si").replace("c","C") for ll in [*self.c13_list,*self.si29_list]]:#why not put here all spin list?
        #for i in [*self.c13_list,*self.si29_list]:#why not put here all spin list?
            a = np.array(td.get(i, [])) * self.get_f("{}_hf".format(i.lower()))
            if np.size(a) > 0:
                f.append(a)
        ff = list(product(*f))
        mfl = np.array(sorted([mwfm + sum(fff) for fff in ff if not np.size(fff) == 0]))

        #here do some ms?
        if ms_trans in ['R']:
            return mfl - self.mw_mixing_frequency_L + self.mw_mixing_frequency_R

        elif ms_trans in ['C']:
            return mfl + -self._mw_mixing_frequency_L+self._mw_mixing_frequency_C
        else:
            return mfl