"""
This module contains classes for parsing and processing CHARMM parameter,
topology, and stream files. It only extracts atom properties from the
topology files and extracts all parameters from the parameter files

Author: Jason M. Swails
Contributors:
Date: April 5, 2014
"""
from chemistry.charmm._charmmfile import CharmmFile, CharmmStreamFile
from chemistry.charmm.topologyobjects import (AtomType, BondType, AngleType,
                    DihedralType, ImproperType, CmapType, UreyBradleyType,
                    NoUreyBradley)
from chemistry.exceptions import CharmmFileError
from chemistry.periodic_table import AtomicNum, Mass, Element
import os
import warnings

class CharmmParameterSet(object):
    """
    Stores a parameter set defined by CHARMM files. It stores the equivalent of
    the information found in the MASS section of the CHARMM topology file
    (TOP/RTF) and all of the information in the parameter files (PAR)

    Attributes:
        All type lists are dictionaries whose keys are tuples (with however
        many elements are needed to define that type of parameter). The types
        that can be in any order are SORTED.
        
        - atom_types_str
        - atom_types_int
        - atom_types_tuple
        - bond_types
        - angle_types
        - urey_bradley_types
        - dihedral_types
        - improper_types
        - cmap_types
        - nbfix_types

        The dihedral types can be multiterm, so the values for each dict key is
        actually a list of DihedralType instances. The atom_types are dicts that
        match the name (str), number (int), or (name, number) tuple (tuple) to
        the atom type. The tuple is guaranteed to be the most robust, although
        when only the integer or string is available the other dictionaries are
        helpful

    Parameters:
        - filenames : Load all of the parameter, topology, and stream files
            into the parameter set. The following file type suffixes are
            recognized. Unrecognized file types raise a TypeError
            .rtf, .top -- Residue Topology file
            .par, .prm -- Parameter file
            .str -- stream file
            .inp -- If "par" is in the file name, it is a parameter file. If
                    "top" is in the file name, it is a topology file
    """

    @staticmethod
    def _convert(data, type, msg=''):
        """
        Converts a data type to a desired type, raising CharmmFileError if it
        fails
        """
        try:
            return type(data)
        except ValueError:
            raise CharmmFileError('Could not convert %s to %s' % (msg, type))

    def __init__(self, *args):
        # Instantiate the list types
        self.atom_types_str = dict()
        self.atom_types_int = dict()
        self.atom_types_tuple = dict()
        self.bond_types = dict()
        self.angle_types = dict()
        self.urey_bradley_types = dict()
        self.dihedral_types = dict()
        self.improper_types = dict()
        self.cmap_types = dict()
        self.nbfix_types = dict()
        self.parametersets = []

        # Load all of the files
        tops, pars, strs = [], [], []
        for arg in args:
            if arg.endswith('.rtf') or arg.endswith('.top'):
                tops.append(arg)
            elif arg.endswith('.par') or arg.endswith('.prm'):
                pars.append(arg)
            elif arg.endswith('.str'):
                strs.append(arg)
            elif arg.endswith('.inp'):
                # Only consider the file name (since the directory is likely
                # "toppar" and will screw up file type detection)
                fname = os.path.split(arg)[1]
                if 'par' in fname:
                    pars.append(arg)
                elif 'top' in fname:
                    tops.append(arg)
                else:
                    raise TypeError('Unrecognized file type: %s' % arg)
            else:
                raise TypeError('Unrecognized file type: %s' % arg)
        for top in tops: self.read_topology_file(top)
        for par in pars: self.read_parameter_file(par)
        for strf in strs: self.read_stream_file(strf)

    @classmethod
    def load_set(cls, tfile=None, pfile=None, sfiles=[]):
        """
        Instantiates a CharmmParameterSet from a Topology file and a Parameter
        file (or just a Parameter file if it has all information)

        Parameters:
            - tfile (str) : Name of the Topology (RTF/TOP) file
            - pfile (str) : Name of the Parameter (PAR) file
            - sfiles (list of str) : List or tuple of stream (STR) file names.

        Returns:
            New CharmmParameterSet populated with the parameters found in the
            provided files.
            
        Notes:
            The RTF file is read first (if provided), followed by the PAR file,
            followed by the list of stream files (in the order they are
            provided). Parameters in each stream file will overwrite those that
            came before (or simply append to the existing set if they are
            different)
        """
        inst = cls()
        if tfile is not None:
            inst.read_topology_file(tfile)
        if pfile is not None:
            inst.read_parameter_file(pfile)
        if isinstance(sfiles, str):
            # The API docstring requests a list, but allow for users to pass a
            # string with a single filename instead
            inst.read_stream_file(sfiles)
        elif sfiles is not None:
            for sfile in sfiles:
                inst.read_stream_file(sfile)
        return inst

    def read_parameter_file(self, pfile):
        """
        Reads all of the parameters from a parameter file. Versions 36 and
        later of the CHARMM force field files have an ATOMS section defining
        all of the atom types.  Older versions need to load this information
        from the RTF/TOP files.

        Parameters:
            - pfile (str) : Name of the CHARMM PARameter file to read

        Notes: The atom types must all be loaded by the end of this routine.
        Either supply a PAR file with atom definitions in them or read in a
        RTF/TOP file first. Failure to do so will result in a raised
        RuntimeError.
        """
        conv = CharmmParameterSet._convert
        if isinstance(pfile, str):
            own_handle = True
            f = CharmmFile(pfile)
        else:
            own_handle = False
            f = pfile
        # What section are we parsing?
        section = None
        # The current cmap we are building (these span multiple lines)
        current_cmap = None
        current_cmap_data = []
        current_cmap_res = 0
        nonbonded_types = dict() # Holder
        needs_blank = False
        parameterset = None
        for line in f:
            line = line.strip()
            if not line:
                # This is a blank line
                needs_blank = False
                continue
            if parameterset is None and line.strip().startswith('*>>'):
                parameterset = line.strip()[1:78]
                continue
            # Set section if this is a section header
            if line.startswith('ATOMS'):
                section = 'ATOMS'
                continue
            if line.startswith('BONDS'):
                section = 'BONDS'
                continue
            if line.startswith('ANGLES'):
                section = 'ANGLES'
                continue
            if line.startswith('DIHEDRALS'):
                section = 'DIHEDRALS'
                continue
            if line.startswith('IMPROPER'):
                section = 'IMPROPER'
                continue
            if line.startswith('CMAP'):
                section = 'CMAP'
                continue
            if line.startswith('NONBONDED'):
                section = 'NONBONDED'
                needs_blank = True
                continue
            if line.startswith('NBFIX'):
                section = 'NBFIX'
                continue
            if line.startswith('HBOND'):
                section = None
                continue
            # It seems like files? sections? can be terminated with 'END'
            if line.startswith('END'): # should this be case-insensitive?
                section = None
                continue
            # If we have no section, skip
            if section is None: continue
            # Now handle each section specifically
            if section == 'ATOMS':
                if not line.startswith('MASS'): continue # Should this happen?
                words = line.split()
                try:
                    idx = conv(words[1], int, 'atom type')
                    name = words[2]
                    mass = conv(words[3], float, 'atom mass')
                except IndexError:
                    raise CharmmFileError('Could not parse MASS section.')
                # The parameter file might or might not have an element name
                try:
                    elem = words[4]
                    if len(elem) == 2:
                        elem = elem[0] + elem[1].lower()
                    atomic_number = AtomicNum[elem]
                except (IndexError, KeyError):
                    # Figure it out from the mass
                    atomic_number = AtomicNum[element_by_mass(mass)]
                atype = AtomType(name=name, number=idx, mass=mass,
                                 atomic_number=atomic_number)
                self.atom_types_str[atype.name] = atype
                self.atom_types_int[atype.number] = atype
                self.atom_types_tuple[(atype.name, atype.number)] = atype
                continue
            if section == 'BONDS':
                words = line.split()
                try:
                    type1 = words[0]
                    type2 = words[1]
                    k = conv(words[2], float, 'bond force constant')
                    req = conv(words[3], float, 'bond equilibrium dist')
                except IndexError:
                    raise CharmmFileError('Could not parse bonds.')
                key = (min(type1, type2), max(type1, type2))
                self.bond_types[key] = BondType(k, req)
                continue
            if section == 'ANGLES':
                words = line.split()
                try:
                    type1 = words[0]
                    type2 = words[1]
                    type3 = words[2]
                    k = conv(words[3], float, 'angle force constant')
                    theteq = conv(words[4], float, 'angle equilibrium value')
                except IndexError:
                    raise CharmmFileError('Could not parse angles.')
                key = (min(type1, type3), type2, max(type1, type3))
                self.angle_types[key] = AngleType(k, theteq)
                # See if we have a urey-bradley
                try:
                    ubk = conv(words[5], float, 'Urey-Bradley force constant')
                    ubeq = conv(words[6], float, 'Urey-Bradley equil. value')
                    ubtype = UreyBradleyType(ubk, ubeq)
                except IndexError:
                    ubtype = NoUreyBradley
                self.urey_bradley_types[key] = ubtype
                continue
            if section == 'DIHEDRALS':
                words = line.split()
                try:
                    type1 = words[0]
                    type2 = words[1]
                    type3 = words[2]
                    type4 = words[3]
                    k = conv(words[4], float, 'dihedral force constant')
                    n = conv(words[5], float, 'dihedral periodicity')
                    phase = conv(words[6], float, 'dihedral phase')
                except IndexError:
                    raise CharmmFileError('Could not parse dihedrals.')
                # Torsion can be in either direction. Sort by end groups first,
                # then sort by middle 2
                if type1 < type4:
                    key = (type1, type2, type3, type4)
                elif type1 > type4:
                    key = (type4, type3, type2, type1)
                else:
                    # OK, we need to sort by the middle atoms now
                    if type2 < type3:
                        key = (type1, type2, type3, type4)
                    else:
                        key = (type4, type3, type2, type1)
                # See if this is a second (or more) term of the dihedral group
                # that's already present.
                dihedral = DihedralType(k, n, phase)
                if key in self.dihedral_types:
                    # See if the existing dihedral type list has a term with
                    # the same periodicity -- If so, replace it
                    replaced = False
                    for i, dtype in enumerate(self.dihedral_types[key]):
                        if dtype.per == dihedral.per:
                            # Replace. Should we warn here?
                            warnings.warn('Replacing dihedral %r with %r' % 
                                          (dtype, dihedral))
                            self.dihedral_types[key]
                            replaced = True
                            break
                    if not replaced:
                        self.dihedral_types[key].append(dihedral)
                else: # key not present
                    self.dihedral_types[key] = [dihedral]
                continue
            if section == 'IMPROPER':
                words = line.split()
                try:
                    type1 = words[0]
                    type2 = words[1]
                    type3 = words[2]
                    type4 = words[3]
                    k = conv(words[4], float, 'improper force constant')
                    theteq = conv(words[5], float, 'improper equil. value')
                except IndexError:
                    raise CharmmFileError('Could not parse dihedrals.')
                # If we have a 7th column, that is the real psi0 (and the 6th
                # is just a dummy 0)
                try:
                    tmp = conv(words[6], float, 'improper equil. value')
                    theteq = tmp
                except IndexError:
                    pass # Do nothing
                # Improper types seem not to have the central atom defined in
                # the first place, so just have the key a fully sorted list. We
                # still depend on the PSF having properly ordered improper atoms
                key = tuple(sorted([type1, type2, type3, type4]))
                self.improper_types[key] = ImproperType(k, theteq)
                continue
            if section == 'CMAP':
                # This is the most complicated part, since cmap parameters span
                # many lines. We won't do much error catching here.
                words = line.split()
                try:
                    holder = [float(w) for w in words]
                    current_cmap_data.extend(holder)
                except ValueError:
                    # We assume this is a definition of a new CMAP, so
                    # terminate the last CMAP if applicable
                    if current_cmap is not None:
                        # We have a map to terminate
                        ty = CmapType(current_cmap_res, current_cmap_data)
                        self.cmap_types[current_cmap] = ty
                    try:
                        type1 = words[0]
                        type2 = words[1]
                        type3 = words[2]
                        type4 = words[3]
                        type5 = words[4]
                        type6 = words[5]
                        type7 = words[6]
                        type8 = words[7]
                        res = conv(words[8], int, 'CMAP resolution')
                    except IndexError:
                        raise CharmmFileError('Could not parse CMAP data.')
                    # order the torsions independently
                    k1 = [type1, type2, type3, type4]
                    k2 = [type4, type3, type2, type1]
                    key1 = min(k1, k2)
                    k1 = [type5, type6, type7, type8]
                    k2 = [type8, type7, type6, type5]
                    key2 = min(k1, k2)
                    current_cmap = tuple(key1 + key2)
                    current_cmap_res = res
                    current_cmap_data = []
                continue
            if section == 'NONBONDED' and not needs_blank:
                # Now get the nonbonded values
                words = line.split()
                try:
                    atype = words[0]
                    # 1st column is ignored
                    epsilon = conv(words[2], float, 'vdW epsilon term')
                    rmin = conv(words[3], float, 'vdW Rmin/2 term')
                except IndexError:
                    raise CharmmFileError('Could not parse nonbonded terms.')
                # See if we have 1-4 parameters
                try:
                    # 4th column is ignored
                    eps14 = conv(words[5], float, '1-4 vdW epsilon term')
                    rmin14 = conv(words[6], float, '1-4 vdW Rmin/2 term')
                except IndexError:
                    eps14 = rmin14 = None
                nonbonded_types[atype] = [epsilon, rmin, eps14, rmin14]
                continue
            if section == 'NBFIX':
                words = line.split()
                try:
                    at1 = words[0]
                    at2 = words[1]
                    emin = conv(words[2], float, 'NBFIX Emin')
                    rmin = conv(words[3], float, 'NBFIX Rmin')
                except IndexError:
                    raise CharmmFileError('Could not parse NBFIX terms.')
                self.nbfix_types[(min(at1, at2), max(at1, at2))] = (emin, rmin)
        # Now we're done. Load the nonbonded types into the relevant AtomType
        # instances. In order for this to work, all keys in nonbonded_types
        # must be in the self.atom_types_str dict. Raise a RuntimeError if this
        # is not satisfied
        try:
            for key in nonbonded_types:
                self.atom_types_str[key].set_lj_params(*nonbonded_types[key])
        except KeyError:
            raise RuntimeError('Atom type %s not present in AtomType list' %
                               key)
        if parameterset is not None: self.parametersets.append(parameterset)
        if own_handle: f.close()

    def read_topology_file(self, tfile):
        """
        Reads _only_ the atom type definitions from a topology file. This is
        unnecessary for versions 36 and later of the CHARMM force field.

        Parameters:
            - tfile (str) : Name of the CHARMM TOPology file to read

        Note: The CHARMM TOPology file is also called a Residue Topology File
        """
        conv = CharmmParameterSet._convert
        if isinstance(tfile, str):
            own_handle = True
            f = CharmmFile(tfile)
        else:
            own_handle = False
            f = tfile
        for line in f:
            line = line.strip()
            if line[:4] != 'MASS': continue
            words = line.split()
            try:
                idx = conv(words[1], int, 'atom type')
                name = words[2]
                mass = conv(words[3], float, 'atom mass')
            except IndexError:
                raise CharmmFileError('Could not parse MASS section of %s' %
                                      tfile)
            # The parameter file might or might not have an element name
            try:
                elem = words[4]
                if len(elem) == 2:
                    elem = elem[0] + elem[1].lower()
                atomic_number = AtomicNum[elem]
            except (IndexError, KeyError):
                # Figure it out from the mass
                atomic_number = AtomicNum[element_by_mass(mass)]
            atype = AtomType(name=name, number=idx, mass=mass,
                             atomic_number=atomic_number)
            self.atom_types_str[atype.name] = atype
            self.atom_types_int[atype.number] = atype
            self.atom_types_tuple[(atype.name, atype.number)] = atype
        if own_handle: f.close()

    def read_stream_file(self, sfile):
        """
        Reads RTF and PAR sections from a stream file and dispatches the
        sections to read_topology_file or read_parameter_file

        Parameters:
            - sfile (str or CharmmStreamFile) : Stream file to parse
        """
        if isinstance(sfile, CharmmStreamFile):
            f = sfile
        else:
            f = CharmmStreamFile(sfile)

        title, section = f.next_section()
        while title is not None and section is not None:
            words = title.lower().split()
            if words[1] == 'rtf':
                # This is a Residue Topology File section.
                self.read_topology_file(section)
            elif words[1].startswith('para'):
                # This is a Parameter file section
                self.read_parameter_file(section)
            title, section = f.next_section()

    def condense(self):
        """
        This function goes through each of the parameter type dicts and
        eliminates duplicate types. After calling this function, every unique
        bond, angle, dihedral, improper, or cmap type will pair with EVERY key
        in the type mapping dictionaries that points to the equivalent type

        Returns:
            - Returns the instance that is being condensed.

        Notes:
            The return value allows you to condense the types at construction
            time.

        Example:
        >>> params = CharmmParameterSet.load_set(pfile='charmm.prm').condense()
        """
        # First scan through all of the bond types
        self._condense_types(self.bond_types)
        self._condense_types(self.angle_types)
        self._condense_types(self.urey_bradley_types)
        self._condense_types(self.improper_types)
        self._condense_types(self.cmap_types)
        # Dihedrals have to be handled separately, since each key corresponds to
        # a list of (potentially multiterm) dihedral terms. Since all terms in a
        # multiterm dihedral have to have a DIFFERENT periodicity, we don't have
        # to condense _within_ a single list of torsions assigned to the same
        # key (they're guaranteed to be different)
        keylist = self.dihedral_types.keys()
        for i in range(len(keylist) - 1):
            key1 = keylist[i]
            for dihedral in self.dihedral_types[key1]:
                for j in range(i+1, len(keylist)):
                    key2 = keylist[j]
                    for jj, dihedral2 in enumerate(self.dihedral_types[key2]):
                        if dihedral2 == dihedral:
                            self.dihedral_types[key2][jj] = dihedral
        return self

    @staticmethod
    def _condense_types(typedict):
        """
        Loops through the given dict and condenses all types.

        Parameter:
            - typedict : Type dictionary to condense
        """
        keylist = typedict.keys()
        for i in range(len(keylist) - 1):
            key1 = keylist[i]
            for j in range(i+1, len(keylist)):
                key2 = keylist[j]
                if typedict[key1] == typedict[key2]:
                    typedict[key2] = typedict[key1]

# ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

def element_by_mass(mass):
    """ Determines what element the given atom is based on its mass """

    diff = mass
    best_guess = 'EP'

    for element in Element:
        if abs(Mass[element] - mass) < diff:
            best_guess = element
            diff = abs(Mass[element] - mass)

    return best_guess

