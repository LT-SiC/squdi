# -*- coding: utf-8 -*-
from __future__ import print_function, absolute_import, division

#from pi3diamond import pi3d
import numpy as np
import itertools
import fractions
import copy
# import Analysis
import qudi.logic.NuclearOPs
import os
# import cPickle
import collections
from qudi.logic.qudip_enhanced import data_handling
import datetime
from importlib import reload as reload
from scipy import special

# def full_wavelength(flf, target_length_mus):
#     """
#     WORKS FOR ONE OR TWO FREQUENCIES RIGHT NOW
#
#     returns a length_mus, for which all frequencies f_i in frequency list make a full wavelength.
#
#     :param flf: list of frequencies given as fractions.Fraction(f)
#     :param target_length_mus: float
#     This method tries to output the length_mus which is closest to target_length_mus
#     :return: float
#     length_mus
#     """
#     dn_list = [flf.denominator for f in flf]
#     n_list =  [flf.nominator for f in flf]
#     pd = np.prod(dn_list)
#     n_list =
#     cd = np.prod(dn_list)
#     n_f_cd_list = [int(f.numerator/float(f.denominator)*cd) for f in flf]
#     return  fractions.Fraction(np.prod(n_f_cd_list), cd)

    # if len(frequency_list) == 1:
    #     f = round(frequency_list[0], num_digits)
    #     return round(target_length_mus*f)/f
    # n = max([len(str(round(f, num_digits)).split('.')) for f in frequency_list])
    # fl = np.array(frequency_list)*n
    # min_lm = fractions.Fraction(fl[0], fl[1])
    # if target_length_mus < min_lm:
    #     raise Exception("The chosen 'target_length_mus' is too short or the given frequencies are too odd or too many decimal places have been given. \nSuggested procedure is either reducing num_digits or enlengthening 'num_digits'.")
    # length_mus = round(target_length_mus/min_lm)*min_lm
    # return length_mus

    
def envelope(t0, t_space, pulse_dur, rise_time = .256):
    # hermite envelope after Bradley et al.
    a = 0.5*special.erf(2*(rise_time-t_space+t0)/rise_time)
    b = 0.5*special.erf(2*(rise_time+t_space-(pulse_dur+t0))/rise_time)
    return 1-a-b-1
    
def sin_envelope(t0, t_space, pulse_dur, phase, rf_freq, rise_time = .256/4):
    # sine signal under envelope
    sin = np.sin(2*np.pi*rf_freq*t_space+phase)
    return sin*envelope(t0, t_space, pulse_dur, rise_time)


def check_shift(t0, t_space, pulse_dur, phase, rf_freq, rise_time = .001):
    # t0: start of pulse
    # t_space: sample list
    # rise_time: rise time of error function for envelope. When no envelope is used, rectangular is approximated by rise time of 1ns.
    # shifts beginning of rf pulse by maximum of rf-period/2 to minimize the area under the rf signal.
    time_steps = t_space[1]-t_space[0]
    area_up = np.abs(np.sum(sin_envelope(t0, t_space, pulse_dur, rf_freq, phase, rise_time)))
    area_down = area_up
    n_up = 0
    n_down = 0
    while time_steps * n_up < 1/rf_freq/2:
        n_up+=1
        next_area_up = np.abs(np.sum(sin_envelope(t0 + time_steps * n_up, t_space, pulse_dur, phase, rf_freq, rise_time)))
        if next_area_up > area_up:
            n_up -= 1
            break
        else:
            area_up = next_area_up
    while time_steps * n_down < 1/rf_freq/2:
        n_down-=1
        next_area_down = np.abs(np.sum(sin_envelope(t0 + time_steps * n_down, t_space, pulse_dur, phase, rf_freq, rise_time)))
        if next_area_down > area_down:
            n_down += 1
            break
        else:
            area_down = next_area_down
    if area_up < area_down:
        n = n_up
    elif area_up > area_down:
        n = n_down
    else:
        n = 0
    return time_steps * n


def shift_pulse(seq, t_space, rf_freq):
    # Shift RF Pulse to be aligned with start of period of sine wave.
    total_time = 0
    for key in seq.column_dict.keys():
        total_time += np.sum(seq.times_fields_aphi(key), axis = 0)[0]
    mw = seq.times_fields_aphi('mw')
    rf = seq.times_fields_aphi('rf')
    wait = seq.times_fields_aphi('wait')
    shifts = []
    current_time = 0
    # loop over all sequence steps
    # if step is an rf pulse, check by how much it needs to be shifted to be aligned with the rotating frame.
    for step in seq.sequence_steps:
        idx = int(step[1])-1
        if step[0] == 'mw':
            current_time += mw[idx, 0]
        if step[0] == 'rf':
            shifts.append(check_shift(current_time, t_space, rf[idx, 0], rf[idx, 2], rf_freq))
            current_time += rf[idx, 0]
        elif step[0] == 'wait':
            current_time += wait[idx, 0]
    #print(shifts)
    return shifts


def full_wavelength_improved(frequency_list, target_length_mus, num_digits=3, sampling_frequency=12):
    fl = copy.deepcopy(frequency_list)
    if target_length_mus < 5*64/(sampling_frequency*1000):
        raise Exception('target_length_mus too short!')
    fl.append(fractions.Fraction(sampling_frequency*1000, 64))
    n = max([len(str(round(f, num_digits)).split('.')) for f in fl])
    fl = np.array(fl)*n
    min_lm = fractions.Fraction(fl[0], fl[1])
    if target_length_mus < min_lm:
        raise Exception("The chosen 'target_length_mus' is too short or the given frequencies are too odd or too many decimal places have been given. \nSuggested procedure is either reducing num_digits or enlengthening num_digits.")
    length_mus = round(target_length_mus/min_lm)*min_lm
    return length_mus - 0.9/(sampling_frequency*1e3)


def ret_sms(**kwargs):
    def sspin_type(nuc):
        s = nuc.split(' ')[0].replace('14N', '').replace('13C', '').replace('14n', '').replace('13c', '')
        nuc = nuc.replace('14N', '14n')
        if '14n' in nuc:
            spin_type = '14n ' + s
        else:
            spin_type = '13c'
        return {'s': s, 'spin_type': spin_type}
    if 'transition' in kwargs:
        transition = kwargs['transition'].split(' ')
        ms = transition[1][2:]
        nuc = transition[0]
        r = {'nuc': nuc, 'ms': ms}
        r.update(sspin_type(nuc))
        return r
    elif 'nuc' in kwargs:
        return sspin_type(kwargs['nuc'])

def ret_tl(param_lists):
    return list(itertools.product(*[x[1] for x in param_lists]))

def ret_pds(param_lists, tl):
    return [collections.OrderedDict([[param_lists[i][0], config[i]] for i in range(len(config))]) for config in tl]

def nuclear_settings(nuclear, ret_mcas, analyze_sequence, meas_code, pdc=None, **kwargs):
    if pdc is None:
        pdc = {}
    nuclear.reset_settings()
    if 'script_path' in kwargs:
        nuclear.make_save_location_params(script_path=kwargs['script_path'], folder=r"C:/Users/Erik Hesselmeier/Desktop/NuclearOpsData", sub_folder_kw="UserScripts")
    for key, val in pdc.items():
        if hasattr(val, '__iter__'):
            nuclear.file_name += "_{}{}".format(key, "_".join([str(i) for i in val]))
        else:
            nuclear.file_name += "_{}{}".format(key, val)

    # FIXME
    nuclear.ana_trace.analyze_sequence=analyze_sequence
    nuclear.meas_code = meas_code
    nuclear.ret_mcas = ret_mcas

def confocal_settings():
    pass
    #print('fix me 2')
    #FIXME later deprecarted in qudi
    #pi3d.confocal.reset_settings()
    #pi3d.confocal.aom_voltage = -6

def gated_counter_settings():
    pass
    #FIXME depracated in qudi
    #print('fix me 3')
    #pi3d.gated_counter.reset_settings()

def settings(**kwargs):
    nuclear_settings(**kwargs)
    confocal_settings()

def file_notes_frequencies():
    out = ""
    for t in pi3d.tt.transitions:
        out += "{}\t{}\n".format(t.name, t.current_frequency)
    return out[:-1]

def read_original_filepath(file_path): #used since the new queuelogic
    """Reads the original file path from the top comment of a Python file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        first_lines = [next(f) for _ in range(2)]  # read first two lines

    for line in first_lines:
        if line.startswith("# Original file path:"):
            return line.replace("# Original file path:", "").strip()
    return None


def create_nuclear(script_path):
    try: #used since the new queuelogic
        if not "UserScripts" in script_path:
            script_path =read_original_filepath(script_path)
    except:
        print("could not retriev original path, we will get an error.")
        pass

    reload(qudi.logic.NuclearOPs)
    if not os.path.isfile(script_path):
        raise Exception('Error: ', script_path)
    print(1)
    nuclear = qudi.logic.NuclearOPs.NuclearOPs()#TODO fill config here
    nuclear.make_save_location_params(script_path=script_path,
                                      folder= r"C:/Users/Erik Hesselmeier/Desktop/NuclearOpsData",
                                      sub_folder_kw="UserScripts")
    print(2)
    nuclear_name = "NuclearOPs{}_{}".format(nuclear.file_name, datetime.datetime.strftime(nuclear.date_of_creation, nuclear.__TITLE_DATE_FORMAT__))
    print(3)
    nuclear.pld = data_handling.PlotData(title=nuclear_name, gui=True)
    print("created_plot_data")
    #nuclear.file_notes = ''#TODO get transition tracker here... file_notes_frequencies()
    nuclear.__dict__['file_notes'] = ''
    #setattr(pi3d, nuclear_name, nuclear)##todo
    print("created_nuclear__")
    return nuclear


##########################################
# For tomography preperations to find gates

import sympy as sp
from collections import deque
from sympy.physics.quantum import TensorProduct
import numpy as np

class Tomography_helper:
    # ---------------------------------------------------------------------
    # User must define/import:
    # sigma_x, sigma_y, sigma_z
    # H1,H2,S1,S2,CNOT12,CNOT21
    # ---------------------------------------------------------------------
    # Example placeholders:
    # sigma_x = ...
    # sigma_y = ...
    # sigma_z = ...

    print("building helper")
    # Pauli matrices

    I2 = sp.eye(2)
    I=I2

    X = sp.Matrix([[0,1],[1,0]])
    sigma_x=X
    Y = sp.Matrix([[0,-sp.I],[sp.I,0]])
    sigma_y=Y
    Z = sp.Matrix([[1,0],[0,-1]])
    sigma_z=Z

    H = sp.Matrix([[1,1],[1,-1]])/sp.sqrt(2)
    S = sp.Matrix([[1,0],[0,sp.I]])

    # CNOT (control qubit 0 -> target qubit 1)
    CNOT01 = sp.Matrix([
    [1,0,0,0],
    [0,1,0,0],
    [0,0,0,1],
    [0,0,1,0]
    ])

    # reverse CNOT
    CNOT10 = sp.Matrix([
    [1,0,0,0],
    [0,0,0,1],
    [0,0,1,0],
    [0,1,0,0]
    ])

    SWAP = sp.Matrix([
    [1,0,0,0],
    [0,0,1,0],
    [0,1,0,0],
    [0,0,0,1]
    ])

    H1= TensorProduct(H,I2)
    H2= TensorProduct(I2,H)

    S1= TensorProduct(S,I2)
    S2= TensorProduct(I2,S)

    CNOT12= CNOT01
    CNOT21= CNOT10

    SWAP= SWAP


    pauli = {"I":I2,"X":X,"Y":Y,"Z":Z}

    paulis = {}

    for a in "IXYZ":
        for b in "IXYZ":
            paulis[a+b] = TensorProduct(pauli[a],pauli[b])

    def equal_up_to_sign(self,A,B):
        return sp.simplify(A-B)==sp.zeros(4) or \
            sp.simplify(A+B)==sp.zeros(4)

    def conjugate(self,U,P):
        return sp.simplify(U*P*U.H)

    basis = [
        TensorProduct(I,I),
        
        TensorProduct(sigma_x,I),
        TensorProduct(sigma_y,I),
        TensorProduct(sigma_z,I),

        TensorProduct(I,sigma_x),
        TensorProduct(I,sigma_y),
        TensorProduct(I,sigma_z),

        TensorProduct(sigma_x,sigma_x),
        TensorProduct(sigma_x,sigma_y),
        TensorProduct(sigma_x,sigma_z),

        TensorProduct(sigma_y,sigma_x),
        TensorProduct(sigma_y,sigma_y),
        TensorProduct(sigma_y,sigma_z),

        TensorProduct(sigma_z,sigma_x),
        TensorProduct(sigma_z,sigma_y),
        TensorProduct(sigma_z,sigma_z),
    ]

    pauli_names = [
        "II",

        "XI","YI","ZI",
        "IX","IY","IZ",

        "XX","XY","XZ",
        "YX","YY","YZ",
        "ZX","ZY","ZZ"
    ]

    TP=TensorProduct




    def __init__(self):
        self.create_generators()
        self.create_transitions()

    def pauli_name(self,P):
        """
        Return the Pauli label corresponding to matrix P.
        Ignores an overall ± sign.
        """

        for name, M in self.paulis.items():

            if sp.simplify(P - M) == sp.zeros(4):
                return name

            if sp.simplify(P + M) == sp.zeros(4):
                return name

        return None

    def rx(self,phi):
        return sp.Matrix([
            [sp.cos(phi/2), -sp.I*sp.sin(phi/2)],
            [-sp.I*sp.sin(phi/2), sp.cos(phi/2)]
        ])


    def ry(self,phi):
        return sp.Matrix([
            [sp.cos(phi/2), -sp.sin(phi/2)],
            [sp.sin(phi/2),  sp.cos(phi/2)]
        ])

    def Rx1(self,phi):
        return self.TP(sp.Matrix(self.rx(phi)),self.I2)
    def Ry1(self,phi):
        return self.TP(sp.Matrix(self.ry(phi)),self.I2)

    def Rx2(self,phi):
        return self.TP(self.I2,sp.Matrix(self.rx(phi)))
    def Ry2(self,phi):
        return self.TP(self.I2,sp.Matrix(self.ry(phi)))

    def create_generators(self):
        self.generators2 = {
            "Rx90_1": self.Rx1(sp.pi/2),
            "Rxm90_1": self.Rx1(-sp.pi/2),

            "Ry90_1": self.Ry1(sp.pi/2),
            "Rym90_1": self.Ry1(-sp.pi/2),

            "Rx90_2": self.Rx2(sp.pi/2),
            "Rxm90_2": self.Rx2(-sp.pi/2),

            "Ry90_2": self.Ry2(sp.pi/2),
            "Rym90_2": self.Ry2(-sp.pi/2),

            "CNOT12": self.CNOT12,
            "CNOT21": self.CNOT21,
        }


    def build_paulis(self,sigma_x,sigma_y,sigma_z):
        I=sp.eye(2)
        names=["I","X","Y","Z"]
        mats={"I":I,"X":sigma_x,"Y":sigma_y,"Z":sigma_z}

        paulis={}
        basis=[]
        pauli_names=[]

        for a in names:
            for b in names:
                name=a+b
                P=TensorProduct(mats[a],mats[b])
                paulis[name]=sp.simplify(P)
                basis.append(P)
                pauli_names.append(name)

        return paulis,basis,pauli_names

    def pauli_with_sign(self,P, paulis):
        for n,M in paulis.items():
            if sp.simplify(P-M)==sp.zeros(4):
                return 1,n
            if sp.simplify(P+M)==sp.zeros(4):
                return -1,n
        return None,None

    def build_transition_table(self,paulis):
        transitions={}
        for pname,P in paulis.items():
            if pname=="II":
                continue
            transitions[pname]={}
            for g,G in self.generators2.items():
                s,n=self.pauli_with_sign(sp.simplify(G*P*G.H),paulis)
                transitions[pname][g]=(s,n)
        return transitions

    def find_sequence(self,target, transitions):
        start=(1,target)
        goal=(1,"IZ")
        q=deque([(start,[])])
        visited={start}
        while q:
            state,path=q.popleft()
            if state==goal:
                return state[0],path
            s,p=state
            for gate,(sgn,nxt) in transitions[p].items():
                new=(s*sgn,nxt)
                if new not in visited:
                    visited.add(new)
                    q.append((new,path+[gate]))
        return None,None

    def sequence_to_unitary(self,seq):
        U=sp.eye(4)
        for g in seq:
            U=self.generators2[g]*U
        return sp.simplify(U)

    def apply_measurement_sequence(self,rho,seq):
        U=self.sequence_to_unitary(seq)
        return sp.simplify(U*rho*U.H)

    def measure_pauli_compiled(self,rho,name,paulis,transitions):
        if name=="II":
            return sp.Integer(1)
        sign,seq=self.find_sequence(name,transitions)
        rho_rot=self.apply_measurement_sequence(rho,seq)
        Pp=(sp.eye(4)+paulis["IZ"])/2
        Pm=(sp.eye(4)-paulis["IZ"])/2
        pp=sp.trace(Pp*rho_rot)
        pm=sp.trace(Pm*rho_rot)
        return sp.simplify(sign*(pp-pm))

    def pauli_measurements(self,rho, pauli_names, paulis, transitions):
        vals=[self.measure_pauli_compiled(rho,n,paulis,transitions)
            for n in pauli_names]
        return sp.Matrix(vals)

    def reconstruct_pauli(self,coeffs,basis):
        rho=sp.zeros(4)
        for c,B in zip(coeffs,basis):
            rho+=c*B
        return sp.simplify(rho/4)

    def verify_sequence(self,target,paulis,transitions):
        sign,seq=self.find_sequence(target,transitions)
        U=self.sequence_to_unitary(seq)
        lhs=sp.simplify(U.H*paulis["IZ"]*U)
        rhs=sign*paulis[target]
        ok=sp.simplify(lhs-rhs)==sp.zeros(4)
        return ok,sign,seq

    def pauli_full_test(self,rho, basis, pauli_names, paulis, transitions):
        coeffs=self.pauli_measurements(rho,pauli_names,paulis,transitions)
        rho_rec=self.reconstruct_pauli(coeffs,basis)
        return sp.simplify(rho_rec-rho), coeffs, rho_rec

    def create_transitions(self):
        self.transitions = {}

        for pname, P in self.paulis.items():

            if pname == "II":
                continue

            self.transitions[pname] = {}

            for gname, G in self.generators2.items():

                P2 = sp.simplify(G * P * G.H)

                #transitions[pname][gname] = pauli_name(P2)
                sign,newname = self.pauli_with_sign(P2,self.paulis)
                self.transitions[pname][gname] = (sign,newname)

    def get_measurement_sequence(self,target):
        return self.find_sequence(target,self.transitions)

# for p in sorted(transitions):
#     print("\n", p)

#     for g in transitions[p]:
#         print(f"  {g:8s} -> {transitions[p][g]}")




if __name__ == '__main__':
    print(ret_sms(transition='13C90 ms-1'))