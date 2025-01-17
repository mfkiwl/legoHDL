# ------------------------------------------------------------------------------
# Project: legohdl
# Script: unit.py
# Author: Chase Ruskin
# Description:
#   This script describes the attributes and functions for a HDL design 
#   unit. 
#   
#   In verilog, this is called a 'module', and in VHDL, this is called an 
#   'entity'. Other design units include 'packages', which are available in both
#   VHDL and verilog. Units are used to help gather data on the type of HDL
#   dependency tree that will be generated for the current design.
# ------------------------------------------------------------------------------

import os, re
import logging as log
from enum import Enum

from .apparatus import Apparatus as apt
from .graph import Graph
from .map import Map


class Unit:


    class Design(Enum):
        ENTITY = 1,
        PACKAGE = 2
        pass


    class Language(Enum):
        VHDL = 1,
        VERILOG = 2
        pass


    #class variable storing the dependency tree
    Hierarchy = Graph()

    #multi-level class container to store all entities
    Jar = Map()

    #2-level class container
    Bottle = Map()


    def __init__(self, name, filepath, dsgn, lang_obj):
        '''
        Create a design unit object.

        Parameters:
            name (str): the unit's name
            filepath (str): the file where the design unit was found
            dsgn (Design): the design type
            lang_obj (Language): the Language object this unit belongs to (also carries a Block)
        Returns:
            None   
        '''
        self._filepath = apt.fs(filepath)
        self._lang_obj = lang_obj
        self.setAbout(lang_obj.getAbout())

        self._libs = []
        self._pkgs = []

        _,ext = os.path.splitext(self.getFile())
        ext = '*'+ext.lower()
        if(ext in apt.VHDL_CODE):
            self._language = self.Language.VHDL
        elif(ext in apt.VERILOG_CODE):
            self._language = self.Language.VERILOG
            #automatically given verilog modules ieee library in case
            # for generating auto packge file from verilog modules
            self._libs = ['ieee']
            self._pkgs = ['ieee.std_logic_1164.all']

        self._dsgn = dsgn
        
        self._M = lang_obj.getOwner().M()
        self._L = lang_obj.getOwner().L()
        self._N = lang_obj.getOwner().N()
        self._V = lang_obj.getOwner().V()
        self._E = name

        self._checked = False
        self._config = None
        self._config_modes = Map()

        #create an empty interface
        self._interface = Interface(name=self.E(), library=self.L(), def_lang=self.getLang())

        # :note: allowing packages to print their information like a component can

        # by default, look at the entities available in download section? or look at entities
        # in installation section.

        # add to Jar
        #create new vendor level if vendor DNE
        if(self.M().lower() not in self.Jar.keys()):
            self.Jar[self.M()] = Map()
        #create new library level if libray DNE
        if(self.L().lower() not in self.Jar[self.M()].keys()):
             self.Jar[self.M()][self.L()] = Map()
        #create new block name level if name DNE
        if(self.N().lower() not in self.Jar[self.M()][self.L()].keys()):
             self.Jar[self.M()][self.L()][self.N()] = Map()

        #store entity at this nested level
        if(self.E().lower() not in self.Jar[self.M()][self.L()][self.N()].keys()):
            self.Jar[self.M()][self.L()][self.N()][self.E()] = self
        else:
            log.error("An entity at this level already exists as: "+self.E()+"!")
            print("Already:")
            print(self.Jar[self.M()][self.L()][self.N()][self.E()])
            print("Tries:")
            print(self)
            exit(1)

        # add to Bottle - a 2-level Map with values as lists effectively binning units together
        #create new library level if libray DNE
        if(self.L().lower() not in self.Bottle.keys()):
             self.Bottle[self.L()] = Map()
        #create new unit level if unit DNE
        if(self.E().lower() not in self.Bottle[self.L()].keys()):
             self.Bottle[self.L()][self.E()] = []
        #add entity to a list
        self.Bottle[self.L()][self.E()] += [self]
        pass


    def getLanguageFile(self):
        '''Returns _lang_obj (Language).'''
        return self._lang_obj


    def linkLibs(self, libs, pkgs):
        '''
        Link relevant library and package files (mainly for VHDL entities).

        Parameters:
            libs ([str]): library names
            pkgs ([str]): package names with respective '.' characters
        Returns:
            None
        '''
        self._libs += libs
        self._pkgs += pkgs
        pass


    def getLibs(self, lower_case=False):
        '''
        Returns the list of linked libraries to this entity.

        Parameters:
            lower_case (bool): determine if to convert all libraries to lower case
        Returns:
            _libs ([str]): list of linked libraries
        '''
        if(lower_case == True):
            tmp = []
            #cast to all lower-case for evaluation purposes within VHDL
            for l in self._libs:
                tmp += [l.lower()]
            return tmp
        #return case-sensitive library names
        return self._libs


    def getPkgs(self):
        '''Returns list of packages as strings.'''
        return self._pkgs


    def decodePkgs(self):
        '''
        Returns the list of Unit objects that are design package types linked to this entity.

        Adds connections to all found package objects in the hierarchy graph. Dynamically
        creates _dsgn_pkgs attr to avoid doubling connections.

        Parameters:
            None
        Returns:
            _dsgn_pkgs ([Unit]): list of referenced Unit package objects
        '''
        if(hasattr(self, "_dsgn_pkgs")):
            return self._dsgn_pkgs

        dsgn_pkgs = []
        #iterate through each package string and try to find its object.
        for pkg in self._pkgs:
            pkg_parts = pkg.split('.')
            lib_name = pkg_parts[0]
            #convert library name to current if work is being used
            if(lib_name.lower() == 'work'):
                lib_name = self.L()
            pkg_name = pkg_parts[1]
            
            dsgn_pkg = Unit.ICR(pkg_name, lang=self.getLang(), lib=lib_name)
            
            #add the package object if its been found
            if(dsgn_pkg != None):
                dsgn_pkgs += [dsgn_pkg] 
                #add connection in the graph
                self.addReq(dsgn_pkg)
                pass
        #print("DESIGN PACKAGES:",dsgn_pkgs)
        return dsgn_pkgs


    def linkArch(self, arch):
        '''adds arch (str) to list of _archs ([str]) attr.'''
        if(hasattr(self, '_archs') == False):
            self._archs = []
        self._archs += [arch]
        pass


    def setConfig(self, config):
        '''Sets _config (str) attr.'''
        self._config = config
        pass


    def linkConfig(self, arch, inst_name, search_for, replace_with):
        '''
        Sets a new (Map) for the given unit.
        
        Parameters:
            arch (str): architecture to apply configuration to
            inst_name (str): instance name to look for inside architecture
            search_for (str): new identifier to find in the architecture definition
            replace_with (str): the real entity name to use in the architecture definition
        Returns:
            None
        '''
        #make the architecture map
        if(arch.lower() not in self._config_modes.keys()):
            self._config_modes[arch] = Map()
        #know what identifier to find
        if(search_for.lower() not in self._config_modes[arch].keys()):
            self._config_modes[arch][search_for] = Map()
        #know what instances fall for this
        if(inst_name.lower() not in self._config_modes[arch][search_for].keys()):
            self._config_modes[arch][search_for][inst_name] = replace_with
        pass
        #print(self._config_modes)


    def setChecked(self, c):
        '''
        Sets _checked attr to `c`. 
        
        If True, then the unit object self will be added to the graph as a vertex. 
        If False, then the unit object self will be removed from the graph.

        Parameters:
            c (bool): determine if unit has been checked (data completed/decoded)
        Returns:
            None
        '''
        #add to hierarchy if complete
        if(c == True and not self.isChecked()):
            self.Hierarchy.addVertex(self)
        #remove from hierarchy to restart graph
        if(c == False and self.isChecked()):
            self.Hierarchy.removeVertex(self)
        self._checked = c
        pass


    @classmethod
    def resetHierarchy(cls):
        '''
        Unchecks all units, removes _dsgn_pkgs attr, and removes all vertices from
        the Hierarchy graph.

        Parameters:
            None
        Returns:
            None
        '''
        for u in cls.Hierarchy.getVertices():
            u.setChecked(False)
            #remove dynamic design packages attr
            if(hasattr(u, "_dsgn_pkgs")):
                delattr(u, "_dsgn_pkgs")
            pass
        Unit.Hierarchy.clear()
        pass


    @classmethod
    def resetJar(cls):
        '''Clears Jar (Map) and Bottle (Map) class attrs.'''
        cls.Jar = Map()
        cls.Bottle = Map()
        pass

    
    def setAbout(self, a_txt):
        '''Sets the _about_txt (str) attr.'''
        self._about_txt = a_txt
    

    def isChecked(self):
        '''Returns _checked (bool).'''
        return self._checked


    def readArchitectures(self):
        '''
        Formats the architectures into a string to be printed.

        Parameters:
            None
        Returns:
            (str): architecture text to print to console
        '''
        if(len(self.getArchitectures())):
            txt = "Defined architectures for "+self.getFull()+":\n"
            for arc in self.getArchitectures():
                txt = txt+'\t'+arc+'\n'
        else:
            txt = "No architectures are defined for "+self.getFull()+"!\n"
        return txt

    
    def readReqs(self, upstream=False):
        '''
        Formats the required units into a string to be printed.
        
        Parameters:
            upstream (bool): determine if to show connections below or above unit
        Returns:
            (str): dependency text to print to console
        '''
        txt = 'Instantiates:\n'
        if(upstream == True):
            txt = 'Instantiated within:\n'
        #check if any edges exist
        if(len(self.getReqs(upstream))):
            #iterate through the neighbors/edges of the graph
            txt = txt + apt.listToGrid(self.getReqs(upstream, returnnames=True), min_space=4, offset='\t')
        else:
            txt = txt+'\tN/A'
        return txt


    def readAbout(self):
        '''Returns the already formatted _about_txt (str) attr to be printed.'''
        return self._about_txt


    def getLang(self):
        '''Returns what coding language the unit is in (Unit.Language).'''
        return self._language


    def getArchitectures(self):
        '''Returns list of identified architectures. If empty, returns ['rtl'].'''
        if(hasattr(self, "_archs")):
            return self._archs
        else:
            return ['rtl']


    def isPkg(self):
        '''Returns if the unit is PACKAGE design type.'''
        return (self._dsgn == self.Design.PACKAGE)

    
    def getDesign(self):
        '''Returns the unit's design type (Unit.Design).'''
        return self._dsgn


    def getFile(self):
        '''Return's the filepath where this unit was identified.'''
        return self._filepath
    

    def M(self):
        return self._M


    def L(self):
        return self._L


    def N(self):
        return self._N


    def E(self):
        return self._E


    @classmethod
    def jarExists(cls, M, L, N):
        '''Returns True if the Jar has M/L/N key levels.'''
        if(M.lower() in cls.Jar.keys()):
            if(L.lower() in cls.Jar[M].keys()):
                return (N.lower() in cls.Jar[M][L].keys())
        return False


    @classmethod
    def ICR(cls, dsgn_name, lang, lib=None, ports=[], gens=[]):
        '''
        Intelligently select the entity given the unit name and library (if exists). 
        
        Also uses intelligent component recognition to try and decide between 
        what entity is trying to be used. Updating the _reqs for a unit must be
        done outside the scope of this method.

        Returns None if the unit is not able to be identified.

        Parameters:
            u (str): entity name
            l (str): library name
            ports ([str]): list of ports that were instantiated (all lower-case)
            gens ([str]): list of generics that were instantiated (all lower-case)
        Returns:
            (Unit): unit object from the Jar
        '''
        #toggle 'verbose' to print scores to console
        verbose = False
        #[1.] create a list of all potential design units
        potentials = []
        #if no library, get list of all units
        if(lib == '' or lib == None):
            for ul in list(cls.Bottle.values()):
                #print("searching for:",dsgn_name,"/ units:",list(ul.keys()))
                #could be any design that falls under this unit name
                if(dsgn_name.lower() in list(ul.keys())):
                    potentials += ul[dsgn_name]

        #a library was given, only pull list from that specific library.unit slot
        elif(lib.lower() in cls.Bottle.keys() and dsgn_name.lower() in cls.Bottle[lib].keys()):
            potentials = cls.Bottle[lib][dsgn_name]
        
        #filter the units to only include original language units if mixed language is OFF
        if(apt.getMixedLanguage() == False):
            potentials = list(filter(lambda a: a.getLang() == lang, potentials))

        #[2.] determine if ICR needs to be performed or unit is obviously only one
        dsgn_unit = None
        #the choice is clear; only one option available to be this design unit
        if(len(potentials) == 1):
            #log.info("Instantiating "+potentials[0].getTitle())
            return potentials[0]
        #no unit found to match this naming in the jar
        if(len(potentials) == 0):
            return dsgn_unit

        #[3.] perform intelligent component recognition by comparing ports and generics
        if(verbose):
            log.info("Performing Intelligent Component Recognition for "+dsgn_name+"...")
        #initialize scores for each potential component
        scores = [0]*len(potentials)

        #iterate through every potential component
        for i in range(len(potentials)):

            #[3a.] get the real ports for this challenging/potential component
            challenged_ports = list(potentials[i].getInterface().getPorts().values())
            #can only compare lengths if positional arguments were used
            if(len(ports) and ports.count('?')):
                scores[i] = len(ports) - abs(len(challenged_ports) - len(ports))
            #compare the instance ports with the real ports
            else:
                for c_port in challenged_ports:
                    #check if the true port is instantiated
                    if(c_port.getName().lower() in ports):
                        scores[i] += 1
                    #this port was already previously initialized and can be ignored
                    elif(c_port.isInitialized()):
                        continue
                    #this port was not instantiated, yet it MUST since its an input
                    elif(c_port.getRoute() == Port.Route.IN):
                        #automatically set score to 0 (DQ'ed)
                        scores[i] = 0
                        break
                pass

            #[3b.] get the real generics for this challenging/potential component
            challenged_gens = list(potentials[i].getInterface().getGenerics().values())
            #can only compare lengths if positional arguments were used
            if(len(gens) and gens.count('?')):
                scores[i] = len(gens) - abs(len(challenged_gens) - len(gens))
            #compare the instance generics with the real generics
            else:
                for c_gen in challenged_gens:
                    #check if the true generic is instantiated
                    if(c_gen.getName().lower() in gens):
                        scores[i] += 1
                    #this generic was already previously initialized and can be ignored
                    elif(c_gen.isInitialized()):
                        continue
                    #this generic was not initialized, yet it MUST be so its DQ'ed (score to 0)
                    else:
                        scores[i] = 0
                        break
                pass

            pass

        #[4.] pick the highest score
        if(verbose):
            print('--- ICR SCORE REPORT ---')
        i = 0
        for j in range(len(scores)):
            #calculate percentage based on computed score and number of possible points to get
            percentage = scores[j]
            if(len(ports)+len(gens) > 0):
                percentage = round(scores[j]/(len(ports)+len(gens))*100,2)
            #format report to the console
            if(verbose):
                print('{:<1}'.format(' '),'{:<40}'.format(potentials[j].getTitle()),'{:<4}'.format('='),'{:<5}'.format(percentage),"%")
            #select index with maximum score
            if(scores[j] > scores[i]):
                i = j
            pass

        #select design unit at index with maximum score
        dsgn_unit = potentials[i]
        if(verbose):
            log.info("Intelligently selected "+dsgn_unit.getTitle())
        #return the selected design unit
        return dsgn_unit


    def getFull(self):
        return self.L()+"."+self.E()


    def getTitle(self):
        m = ''
        if(self.M() != ''):
            m = self.M()+'.'
        return m+self.L()+'.'+self.N()+apt.ENTITY_DELIM+self.E()


    def getConfig(self, arch=None):
        '''Returns the _config (str) attr when arch is None. If an arch (str) is
        specified, return the 2-level (Map) for that architecture's configuration.'''
        if(arch == None):
            return self._config
        elif(arch.lower() in self._config_modes.keys()):
            return self._config_modes[arch]
        else:
            return Map()


    def getInterface(self):
        return self._interface


    def isTb(self):
        '''Returns true if the design is an entity and has zero ports.'''
        #testbench must have zero ports as an entity unit
        return (self._dsgn == self.Design.ENTITY and \
            len(self.getInterface().getPorts()) == 0)


    def addReq(self, req):
        '''
        Add a unit as a requirement for this object.

        Parameters:
            req (Unit): unit object that is used by unit calling the method
        Returns:
            None
        '''
        if(req == None):
            return
        #add new edge
        self.Hierarchy.addEdge(self, req)
        pass
    

    def getReqs(self, upstream=False, returnnames=False):
        '''
        Returns a list of Unit objects directly required for this unit.

        Parameters:
            upstream (bool): determine if to return units that use this design
            returnnames (bool): determine if to return the string names for each unit
        Returns:
            ([Unit]) or ([str]): list of required Units (or names)
        '''
        edges = self.Hierarchy.getNeighbors(self, upstream)
        reqs = []
        if(returnnames):
            for e in edges:
                reqs += [e.getTitle()]
        else:
            reqs = edges
        return reqs


    # uncomment to use for debugging
    # def __str__(self):
    #     reqs = '\n'
    #     for dep in self.getReqs():
    #         reqs = reqs + '-'+dep.M()+'.'+dep.L()+'.'+dep.N()+':'+dep.E()+" "
    #         reqs = reqs + hex(id(dep)) + "\n"
    #     return f'''
    #     ID: {hex(id(self))}
    #     Completed? {self.isChecked()}
    #     full name: {self.getTitle()}
    #     file: {self.getFile()}
    #     dsgn: {self.getDesign()}
    #     lang: {self.getLang()}
    #     arch: {self.getArchitectures()}
    #     tb?   {self.isTb()}
    #     conf? {self.getConfig()}
    #     reqs: {reqs}
    #     '''


    pass


class Signal:


    def __init__(self, lang, name, dtype, value):
        '''
        Construct a Signal object.

        Parameters:
            lang (Unit.Language): natural coding language
            name (str): port identifier
            dtype ([str]): list of tokens that make up the datatype
            value ([str]): list of tokens that make up the initial value
        Returns:
            None
        '''
        self._lang = lang
        self._name = name
        self._dtype = dtype
        self._value = value
        pass

    def writeConnection(self, lang, spaces=1, end=';', name='*'):
        '''
        Create compatible code for signal/wire declarations. Includes ';' at the
        end.

        Parameters:
            lang (Unit.Language): VHDL or VERILOG coding format
            spaces (int): number of spaces between identifier and keyword/token
            end (str): final character
            name (str): the name of the connection
        Returns:
            c_txt (str): compatible line of code to be printed
        '''
        c_txt = ''
        #write VHDL-style code
        if(lang == Unit.Language.VHDL):
            #write connection type
            if(isinstance(self, Generic)):
                c_txt = 'constant '
            else:
                c_txt = 'signal '
            #append identifier
            c_txt = c_txt + self.getName(mod=name)+(spaces*' ')+': '
            #append datatype
            c_txt = c_txt + self.castDatatype(lang)
            #append initial value
            if(len(self.getValue())):
                c_txt = c_txt + ' := ' + self.getValue()
            pass
        #write VERILOG-style code
        elif(lang == Unit.Language.VERILOG):
            if(isinstance(self, Generic)):
                c_txt = 'parameter '
            #write the datatype
            c_txt = self.castDatatype(lang, keep_net=False) 
            #append the name
            c_txt = c_txt + " " + self.getName(mod=name)
            #append the initial value
            if(len(self.getValue())):
                c_txt = c_txt + ' = ' + self.getValue()
            pass
        #add finishing ';' 
        return c_txt + ';'


    def writeMapping(self, lang, spaces=0, fit=False, end=',', name='*'):
        '''
        Create the compatible code for mapping a given signal.

        Parameters:
            lang (Unit.Language): VHDL or VERILOG coding format
            spaces (int): number of spaces required between name and '=>'
            end (str): final character
        Returns:
            m_txt (str): compatible line of code to be printed
        '''
        r_space = 1 if(fit) else spaces

        if(lang == Unit.Language.VHDL):
            m_txt = "    "+self.getName()+(spaces*' ')+"=>"+(r_space*' ')+self.getName(mod=name)
        elif(lang == Unit.Language.VERILOG):
            m_txt = "    ."+self.getName()+(spaces*' ')+"("+self.getName(mod=name)+")"

        return m_txt+end


    def castDatatype(self, lang, keep_net=False):
        '''
        Returns converted datatype. Won't perform any conversions if `lang` is
        the original language for the datatype.

        Converts _dtype ([str]) to (str).
        
        Parameters:
            lang (Unit.Language): the coding language to cast to
            keep_net (bool): determine if to keep original verilog net or convert all to wire
        Returns:
            (str): proper data type for the respective coding language
        '''
        #return the true stored datatype if the the original language is requested
        if(lang == self.getLang()):
            dt = apt.listToStr(self.getDatatype())
            if(lang == Unit.Language.VHDL):
                fc = dt.find(',(')
                if(fc > -1):
                    #drop that comma
                    dt = dt[:fc] + dt[fc+1:]
                    #properly format string repr
                    dt = dt.replace('(,', '(')
                    dt = dt.replace(',)', ')')
                    dt = dt.replace(',', ' ')
                pass
            elif(lang == Unit.Language.VERILOG):
                #properly format string repr
                dt = dt.replace(',[', ' [')
                dt = dt.replace(',', '')
                #print("new",dt)
                if(dt.startswith('reg')):
                    #remove reg from any signals and convert to wire
                    if(keep_net == False):
                        dt = dt[len('reg'):]
                        dt = 'wire'+dt
            return dt
        #cast from verilog to vhdl
        elif(lang == Unit.Language.VHDL):
            if('integer' in self.getDatatype()):
                return 'integer'

            dtype = "std_logic"
            if(hasattr(self, "_bus_width")):
                dtype = dtype+"_vector("+self._bus_width[0]+" downto "+self._bus_width[1]+")"
            return dtype
        #cast from vhdl to verilog
        elif(lang == Unit.Language.VERILOG):
            dtype = ''
            a = 0
            b = 1
            for word in self.getDatatype():
                #fix writing from LSB->MSB to MSB->LSB (swap bus width positions)
                if(word.lower() == 'to'):
                    a = 1
                    b = 0
                    break
            if(hasattr(self, "_bus_width")):
                dtype = "["+self._bus_width[a]+":"+self._bus_width[b]+"]"
                
            #skip forcing wire declaration if keep_net is True
            if(isinstance(self, Generic)):
                dtype = ('parameter '+dtype).strip()
            elif(keep_net == True):
                pass
            #add wire declaration
            elif(len(dtype)):
                dtype = 'wire '+dtype
            else:
                dtype = 'wire'

            return dtype


    def getName(self, mod=None):
        '''Returns the identifier (str). Use mod (str) to modify the name.'''
        if(mod == None):
            return self._name
        return mod.replace('*', self._name)

    
    def getLang(self):
        '''Returns the original coding language (Unit.Language).'''
        return self._lang

    
    def getDatatype(self):
        '''Returns the list of tokens that make up the datatype ([str]).'''
        return self._dtype


    def isInitialized(self):
        '''Returns (bool) if connection has a default value declared.'''
        return bool(len(self.getValue()) > 0)


    def getValue(self):
        '''Returns the list of tokens that make up the initial value (str).'''
        return apt.listToStr(self._value, delim='')


    pass


class Generic(Signal):


    def __init__(self, lang, name, dtype, value):
        super().__init__(lang, name, dtype, value)
        pass
        

    def writeDeclaration(self, lang, spaces=1):
        '''
        Create the compatible code for declaring a constant from the given generic.

        Parameters:
            lang (Unit.Language): VHDL or VERILOG compatible code
            spaces (int): number of spaces required between name and ':'
        Returns:
            c_txt (str): compatible line of code to be printed
        '''
        #omit the keyword 'constant'
        d_txt = self.writeConnection(lang, spaces)

        if(lang == Unit.Language.VHDL):
            d_txt = d_txt[len('constant '):]

        return d_txt  


    pass


class Port(Signal):


    class Route(Enum):
        IN = 1,
        OUT = 2,
        INOUT = 3,
        BUFFER = 4,
        LINKAGE = 5,
        OTHER = -1
        pass


    def __init__(self, lang, name, mode, dtype, value, bus_width=('','')):
        '''
        Construct a port object.

        Parameters:
            lang (Unit.Language): natural coding language
            name (str): port identifier
            mode (str): direction
            dtype ([str]): list of tokens that make up the datatype
            value ([str]): initial value
            bus_width ((str, str)): the lower and upper (exclusive) ends of a bus
        Returns:
            None
        '''
        super().__init__(lang, name, dtype, value)

        #store the port's direction word
        self._mode = mode

        #store the port's direction data (works for both verilog and vhdl)
        mode = mode.lower()
        if(mode == 'inout'):
            self._route = self.Route.INOUT
        elif(mode.startswith('in')):
            self._route = self.Route.IN
        elif(mode.startswith('out')):
            self._route = self.Route.OUT
        else:
            self._route = self.Route.OTHER

        #store the port's bit width
        if(bus_width != ('','')):
            self._bus_width = bus_width
        pass


    def writeDeclaration(self, lang, spaces=1, fit=True):
        if(lang == Unit.Language.VHDL):
            #gather the basic connection writing
            d_txt = self.writeConnection(lang, spaces)
            #remove the 'signal' keyword
            d_txt = d_txt[len('signal '):]
            #add-in the mode
            i = d_txt.find(':')
            d_txt = d_txt[:i+1] + ' ' + self.castRoute(lang, even=fit) + d_txt[i+1:]
            pass
        #write VERILOG-style code
        elif(lang == Unit.Language.VERILOG):
            #add-in the mode to the beginning
            d_txt = self.castRoute(lang, even=fit)
            #write the datatype
            d_txt = d_txt + ' ' + self.castDatatype(lang, keep_net=True) 
            #append the name
            d_txt = d_txt + ' ' + self.getName()
            #append the initial value
            if(len(self.getValue())):
                d_txt = d_txt + ' = ' + self.getValue()
            
            d_txt = d_txt + ','
            pass
        
        return d_txt


    def getRoute(self):
        '''Returns the port's route (Port.Route).'''
        return self._route


    def getMode(self):
        '''Returns the port's mode (str).'''
        return self._mode


    def castRoute(self, lang, even=True):
        '''Converts _route (Port.Route) to (str). `even` will ensure even spaces for
        all directions.'''
        spaces = 0
        if(even and self.getRoute() == self.Route.IN):
            spaces = 1
        if(lang == Unit.Language.VERILOG):
            rt = str(self.getRoute().name).lower()+'put'+(spaces*' ')
        elif(lang == Unit.Language.VHDL):
            rt = str(self.getRoute().name).lower()+(spaces*' ')
        return rt


    pass


class Interface:
    'An interface has generics and port signals. An entity will have an interface.'


    def __init__(self, name, library, def_lang):
        self._name = name
        self._library = library
        self._default_lang = def_lang

        self._ports = {}
        self._generics = {}
        pass


    def addConnection(self, name, mode, dtype, value, isPort, bounds=('','')):
        '''
        Adds an interface connection.

        Parameters:
            name (str): signal identifier
            mode (str): port direction (ignored if isPort is False)
            dtype ([str]): tokens for connection's datatype
            value ([str]): tokens for connection's initial value
            isPort (bool): determine if to store as port or generic
            bounds ((str,str)): the L and R bounds of the specified port
        Returns:
            None
        '''
        if(isPort):
            self._ports[name] = Port(self._default_lang, name, mode, dtype, value, bus_width=bounds)
        else:
            self._generics[name] = Generic(self._default_lang, name, dtype, value)
        
        pass


    def writeConnections(self, form=None, align=True, g_name=None, p_name=None):
        '''
        Write the necessary constants (from generics) and signals (from ports)
        for the given entity.

        Parameters:
            form (Unit.Language): VHDL or VERILOG compatible code style
            align (bool): determine if names should be all equally spaced
            g_name (str): the modified generics name pattern
            p_name (str): the modified ports name pattern
        Returns:
            connect_txt (str): compatible code to be printed
        '''
        #default selection is to write in original coding language
        if(form == None):
            form = self._default_lang

        connect_txt = ''
        #default number of spaces when not aligning
        spaces = 1 
        #do not write anything if no interface!
        if(len(self.getGenerics()) == 0 and len(self.getPorts()) == 0):
                return connect_txt
        
        #determine farthest reach constant name
        g_pairs = []
        g_ids = list(self.getGenerics().values())
        for i in range(len(g_ids)):
            g_pairs += [[g_ids[i].getName(), g_ids[i].getName(mod=g_name)]]
            g_ids[i] = g_ids[i].getName(mod=g_name)
            
        farthest = apt.computeLongestWord(g_ids)
                
        #write constants
        for g in self.getGenerics().values():
            if(align):
                spaces = farthest - len(g.getName(mod=g_name)) + 1
            connect_txt = connect_txt + g.writeConnection(form, spaces, name=g_name) +'\n'
        
        #add new-line between generics and signals
        if(len(self.getGenerics())):
            connect_txt = connect_txt + '\n'

        #determine farthest reach signal name
        p_ids = list(self.getPorts().values())
        for i in range(len(p_ids)):
            p_ids[i] = p_ids[i].getName(mod=p_name)
        farthest = apt.computeLongestWord(p_ids)
        
        #write signals
        signal_txt = ''
        for p in self.getPorts().values():
            if(align):
                spaces = farthest - len(p.getName(mod=p_name)) + 1
            signal_txt = signal_txt + p.writeConnection(form, spaces, name=p_name) +'\n'

        #replace all old generic identifiers with new modifiers
        for pair in g_pairs:
            #replace pairs only that have complete word
            expression = re.compile('\\b'+pair[0]+'\\b', re.IGNORECASE)
            #rewrite the connection text
            signal_txt = expression.sub(pair[1], signal_txt)
            pass

        return connect_txt + signal_txt
    

    def writeInstance(self, lang=None, entity_lib=None, inst_name='uX', fit=True, \
        hang_end=True, maps_on_newline=False, alignment=1, g_name=None, p_name=None):
        '''
        Write the correct compatible code for an instantiation of the given
        entity.

        Parameters:
            lang (Unit.Language): VHDL or VERILOG compatible code style
            entity_lib (str): if VHDL and not None, use entity instantiation 
            inst_name (str): the name to give the instance
            fit (bool): determine if names should be all equally spaced
            hand_end (bool): true if ) deserves its own line
            maps_on_newline (bool): determine if start of a mapping deserves a newline
            alignment (int): determine number of additional spaces
            g_name (str): the modified generics name pattern
            p_name (str): the modified ports name pattern
        Returns:
            m_txt (str): the compatible code to be printed
        '''
        #default selection is to write in original coding language
        if(lang == None):
            lang = self._default_lang
        #default name if none given
        if(inst_name == None):
            inst_name = 'uX'

        m_txt = 'Empty interface!\n'
        #default number of spaces when not aligning
        spaces = alignment
        #do not write anything if no interface!
        if(len(self.getGenerics()) == 0 and len(self.getPorts()) == 0):
                return m_txt
        
        #write VHDL-style code
        if(lang == Unit.Language.VHDL):
            #write the instance name and entity name
            m_txt = inst_name + " : "+self.getName()+" "
            #re-assign beginning of mapping to be a pure entity instance
            if(entity_lib != None):
                m_txt = inst_name+" : entity "+entity_lib+"."+self.getName()+" "
            #place mapping on new line
            if(maps_on_newline):
                 m_txt =  m_txt + "\n"

            #generics to map
            if(len(self.getGenerics())):
                m_txt = m_txt + "generic map(\n"

                farthest = apt.computeLongestWord(self.getGenerics().keys())
                #iterate through every generic
                gens = list(self.getGenerics().values())
                for g in gens:
                    #compute number of spaces for this generic instance mapping
                    if(fit):
                        spaces = farthest - len(g.getName()) + alignment

                    #add generic instance mapping
                    m_txt = m_txt + g.writeMapping(lang, spaces, fit, name=g_name)
                    
                    #add newline
                    if(g == gens[-1]):
                        #trim final ','
                        m_txt = m_txt[:len(m_txt)-1]
                        #don't add \n to last map if hang_end
                        if(hang_end == False):
                            continue
                    #append a newline
                    m_txt = m_txt + "\n"
                    pass
                #add necessary closing
                m_txt = m_txt + ") "
                pass

            #ports to map
            if(len(self.getPorts())):
                #add new line if generics were written
                if(len(self.getGenerics()) and hang_end == False):
                    m_txt = m_txt + "\n"

                m_txt = m_txt + "port map(\n"

                farthest = apt.computeLongestWord(self.getPorts().keys())

                #iterate through every port
                ports = list(self.getPorts().values())
                for p in ports:
                    #compute number of spaces needed for this port instance mapping
                    if(fit):
                        spaces = farthest - len(p.getName()) + alignment
                    #add port instance mapping
                    m_txt = m_txt + p.writeMapping(lang, spaces, fit, name=p_name)
                    #add newline
                    if(p == ports[-1]):
                        #trim final ','
                        m_txt = m_txt[:len(m_txt)-1]
                        #don't add \n to last map if hang_end
                        if(hang_end == False):
                            continue
                    #append to the entire text
                    m_txt = m_txt + "\n"
                    pass
                #add necessary closing
                m_txt = m_txt + ")"
                pass

            #add final ';'
            m_txt = m_txt + ";\n"
            pass
        #write VERILOG-style code
        elif(lang == Unit.Language.VERILOG):
            #start with entity's identifier
            m_txt = self.getName()
            #write out parameter section
            if(len(self.getGenerics())):
                #compute longest identifier name for auto-fit
                farthest = apt.computeLongestWord(self.getGenerics().keys())
                #begin parameter mapping
                m_txt = m_txt + ' #(\n'

                #iterate through every parameter
                params = list(self.getGenerics().values())
                for p in params:
                    #compute number of spaces for this parameter
                    if(fit):
                        spaces = farthest - len(p.getName()) + alignment
                    #add parameter instance mapping
                    m_txt = m_txt + p.writeMapping(lang, spaces, fit, name=g_name)
                    #don't add ',\n' if on last generic
                    if(p == params[-1]): 
                        #trim final ','
                        m_txt = m_txt[:len(m_txt)-1]
                        #enter newlines
                        if(hang_end == True):
                            m_txt = m_txt + "\n) "
                        else:
                            m_txt = m_txt + ")\n"
                        #add instance name
                        m_txt = m_txt + inst_name
                    else:
                        m_txt = m_txt + '\n'
                    pass
                pass
            #no generics...so begin with instance name
            else:
                m_txt = m_txt + ' ' + inst_name

            #write out port section
            if(len(self.getPorts())):
                m_txt = m_txt + ' (\n'
                #compute farthest identifier word length
                farthest = apt.computeLongestWord(self.getPorts().keys())

                #iterate through every port
                ports = list(self.getPorts().values())
                for p in ports:
                    #compute number of spaces for even fit for port declaration
                    if(fit):
                        spaces = farthest - len(p.getName()) + alignment
                    #add port declaration
                    m_txt = m_txt + p.writeMapping(lang, spaces, fit, name=p_name)
                    #don't add ,\n if on last port
                    if(p == ports[-1]):
                        #trim final ','
                        m_txt = m_txt[:len(m_txt)-1]
                        #add newline if hanging end
                        if(hang_end == True):
                            m_txt = m_txt + "\n"
                        #add closing ')'
                        m_txt = m_txt + ")"
                    else:
                        m_txt = m_txt + '\n'
                    pass
                pass

            #add final ';'
            m_txt = m_txt + ';'
            pass
        #print(m_txt)
        return m_txt

    
    def writeDeclaration(self, form, align=True, hang_end=True, tabs=0):
        '''
        Write the correct compatible code for a component declaration of the given
        entity. For VERILOG, it will return the module declaration statement.

        Parameters:
            form (Unit.Language): VHDL or VERILOG compatible code style
            align (bool): determine if identifiers should be all equally spaced
            hand_end (bool): true if ) deserves its own line
            tabs (int): number of tabs to begin on (used for auto-packaging)
        Returns:
            comp_txt (str): the compatible code to be printed
        '''
        #default selection is to write in original coding language
        if(form == None):
            form = self._default_lang

        #define tab character to be 4 spaces
        T = ' '*4 
        #store running component text
        comp_txt = ''
        #default number of spaces when not aligning
        spaces = 1
        #write VHDL-style code
        if(form == Unit.Language.VHDL):
            comp_txt = (tabs*T)+'component ' + self.getName() + '\n'
            #write generics
            gens = list(self.getGenerics().values())
            if(len(gens)):
                farthest = apt.computeLongestWord(self.getGenerics().keys())
                comp_txt  = comp_txt + (tabs*T)+'generic(' + '\n'
                #write every generic
                for gen in gens:
                    #determine number of spaces for this declaration
                    if(align):
                        spaces = farthest - len(gen.getName()) + 1

                    comp_txt = comp_txt + ((tabs+1)*T) + gen.writeDeclaration(form, spaces=spaces)
                    #trim off final ';'
                    if(gen == gens[-1]):
                        comp_txt = comp_txt[:len(comp_txt)-1]
                    #enter newline
                    if(gen != gens[-1]):
                        comp_txt = comp_txt + '\n'
                    elif(hang_end):
                         comp_txt = comp_txt + '\n'
                    pass
                #add final generic closing token
                comp_txt = comp_txt + (tabs*T*int(hang_end)) + ');\n'
                pass
            #write ports
            ports = list(self.getPorts().values())
            if(len(ports)):
                farthest = apt.computeLongestWord(self.getPorts().keys())
                comp_txt = comp_txt + (tabs*T)+'port(' + '\n'
                #write every port
                for port in ports:
                    #determine number of spaces for this declaration
                    if(align):
                        spaces = farthest - len(port.getName()) + 1
                    #add port declaration
                    comp_txt = comp_txt + ((tabs+1)*T) + port.writeDeclaration(form, spaces, align)
                    #trim off final ';'
                    if(port == ports[-1]):
                        comp_txt = comp_txt[:len(comp_txt)-1]
                    #enter newlines
                    if(port != ports[-1]):
                        comp_txt = comp_txt + '\n'
                    elif(hang_end):
                        comp_txt = comp_txt + '\n'
                    pass
                #add final port closing token
                comp_txt = comp_txt + (tabs*T*int(hang_end)) + ');\n'
            #add final closing segment
            comp_txt = comp_txt + (tabs*T)+'end component;'
            pass
        #write VERILOG-style code
        elif(form == Unit.Language.VERILOG):
            comp_txt = 'module '+self.getName()

            #get the generics
            gens = list(self.getGenerics().values())
            #add the generics (if exists)
            if(len(gens)):
                comp_txt = comp_txt + ' #(\n'
                #add-in every generic as a 'parameter'
                for gen in gens:
                    #add declaration
                    gen_dec = ((tabs+1)*T)+gen.writeDeclaration(form, spaces=spaces)
                    #enter newlines
                    if(gen == gens[-1]):
                        #trim final ','
                        gen_dec = gen_dec[:len(gen_dec)-1]
                        #check if to hang end
                        if(hang_end):
                            gen_dec = gen_dec + '\n'
                        gen_dec = gen_dec + ')'
                    else:
                        gen_dec = gen_dec + '\n'
                    comp_txt = comp_txt + gen_dec
                pass

            #get the ports
            ports = list(self.getPorts().values())
            #add the ports (if exists)
            if(len(ports)):
                if(hang_end == False):
                    comp_txt = comp_txt + '\n(\n'
                else:
                    comp_txt = comp_txt + ' (\n'
                #get all datatypes
                ports_dt = []
                for p in ports:
                    ports_dt += [p.castDatatype(form, keep_net=True)]
                #compute longest datatype
                farthest = apt.computeLongestWord(ports_dt)
                #add-in every port
                for port in ports:
                    #compute number of spaces for this port declaration
                    if(align):
                        spaces = farthest - len(port.castDatatype(form, keep_net=True)) + 1
                    #add port declaration
                    port_dec = ((tabs+1)*T) + port.writeDeclaration(form, spaces, align)
                    #enter newlines
                    if(port == ports[-1]):
                        #chop off final ','
                        port_dec = port_dec[:len(port_dec)-1]
                        #check if to hang end
                        if(hang_end):
                            port_dec = port_dec + '\n'
                        port_dec = port_dec + ')'
                    else:
                        port_dec = port_dec + '\n'
                    comp_txt = comp_txt + port_dec
                    pass
                pass
            
            #add final semicolon
            comp_txt = comp_txt + ';'
            pass

        return comp_txt


    def getPorts(self):
        '''Returns _ports (Map).'''
        return self._ports


    def getGenerics(self):
        '''Returns _generics (Map).'''
        return self._generics


    def getName(self):
        '''Returns _name (str).'''
        return self._name


    def getLibrary(self):
        '''Returns _library (str).'''
        return self._library


    # uncomment to use for debugging
    # def __str__(self):
    #     return f'''
    #     ports: {list(self.getPorts().values())}
    #     generics: {list(self.getGenerics().values())}
    #     '''


    pass