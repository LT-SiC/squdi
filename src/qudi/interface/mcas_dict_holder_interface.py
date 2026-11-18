# -*- coding: utf-8 -*-
"""
Interfaces of the MCAS logic (``McasDictHolderInterface``, implemented by ``mcas_dict_holder``) and of the
two hardware modules it connects to.

The style (``InterfaceMetaclass`` / ``abstractmethod``) follows the standard qudi interface files.
If the header of your existing ``interface/mcas_interface.py`` looks different (other import paths), copy
its import lines and ``_modtype``/``_modclass`` convention over to this file.
"""

from abc import abstractmethod
from qudi.core.module import Base


class McasDictHolderInterface(Base):
    """Logic module that owns the AWG memory and creates sequences (``mcas_dict_holder``).

    This is the interface that ``queue_logic``, ``transition_tracker`` and ``gated_counter_logic`` connect to
    (``Connector(interface='McasDictHolderInterface')``). Implementing modules provide, after activation:

        mcas_dict   MultiChSeqDict; ``.awgs['2g']`` / ``.awgs['ps']`` are the hardware modules
        mcas        class that creates a new sequence: ``mcas(name=..., ch_dict={...})``
        settings    McasSettings (marker_alias, master_awg, ...)

    These are plain attributes, so there is nothing abstract to declare here; the class only has to be in the
    base classes of the implementing module for qudi to accept the connection.
    """
    _modtype = 'McasDictHolderInterface'
    _modclass = 'interface'