# -*- coding: utf-8 -*-
"""Sequence building blocks for the M8190A + PulseStreamer setup (hardware independent)."""
import numpy as np
np.set_printoptions(linewidth=500, suppress=True)  # kept from the legacy __init__

from . import elements
from . import elements as el
from . import util
from .settings import McasSettings
from .sequence import MultiChSeq, MultiChSeqDict, make_mcas_class
