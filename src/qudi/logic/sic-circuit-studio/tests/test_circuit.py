import ast
import math
import unittest
from backend.circuit import CircuitError, normalize, qasm2, qiskit_python, export

class CircuitTests(unittest.TestCase):
    def test_empty(self):
        c={'qubits':2,'columns':12,'gates':[]}
        self.assertIn('qreg q[2]',qasm2(c))
        self.assertEqual(normalize(c)['gates'],[])
    def test_angles(self):
        c={'qubits':2,'columns':12,'gates':[{'type':'rx','row':1,'col':2,'angle':math.pi/2}]}
        self.assertIn('rx(pi/2) q[1];',qasm2(c))
        ast.parse(qiskit_python(c))
    def test_ddrf_x_decomposition(self):
        c={'qubits':2,'columns':12,'gates':[{'type':'ddrf','row':0,'target':1,'col':0,'axis':'x','angle':math.pi/2,'sign':1}]}
        t=qasm2(c)
        self.assertIn('h q[1];\ncx q[0],q[1];\nrz(pi/2) q[1];\ncx q[0],q[1];\nh q[1];',t)
        ast.parse(export(c,'qiskit'))
    def test_ddrf_y_reverse(self):
        c={'qubits':2,'columns':12,'gates':[{'type':'ddrf','row':0,'target':1,'col':0,'axis':'y','angle':math.pi,'sign':-1}]}
        self.assertIn('ry(-pi) q[1];',qasm2(c))
    def test_ddrf_invalid_sign(self):
        c={'qubits':2,'columns':12,'gates':[{'type':'ddrf','row':0,'target':1,'col':0,'axis':'y','angle':math.pi,'sign':0}]}
        with self.assertRaises(CircuitError):normalize(c)
    def test_ddrf_requires_different_wires(self):
        with self.assertRaises(CircuitError):normalize({'qubits':1,'columns':12,'gates':[{'type':'ddrf','row':0,'target':0,'col':0,'axis':'x','angle':math.pi}]})
    def test_gate_collision(self):
        c={'qubits':3,'columns':12,'gates':[{'type':'cx','row':0,'target':2,'col':1},{'type':'h','row':1,'col':1}]}
        with self.assertRaises(CircuitError):normalize(c)
    def test_columns_empty_not_emitted(self):
        c={'qubits':2,'columns':250,'gates':[{'type':'h','row':0,'col':200}]}
        self.assertEqual(qasm2(c).count('h q[0];'),1)
    def test_legacy_supported(self):
        c={'qubits':3,'columns':12,'gates':[{'type':'rx','row':0,'col':0,'angle':math.pi/2},{'type':'ry','row':1,'col':1,'angle':math.pi},{'type':'cx','row':0,'target':2,'col':2}]}
        m=export(c,'mcas');self.assertIn('op.rx_nitrogen',m);self.assertIn('op.ry_carbon_414',m);self.assertIn('op.crot_pi_x_between_nuclear_spins',m)
        ast.parse(m)
    def test_legacy_reject_ddrf(self):
        c={'qubits':3,'columns':12,'gates':[{'type':'ddrf','row':0,'target':1,'col':0,'axis':'x','angle':math.pi/2,'sign':1}]}
        with self.assertRaises(CircuitError):export(c,'mcas')
    def test_legacy_reject_different_qubits(self):
        with self.assertRaises(CircuitError):export({'qubits':4,'columns':12,'gates':[]},'mcas')
    def test_bad_format(self):
        with self.assertRaises(CircuitError):export({'qubits':2,'columns':12,'gates':[]},'unknown')
    def test_reject_arbitrary_code(self):
        with self.assertRaises(CircuitError):normalize({'qubits':2,'columns':12,'gates':[{'type':'rx','row':0,'col':0,'angle':'__import__("os")'}]})
    def test_reject_invalid_qubits(self):
        with self.assertRaises(CircuitError):normalize({'qubits':26,'columns':12,'gates':[]})

    def test_extended_standard_gates(self):
        data={'qubits':3,'columns':12,'gates':[
            {'type':'sdg','row':0,'col':0},
            {'type':'sx','row':1,'col':0},
            {'type':'sxdg','row':2,'col':0},
            {'type':'cy','row':0,'target':2,'col':1},
            {'type':'ch','row':1,'target':2,'col':2},
            {'type':'crz','row':0,'target':1,'col':3,'angle':math.pi/2},
            {'type':'barrier','row':2,'col':4},
            {'type':'id','row':0,'col':4},
            {'type':'tdg','row':1,'col':4},
        ]}
        qasm=qasm2(data)
        for expected in ['sdg q[0];', 'sx q[1];', 'sxdg q[2];',
                         'cy q[0],q[2];','ch q[1],q[2];',
                         'crz(pi/2) q[0],q[1];', 'barrier q[2];',
                         'id q[0];', 'tdg q[1];']:
            self.assertIn(expected,qasm)
        code=qiskit_python(data)
        ast.parse(code)
        self.assertIn('qc.crz(pi/2, 0, 1)',code)
    def test_extended_gate_overlap(self):
        data={'qubits':3,'columns':12,'gates':[
          {'type':'ch','row':0,'target':2,'col':0},
          {'type':'s','row':1,'col':0},
        ]}
        with self.assertRaises(CircuitError):normalize(data)
if __name__=='__main__':unittest.main()
