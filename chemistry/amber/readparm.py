"""
This module is simply a namespace for all Amber topology-like classes. There are
different variants; for instance the standard Amber topology, the chamber-made
topology, and the tinker_to_amber-made topology. These classes are all defined
in their own private modules, but imported here to simplify the API.

Copyright (C) 2010 - 2014  Jason Swails

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
   
You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330,
Boston, MA 02111-1307, USA.
"""

from chemistry.amber.amberformat import AmberFormat
from chemistry.amber._amberparm import AmberParm, Rst7
from chemistry.amber._chamberparm import ChamberParm, ConvertFromPSF
from chemistry.amber._tinkerparm import AmoebaParm, BeemanRestart
from warnings import warn as _warn

# Define importables via *
__all__ = ['AmberFormat', 'AmberParm', 'ChamberParm', 'LoadParm', 'Rst7']

# For backwards compatibility, but this will be eliminated
class rst7(Rst7):
    """ Amber input coordinate (or restart coordinate) file format """

    def __init__(self, filename=None):
        _warn('rst7 is deprecated. Use Rst7 instead.', DeprecationWarning)
        super(rst7, self).__init__(filename=filename)
   

# Supply a function to load a topology file in the 'correct' format
def LoadParm(parmname, rst7name=None):
    """
    Loads a topology file using the correct class.

    Parameters:
        parmname (str): The name of the topology file to load
        rst7name (str): The (optional) name of the restart file to load

    Returns:
        AmberParm or ChamberParm instance, depending on whether it is an Amber
        topology (i.e., created with LEaP) or a Chamber topology (i.e., created
        with chamber), respectively. If the restart file is not None, it will
        load the restart file into the parameter file
    """
    parm = AmberFormat(parmname)
    if 'CTITLE' in parm.flag_list:
        parm = parm.view(ChamberParm)
    elif 'AMOEBA_FORCEFIELD' in parm.flag_list:
        parm = parm.view(AmoebaParm)
    else:
        parm = parm.view(AmberParm)

    # Now load the restart file
    if rst7name is not None:
        rst = Rst7.open(rst7name)
        parm.LoadRst7(rst)

    return parm
