0      NuclearOps         40174.405333 1
   0      triggerwait        0.864000   1
      0      trigger            0.864000   wait 0 1
      1      waittrigger        0.000000   wait 0 0
      2      _missing_smpls_    0.000000   wait 0 0
   1      Repump             30.080000  5
      0      Repump             6.016000   wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   2      Decay              1.024000   1
      0      RepumpDecay        1.024000   wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   3      init               200.000000 20
      0      resonant_init      10.000000  sinehermite [5424.52002849 5429.33002849 5564.09028026 5568.90028026] [0.   0.   0.04 0.04] [0. 0. 0. 0.] 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   4      init_correction    49.450667  1
      0      resonant_init      0.000000   sinehermite [5424.52002849 5429.33002849 5564.09028026 5568.90028026] [0.   0.   0.04 0.04] [0. 0. 0. 0.] 0 0
      1      resonant_init      1.024000   wait 0 0
      2      Init Decay         0.512000   wait 0 0
      3                         0.256000   wait 0 0
      4      e_rabi             0.314000   sine [5429.33002849] [0.95] [0.] 0 0
      5      RFSafetyWait1      0.992000   wait 0 0
      6      nuc                44.350000  wait 0 0
      7      RFSafetyWait2      2.000000   wait 0 0
      8      _missing_smpls_    0.002667   wait 0 0
   5      ssr29si8_A2        7968.000000 2000
      0      triggerTrue_gate   0.064000   wait 1 0
      1      MW                 0.192000   wait 0 0
      2      MW                 0.295000   sinehermite [5424.52002849] [0.9] [0.] 0 0
      3      MW                 0.295000   sinehermite [5564.09028026] [0.83] [0.] 0 0
      4      Laser A2           3.072000   wait 0 0
      5      Count              0.000000   wait 0 0
      6      triggerTrue2_memory 0.064000   wait 0 0
      7      _missing_smpls_    0.002000   wait 0 0
   6      Init               2704.416000 3
      0      resonant_init      100.000000 sinehermite [5429.33002849 5568.90028026] [0.   0.04] [0. 0.] 0 0
      1      resonant_init      1.024000   wait 0 0
      2      Init Decay         0.512000   wait 0 0
      3                         0.256000   wait 0 0
      4      electron rabi      0.186000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      5                         0.433000   wait 0 0
      6      nuc                18.876000  wait 0 0
      7                         0.433000   wait 0 0
      8      electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [120.] 0 0
      9                         0.475000   wait 0 0
      10     nuc                38.720000  wait 0 0
      11                        0.475000   wait 0 0
      12     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      13                        0.475000   wait 0 0
      14     nuc                38.720000  wait 0 0
      15                        0.475000   wait 0 0
      16     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [180.] 0 0
      17                        0.475000   wait 0 0
      18     nuc                38.720000  wait 0 0
      19                        0.475000   wait 0 0
      20     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      21                        0.475000   wait 0 0
      22     nuc                38.720000  wait 0 0
      23                        0.475000   wait 0 0
      24     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [120.] 0 0
      25                        0.475000   wait 0 0
      26     nuc                38.720000  wait 0 0
      27                        0.475000   wait 0 0
      28     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [120.] 0 0
      29                        0.475000   wait 0 0
      30     nuc                38.720000  wait 0 0
      31                        0.475000   wait 0 0
      32     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      33                        0.475000   wait 0 0
      34     nuc                38.720000  wait 0 0
      35                        0.475000   wait 0 0
      36     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [180.] 0 0
      37                        0.475000   wait 0 0
      38     nuc                38.720000  wait 0 0
      39                        0.475000   wait 0 0
      40     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      41                        0.475000   wait 0 0
      42     nuc                38.720000  wait 0 0
      43                        0.475000   wait 0 0
      44     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [120.] 0 0
      45                        0.433000   wait 0 0
      46     nuc                18.876000  wait 0 0
      47                        0.433000   wait 0 0
      48     electron rabi      0.186000   sinehermite [5429.33002849] [0.95] [180.] 0 0
      49                        0.433000   wait 0 0
      50     nuc                18.876000  wait 0 0
      51                        0.433000   wait 0 0
      52     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [30.] 0 0
      53                        0.475000   wait 0 0
      54     nuc                38.720000  wait 0 0
      55                        0.475000   wait 0 0
      56     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [0.] 0 0
      57                        0.475000   wait 0 0
      58     nuc                38.720000  wait 0 0
      59                        0.475000   wait 0 0
      60     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      61                        0.475000   wait 0 0
      62     nuc                38.720000  wait 0 0
      63                        0.475000   wait 0 0
      64     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [0.] 0 0
      65                        0.475000   wait 0 0
      66     nuc                38.720000  wait 0 0
      67                        0.475000   wait 0 0
      68     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [30.] 0 0
      69                        0.475000   wait 0 0
      70     nuc                38.720000  wait 0 0
      71                        0.475000   wait 0 0
      72     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [30.] 0 0
      73                        0.475000   wait 0 0
      74     nuc                38.720000  wait 0 0
      75                        0.475000   wait 0 0
      76     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [0.] 0 0
      77                        0.475000   wait 0 0
      78     nuc                38.720000  wait 0 0
      79                        0.475000   wait 0 0
      80     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      81                        0.475000   wait 0 0
      82     nuc                38.720000  wait 0 0
      83                        0.475000   wait 0 0
      84     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [0.] 0 0
      85                        0.475000   wait 0 0
      86     nuc                38.720000  wait 0 0
      87                        0.475000   wait 0 0
      88     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [30.] 0 0
      89                        0.433000   wait 0 0
      90     nuc                18.876000  wait 0 0
      91                        0.433000   wait 0 0
      92     _missing_smpls_    0.000000   wait 0 0
   7      init               200.000000 20
      0      resonant_init      10.000000  sinehermite [5429.33002849 5568.90028026] [0.   0.24] [0. 0.] 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   8      init_correction    1.536000   1
      0      resonant_init      0.000000   sinehermite [5429.33002849 5568.90028026] [0.   0.24] [0. 0.] 0 0
      1      resonant_init      1.024000   wait 0 0
      2      Init Decay         0.512000   wait 0 0
      3      _missing_smpls_    0.000000   wait 0 0
   9      SEDOR              200.256000 1
      0                         0.256000   wait 0 0
      1      nuc                200.000000 wait 0 0
      2      _missing_smpls_    0.000000   wait 0 0
   10     Tau                9000.000000 9
      0                         1000.000000 wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   11     TauRest            1962.000000 1
      0                         899.488000 wait 0 0
      1                         0.512000   wait 0 0
      2      nuc                400.000000 wait 0 0
      3      nuc                662.000000 wait 0 0
      4      _missing_smpls_    0.000000   wait 0 0
   12     Tau                8000.000000 8
      0                         1000.000000 wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   13     TauRest            1385.626667 1
      0                         937.488000 wait 0 0
      1                         0.512000   wait 0 0
      2                         0.256000   wait 0 0
      3      electron rabi      0.186000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      4                         0.433000   wait 0 0
      5      nuc                18.876000  wait 0 0
      6                         0.433000   wait 0 0
      7      electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [120.] 0 0
      8                         0.475000   wait 0 0
      9      nuc                38.720000  wait 0 0
      10                        0.475000   wait 0 0
      11     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      12                        0.475000   wait 0 0
      13     nuc                38.720000  wait 0 0
      14                        0.475000   wait 0 0
      15     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [180.] 0 0
      16                        0.475000   wait 0 0
      17     nuc                38.720000  wait 0 0
      18                        0.475000   wait 0 0
      19     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      20                        0.475000   wait 0 0
      21     nuc                38.720000  wait 0 0
      22                        0.475000   wait 0 0
      23     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [120.] 0 0
      24                        0.475000   wait 0 0
      25     nuc                38.720000  wait 0 0
      26                        0.475000   wait 0 0
      27     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [120.] 0 0
      28                        0.475000   wait 0 0
      29     nuc                38.720000  wait 0 0
      30                        0.475000   wait 0 0
      31     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      32                        0.475000   wait 0 0
      33     nuc                38.720000  wait 0 0
      34                        0.475000   wait 0 0
      35     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [180.] 0 0
      36                        0.475000   wait 0 0
      37     nuc                38.720000  wait 0 0
      38                        0.475000   wait 0 0
      39     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [90.] 0 0
      40                        0.475000   wait 0 0
      41     nuc                38.720000  wait 0 0
      42                        0.475000   wait 0 0
      43     electron rabi      0.314000   sinehermite [5429.33002849] [0.95] [120.] 0 0
      44                        0.433000   wait 0 0
      45     nuc                18.876000  wait 0 0
      46                        0.433000   wait 0 0
      47     electron rabi      0.186000   sinehermite [5429.33002849] [0.95] [180.] 0 0
      48     RFSafetyWait1      0.992000   wait 0 0
      49     nuc                44.350000  wait 0 0
      50     RFSafetyWait2      2.000000   wait 0 0
      51     _missing_smpls_    0.002667   wait 0 0
   14     ssr29si8_A2        7968.000000 2000
      0      triggerTrue_gate   0.064000   wait 1 0
      1      MW                 0.192000   wait 0 0
      2      MW                 0.295000   sinehermite [5424.52002849] [0.9] [0.] 0 0
      3      MW                 0.295000   sinehermite [5564.09028026] [0.83] [0.] 0 0
      4      Laser A2           3.072000   wait 0 0
      5      Count              0.000000   wait 0 0
      6      triggerTrue2_memory 0.064000   wait 0 0
      7      _missing_smpls_    0.002000   wait 0 0
   15     ssrcharge_state    502.128000 1
      0      gate1              0.064000   wait 1 0
      1      State_check        500.000000 wait 0 0
      2      wait               2.000000   wait 0 0
      3      memory             0.064000   wait 0 0
      4      Count              0.000000   wait 0 0
      5      _missing_smpls_    0.000000   wait 0 0
   16     w_trig_safety      1.024000   1
      0      w_trig_safety      1.024000   wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
-------------------------------------------------------------------


-------------------------------------------------------------------
0      NuclearOps         40174.405333 1
   0      triggerwait        0.864000   1
      0      trigger            0.864000   wait 0 0
      1      waittrigger        0.000000   wait 0 0
      2      _missing_smpls_    0.000000   wait 0 0
   1      Repump             30.080000  5
      0      Repump             6.016000   wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   2      Decay              1.024000   1
      0      RepumpDecay        1.024000   wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   3      init               200.000000 20
      0      resonant_init      10.000000  wait 1 0
      1      _missing_smpls_    0.000000   wait 0 0
   4      init_correction    49.450667  1
      0      resonant_init      0.000000   wait 1 0
      1      resonant_init      1.024000   wait 0 0
      2      Init Decay         0.512000   wait 0 0
      3                         0.256000   wait 1 0
      4      e_rabi             0.314000   wait 1 0
      5      RFSafetyWait1      0.992000   wait 0 0
      6      nuc                44.350000  sinehermite_rf [-8.88492] [0.9] [0.] 0 0
      7      RFSafetyWait2      2.000000   wait 0 0
      8      _missing_smpls_    0.002667   wait 0 0
   5      ssr29si8_A2        7968.000000 2000
      0      triggerTrue_gate   0.064000   wait 1 0
      1      MW                 0.192000   wait 1 0
      2      MW                 0.295000   wait 1 0
      3      MW                 0.295000   wait 1 0
      4      Laser A2           3.072000   wait 0 0
      5      Count              0.000000   wait 0 0
      6      triggerTrue2_memory 0.064000   wait 0 1
      7      _missing_smpls_    0.002000   wait 0 0
   6      Init               2704.416000 3
      0      resonant_init      100.000000 wait 1 0
      1      resonant_init      1.024000   wait 0 0
      2      Init Decay         0.512000   wait 0 0
      3                         0.256000   wait 1 0
      4      electron rabi      0.186000   wait 1 0
      5                         0.433000   wait 1 0
      6      nuc                18.876000  sinehermite_rf [2.06658932] [0.49] [0.] 0 0
      7                         0.433000   wait 1 0
      8      electron rabi      0.314000   wait 1 0
      9                         0.475000   wait 1 0
      10     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-23.48563678] 0 0
      11                        0.475000   wait 1 0
      12     electron rabi      0.314000   wait 1 0
      13                        0.475000   wait 1 0
      14     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-46.97127356] 0 0
      15                        0.475000   wait 1 0
      16     electron rabi      0.314000   wait 1 0
      17                        0.475000   wait 1 0
      18     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-70.45691034] 0 0
      19                        0.475000   wait 1 0
      20     electron rabi      0.314000   wait 1 0
      21                        0.475000   wait 1 0
      22     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-93.94254712] 0 0
      23                        0.475000   wait 1 0
      24     electron rabi      0.314000   wait 1 0
      25                        0.475000   wait 1 0
      26     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-117.4281839] 0 0
      27                        0.475000   wait 1 0
      28     electron rabi      0.314000   wait 1 0
      29                        0.475000   wait 1 0
      30     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-140.91382068] 0 0
      31                        0.475000   wait 1 0
      32     electron rabi      0.314000   wait 1 0
      33                        0.475000   wait 1 0
      34     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-164.39945746] 0 0
      35                        0.475000   wait 1 0
      36     electron rabi      0.314000   wait 1 0
      37                        0.475000   wait 1 0
      38     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [172.11490576] 0 0
      39                        0.475000   wait 1 0
      40     electron rabi      0.314000   wait 1 0
      41                        0.475000   wait 1 0
      42     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [148.62926899] 0 0
      43                        0.475000   wait 1 0
      44     electron rabi      0.314000   wait 1 0
      45                        0.433000   wait 1 0
      46     nuc                18.876000  sinehermite_rf [2.06658932] [0.49] [125.14363221] 0 0
      47                        0.433000   wait 1 0
      48     electron rabi      0.186000   wait 1 0
      49                        0.433000   wait 1 0
      50     nuc                18.876000  sinehermite_rf [2.06658932] [0.49] [39.9924541] 0 0
      51                        0.433000   wait 1 0
      52     electron rabi      0.314000   wait 1 0
      53                        0.475000   wait 1 0
      54     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [16.50681732] 0 0
      55                        0.475000   wait 1 0
      56     electron rabi      0.314000   wait 1 0
      57                        0.475000   wait 1 0
      58     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-6.97881946] 0 0
      59                        0.475000   wait 1 0
      60     electron rabi      0.314000   wait 1 0
      61                        0.475000   wait 1 0
      62     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-30.46445624] 0 0
      63                        0.475000   wait 1 0
      64     electron rabi      0.314000   wait 1 0
      65                        0.475000   wait 1 0
      66     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-53.95009302] 0 0
      67                        0.475000   wait 1 0
      68     electron rabi      0.314000   wait 1 0
      69                        0.475000   wait 1 0
      70     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-77.4357298] 0 0
      71                        0.475000   wait 1 0
      72     electron rabi      0.314000   wait 1 0
      73                        0.475000   wait 1 0
      74     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-100.92136658] 0 0
      75                        0.475000   wait 1 0
      76     electron rabi      0.314000   wait 1 0
      77                        0.475000   wait 1 0
      78     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-124.40700336] 0 0
      79                        0.475000   wait 1 0
      80     electron rabi      0.314000   wait 1 0
      81                        0.475000   wait 1 0
      82     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-147.89264014] 0 0
      83                        0.475000   wait 1 0
      84     electron rabi      0.314000   wait 1 0
      85                        0.475000   wait 1 0
      86     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-171.37827691] 0 0
      87                        0.475000   wait 1 0
      88     electron rabi      0.314000   wait 1 0
      89                        0.433000   wait 1 0
      90     nuc                18.876000  sinehermite_rf [2.06658932] [0.49] [165.13608631] 0 0
      91                        0.433000   wait 1 0
      92     _missing_smpls_    0.000000   wait 0 0
   7      init               200.000000 20
      0      resonant_init      10.000000  wait 1 0
      1      _missing_smpls_    0.000000   wait 0 0
   8      init_correction    1.536000   1
      0      resonant_init      0.000000   wait 1 0
      1      resonant_init      1.024000   wait 0 0
      2      Init Decay         0.512000   wait 0 0
      3      _missing_smpls_    0.000000   wait 0 0
   9      SEDOR              200.256000 1
      0                         0.256000   wait 0 0
      1      nuc                200.000000 sinehermite_rf [2.06658932] [0.373] [0.] 0 0
      2      _missing_smpls_    0.000000   wait 0 0
   10     Tau                9000.000000 9
      0                         1000.000000 wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   11     TauRest            1962.000000 1
      0                         899.488000 wait 0 0
      1                         0.512000   wait 0 0
      2      nuc                400.000000 sinehermite_rf [2.06658932] [0.373] [0.] 0 0
      3      nuc                662.000000 sinehermite_rf [-0.84583095] [0.] [0.] 0 0
      4      _missing_smpls_    0.000000   wait 0 0
   12     Tau                8000.000000 8
      0                         1000.000000 wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
   13     TauRest            1385.626667 1
      0                         937.488000 wait 0 0
      1                         0.512000   wait 0 0
      2                         0.256000   wait 1 0
      3      electron rabi      0.186000   wait 1 0
      4                         0.433000   wait 1 0
      5      nuc                18.876000  sinehermite_rf [2.06658932] [0.49] [-165.03413193] 0 0
      6                         0.433000   wait 1 0
      7      electron rabi      0.314000   wait 1 0
      8                         0.475000   wait 1 0
      9      nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [171.48023129] 0 0
      10                        0.475000   wait 1 0
      11     electron rabi      0.314000   wait 1 0
      12                        0.475000   wait 1 0
      13     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [147.99459451] 0 0
      14                        0.475000   wait 1 0
      15     electron rabi      0.314000   wait 1 0
      16                        0.475000   wait 1 0
      17     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [124.50895773] 0 0
      18                        0.475000   wait 1 0
      19     electron rabi      0.314000   wait 1 0
      20                        0.475000   wait 1 0
      21     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [101.02332095] 0 0
      22                        0.475000   wait 1 0
      23     electron rabi      0.314000   wait 1 0
      24                        0.475000   wait 1 0
      25     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [77.53768417] 0 0
      26                        0.475000   wait 1 0
      27     electron rabi      0.314000   wait 1 0
      28                        0.475000   wait 1 0
      29     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [54.05204739] 0 0
      30                        0.475000   wait 1 0
      31     electron rabi      0.314000   wait 1 0
      32                        0.475000   wait 1 0
      33     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [30.56641061] 0 0
      34                        0.475000   wait 1 0
      35     electron rabi      0.314000   wait 1 0
      36                        0.475000   wait 1 0
      37     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [7.08077383] 0 0
      38                        0.475000   wait 1 0
      39     electron rabi      0.314000   wait 1 0
      40                        0.475000   wait 1 0
      41     nuc                38.720000  sinehermite_rf [2.06658932] [0.49] [-16.40486295] 0 0
      42                        0.475000   wait 1 0
      43     electron rabi      0.314000   wait 1 0
      44                        0.433000   wait 1 0
      45     nuc                18.876000  sinehermite_rf [2.06658932] [0.49] [-39.89049973] 0 0
      46                        0.433000   wait 1 0
      47     electron rabi      0.186000   wait 1 0
      48     RFSafetyWait1      0.992000   wait 0 0
      49     nuc                44.350000  sinehermite_rf [-8.88492] [0.9] [0.] 0 0
      50     RFSafetyWait2      2.000000   wait 0 0
      51     _missing_smpls_    0.002667   wait 0 0
   14     ssr29si8_A2        7968.000000 2000
      0      triggerTrue_gate   0.064000   wait 1 0
      1      MW                 0.192000   wait 1 0
      2      MW                 0.295000   wait 1 0
      3      MW                 0.295000   wait 1 0
      4      Laser A2           3.072000   wait 0 0
      5      Count              0.000000   wait 0 0
      6      triggerTrue2_memory 0.064000   wait 0 1
      7      _missing_smpls_    0.002000   wait 0 0
   15     ssrcharge_state    502.128000 1
      0      gate1              0.064000   wait 0 0
      1      State_check        500.000000 wait 0 0
      2      wait               2.000000   wait 0 0
      3      memory             0.064000   wait 0 1
      4      Count              0.000000   wait 0 0
      5      _missing_smpls_    0.000000   wait 0 0
   16     w_trig_safety      1.024000   1
      0      w_trig_safety      1.024000   wait 0 0
      1      _missing_smpls_    0.000000   wait 0 0
-------------------------------------------------------------------


-------------------------------------------------------------------
[([], 795.0), (5,), (['repump'], 6016.0), (1,), ([], 1024.0), (20,), (['A1', 'laser'], 10000.0), (1,), (['A1', 'laser'], 0.0), (['A1', 'laser'], 1024.0), ([], 512.0), ([], 256.0), ([], 314.0), (['gateRF'], 992.0), (['gateRF'], 44350.0), (['gateRF'], 2000.0), (2000,), ([], 64.0), ([], 192.0), ([], 295.0), ([], 295.0), (['laser', 'A2'], 3072.0), ([], 0.0), ([], 64.0), (3,), (['A1', 'laser'], 100000.0), (['A1', 'laser'], 1024.0), ([], 512.0), ([], 256.0), (['gateRF'], 186.0), (['gateRF'], 433.0), (['gateRF'], 18876.0), (['gateRF'], 433.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 433.0), (['gateRF'], 18876.0), (['gateRF'], 433.0), (['gateRF'], 186.0), (['gateRF'], 433.0), (['gateRF'], 18876.0), (['gateRF'], 433.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 433.0), (['gateRF'], 18876.0), (['gateRF'], 433.0), (20,), (['A1', 'laser'], 10000.0), (1,), (['A1', 'laser'], 0.0), (['A1', 'laser'], 1024.0), ([], 512.0), (1,), (['gateRF'], 256.0), (['gateRF'], 200000.0), (9,), ([], 1000000), (1,), ([], 899488.0), (['gateRF'], 512.0), (['gateRF'], 400000.0), (['gateRF'], 662000.0), (8,), ([], 1000000), (1,), ([], 937488.0), (['gateRF'], 512.0), ([], 256.0), (['gateRF'], 186.0), (['gateRF'], 433.0), (['gateRF'], 18876.0), (['gateRF'], 433.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 475.0), (['gateRF'], 38720.0), (['gateRF'], 475.0), (['gateRF'], 314.0), (['gateRF'], 433.0), (['gateRF'], 18876.0), (['gateRF'], 433.0), (['gateRF'], 186.0), (['gateRF'], 992.0), (['gateRF'], 44350.0), (['gateRF'], 2000.0), (2000,), ([], 64.0), ([], 192.0), ([], 295.0), ([], 295.0), (['laser', 'A2'], 3072.0), ([], 0.0), ([], 64.0), (1,), ([], 64.0), (['A1', 'A2', 'laser'], 500000.0), ([], 2000.0), ([], 64.0), ([], 0.0)]
-------------------------------------------------------------------
