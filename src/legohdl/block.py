# ------------------------------------------------------------------------------
# Project: legohdl
# Script: block.py
# Author: Chase Ruskin
# Description:
#   This script describes the attributes and behaviors for a "block" within
#   the legohdl framework. A block is a HDL project with a marker file at the 
#   root folder.
# ------------------------------------------------------------------------------

import os, shutil, stat, glob
import logging as log
from datetime import date
from enum import Enum

from .apparatus import Apparatus as apt
from .cfg import Cfg, Section, Key
from .git import Git
from .map import Map
from .graph import Graph
from .vhdl import Vhdl
from .verilog import Verilog
from .unit import Unit


#a Block is a package/module that is signified by having the marker file
class Block:

    #define the various places a block can exist
    class Level(Enum):
        DNLD  = 0
        INSTL = 1
        AVAIL = 2
        VER   = 3
        TMP   = 9
        pass


    LAYOUT = {'block' : {
                'name' : Cfg.NULL,
                'library' : Cfg.NULL,
                'version' : Cfg.NULL,
                'remote' : Cfg.NULL,
                'vendor' : Cfg.NULL,
                'requires' : '()'},
            }

    #metadata that must be written in [block] else the block is seen as corrupted
    REQ_KEYS = ['name', 'library', 'version', 'remote', 'vendor', 'requires']

    #metadata that gets added as block loses detail (at AVAIL or VERS level)
    EXTRA_KEYS = ['versions', 'size', 'vhdl-units', 'vlog-units']

    #supported files to be identified as "changelogs"
    CHANGE_LOGS = ['changelog.md', 'change.log', 'changelog.txt']

    #class attribute that is a block object found on current path
    _Current = None

    #class container listing storing all created blocks
    Inventory = Map()

    #class container storing the relationships between blocks
    Hierarchy = Graph()

    #an unreleased block's version number
    NULL_VER = 'v0.0.0'


    def __init__(self, path, ws, lvl=Level.DNLD):
        '''
        Create a legohdl Block object. 
        
        If a valid Block.cfg file is found as the path or within the direct
        path directory, title is ignored and data is loaded from metadata.

        Parameters:
            path (str): the filepath to the Block's root directory
            ws (Workspace): the workspace this block belongs to
            lvl (Block.Level): the level at which the block exists
        '''
        #store the block's workspace
        self._ws = ws
        
        self._path = apt.fs(path)
        #is this a valid Block marker?
        fname = os.path.basename(path)

        self._lvl = lvl
        
        if(fname == apt.MARKER):
            self._path,_ = os.path.split(path)
            self._path = apt.fs(self._path)
            pass
        #try to see if a Block marker is within this directory
        elif(os.path.isdir(path)):
            files = os.listdir(path)
            for f in files:
                if(f == apt.MARKER):
                    self._path = apt.fs(path)
                    break
        #check if valid
        if(self.isValid()):
            #create Git object if is download block or main installation
            if(self._lvl == Block.Level.DNLD or self._lvl == Block.Level.INSTL or \
                self._lvl == Block.Level.TMP):
                self._repo = Git(self.getPath())
            #are the two paths equal to each other? then this is the current block
            if(apt.isEqualPath(self.getPath(), os.getcwd())):
                self.setCurrent(self)
                
            #load from metadata
            self.loadMeta()
            
            #add the block to the inventory
            success = False
            if(self._lvl != Block.Level.TMP):
                success = self.addToInventory()

            #store specifc installation versions in a map
            if(success and self._lvl == Block.Level.INSTL):
                self.getInstalls()
            pass
        pass


    @classmethod
    def setCurrent(cls, b):
        cls._Current = b


    def getLvl(self):
        '''Returns _lvl (Block.Level). Use .value to get (int) representation.'''
        return self._lvl


    def addToInventory(self):
        '''
        Adds the self block object to the class container at the correct level.

        Blocks of level VER or TMP are skipped when trying to add to the Inventory.

        Parameters:
            None
        Returns:
            (bool): determine if the block was successfully added (spot empty)
        '''
        #make sure appropriate scopes exists in inventory
        if(self.M().lower() not in Block.Inventory.keys()):
            Block.Inventory[self.M()] = Map()
        if(self.L().lower() not in Block.Inventory[self.M()].keys()):
            Block.Inventory[self.M()][self.L()] = Map()
        #define empty tuple for all of a block's levels
        if(self.N().lower() not in Block.Inventory[self.M()][self.L()].keys()):
            Block.Inventory[self.M()][self.L()][self.N()] = [None, None, None]
        #check if the level location is empty
        lvl = self.getLvl().value
        if(lvl < len(Block.Inventory[self.M()][self.L()][self.N()])):
            if(Block.Inventory[self.M()][self.L()][self.N()][lvl] != None):
                log.error("Block "+self.getFull()+" already exists at level "+str(lvl)+"!")
                return False
            #add to inventory if spot is empty
            else:
                Block.Inventory[self.M()][self.L()][self.N()][lvl] = self

        if(self.getMeta('requires') != None):
            #update graph
            #print(self.getFull(inc_ver=True))
            Block.Hierarchy.addVertex(self.getFull(inc_ver=True))
            #print(self.getFull(inc_ver=True))
            for d in self.getMeta('requires'):
                #remove any partial versions from identifier in requires
                at_i = d.rfind('@')
                v_i = d.rfind('(')
                d = d[:v_i+1] + d[at_i:]
                #add edge to graph
                #print(d)
                Block.Hierarchy.addEdge(self.getFull(inc_ver=True), d)
                pass

        return True


    @classmethod
    def getCurrent(cls, bypass=False):
        if(bypass == False and cls._Current == None):
            exit(log.error("Not in a valid block!"))
        return cls._Current


    def getWorkspace(self):
        '''Returns the block's workspace _ws (Workspace).'''
        return self._ws


    #return the block's root path
    def getPath(self, low=False):
        if(low):
            return self._path.lower()
        else:
            return self._path


    def getInstalls(self, returnvers=False):
        '''
        Dynamically creates and returns map of block objects that are found
        in cache as specific installations.

        The Map uses the version number (folder name) as the key and the block
        object as the value.

        Parameters:
            returnvers (bool): determine if to only return keys (versions)
        Returns:
            _instls [Map(Block)]: list of specific block installations
            or
            [str]: list of version keys when returnvers is set
        '''
        #first ensure using the installation level
        instl = self.getLvlBlock(Block.Level.INSTL)

        #return empy structures if installation DNE
        if(instl == None):
            if(returnvers):
                return []
            return Map()

        #dynamically use existing attribute computation
        if(hasattr(instl, '_instls')):
            if(returnvers):
                return list(instl._instls.keys())
            return instl._instls

        instl._instls = Map()

        #get all folders one path below
        base_path,_ = os.path.split(instl.getPath()[:len(instl.getPath())-1])
        base_path = apt.fs(base_path)
        dirs = os.listdir(base_path)
        for d in dirs:
            if(Block.validVer(d, places=[1,2,3])):
                path = apt.fs(base_path+d+'/')
                instl._instls[d] = Block(path, instl.getWorkspace(), lvl=Block.Level.VER)

        if(returnvers):
                return list(instl._instls.keys())
        return instl._instls


    def delete(self, prompt=False, squeeze=0):
        '''
        Deletes the block object. Removes its path. Does not update any class variables,
        such as the graph.
        
        Parameters:
            prompt (bool): determine if to issue prompt if deleting a DNLD block
            squeeze (int): number of possible empty nested folders to remove
        Returns:
            None
        '''
        #get the status of the levels for this block
        lvls = Block.Inventory[self.M()][self.L()][self.N()]
        #if block is nowhere else, ask for confirmation and warn user that
        #the block may be unrecoverable.
        yes = True
        if(lvls.count(None) == len(lvls)-1):
            yes = apt.confirmation("Block "+self.getFull()+" does not exist anywhere else; deleting "+\
                "it from the workspace path may make it unrecoverable. Delete anyway?")
        elif(self.getLvl() == Block.Level.DNLD and prompt):
            yes = apt.confirmation("Are you sure you want to remove block "+self.getFull()+" from the "+\
                "workspace's local path?")

        if(yes == False):
            log.info("Cancelled.")
            return
        #delete the directory
        shutil.rmtree(self.getPath(), onerror=apt.rmReadOnly)

        #remove from inventory
        if(self.getLvl().value < len(lvls)):
            Block.Inventory[self.M()][self.L()][self.N()][self.getLvl().value] = None

        #display message to user indicating deletion was successful
        if(self.getLvl() == Block.Level.DNLD):
            log.info("Deleted block "+self.getFull()+" from downloads.")

        #try to continually clean up empty folders
        nested = self.getPath()
        for i in range(squeeze):
            #remove the trailing slash '/'
            nested = nested[:len(nested)-1]
            #step back 1 directory
            nested,_ = os.path.split(nested)
            #print(nested)
            #try to remove this directory
            if(len(os.listdir(nested)) == 0):
                shutil.rmtree(nested, onerror=apt.rmReadOnly)
            #not encountering empty directories anymore
            else:
                break
            pass
        pass


    def getLvlBlock(self, lvl):
        '''
        Tries to get the block of same M.L.N but at the request level.

        Returns None if the block does not exist at that level.

        Parameters:
            lvl (Block.Level): which level to get self block from
        Returns:
            (Block): the block from requested level
        '''
        return Block.Inventory[self.M()][self.L()][self.N()][int(lvl.value)]

    
    def getTitle(self, index, dist=0):
        '''
        Returns partial or full block title M.L.N. index 2 corresponds to the
        the N, 1 corresponds to L, and 0 corresponds to M.

        Parameters:
            index (int): 0-2 to indicate what section to start at
            dist (int): 0-2 indicates how many additional sections to include
        Returns:
            ((str)): tuple of requested title sections where 0 = M, 1 = L, 2 = N
        '''
        sects = (self.M(), self.L(), self.N())
        return sects[index-dist:index+1]


    def getTitle_old(self, low=True, vndr=False):
        '''
        Returns the full block title combined.
        
        Parameters:
            low (bool): enable case-sensitivity
            vndr (bool): prepend vendor name, if available
        Returns:
            (str): M.L.N format
        '''
        m = ''
        if(vndr and self.getMeta('vendor') != None):
            m = self.getMeta('vendor')+'.'
            
        return m+self.L()+'.'+self.N()


    def getVersion(self):
        '''Returns version without 'v' prepended.'''
        return self.getMeta('version')


    def getHighestTaggedVersion(self):
        '''
        Returns the highest tagged version for this block's repository or (v0.0.0 
        if none found).

        Parameters:
            None
        Returns:
            highest (str): highest version in format ('v0.0.0')
        '''
        all_vers = self.getTaggedVersions()
        highest = 'v0.0.0'
        for v in all_vers:
            if(self.cmpVer(highest,v) == v):
                highest = v
        return highest


    def waitOnChangelog(self, ver):
        '''
        Automatically opens the CHANGELOG in the configured editor to update.

        Parameters:
            ver (str): version to write new line for
        Returns:
            (bool): determine if the changelog was opened (release was paused)
        ''' 
        cl = self.getChangelog()
        #no changelog identified for this block.
        if(cl == None):
            return False  
        #no editor available to open the changelog      
        if(apt.getEditor() == Cfg.NULL):
            log.info("Skipping updating CHANGELOG due to no configured text-editor...")
            return False

        #check that a changelog exists for this block
        with open(cl, 'r+') as f:
            data = f.read()
            f.seek(0)
            f.write(ver+'\n\n'+data)
            f.close()

        #open the changelog and wait for the developer to finish writing changes
        apt.execute(apt.getEditor(), cl)
        try:
            resp = input("Enter 'k' when done writing CHANGELOG to proceed...")
        except KeyboardInterrupt:
            exit('\nExited prompt. Release cancelled.')
        while resp.lower() != 'k':
            try:
                resp = input()
            except KeyboardInterrupt:
                exit('\nExited prompt. Release cancelled.')

        return True


    def getChangelog(self, rel_path=False, returnname=False):
        '''
        Find a supported changelog file and return its filepath. Dynamically
        creates a _changelog (str) attr. Returns None if DNE.

        Parameters:
            rel_path (bool): determine if to return the changelog's relative path
        Returns:
            _changelog (str): filepath for the changelog
        '''
        if(hasattr(self, "_changelog")):
            if(rel_path and self._changelog != None):
                return self._changelog.replace(self.getPath(), '')
            elif(returnname):
                return os.path.split(self._changelog)[1]
            return self._changelog

        #get all files
        all_files = glob.glob(self.getPath()+"**/*", recursive=True)
        self._changelog = None
        #iterate through all results to find a changelog
        for f in all_files:
            #skip all non-files found
            if(os.path.isfile(f) == False):
                continue
            #extract the filename
            _,fname = os.path.split(f)
            #check if filename matches a supported changelog file
            if(fname.lower() in Block.CHANGE_LOGS):
                self._changelog = f
                break
            pass
        if(rel_path and self._changelog != None):
            return self._changelog.replace(self.getPath(), '')
        elif(returnname):
            return os.path.split(self._changelog)[1]
        return self._changelog


    def release(self, next_ver, msg=None, dry_run=False, only_meta=False, no_install=False, skip_changelog=False):
        '''
        Releases a new version for a block to be utilized in other designs.

        A dry-run will not affect any part of the block and is used for helping
        the user see if the release will go smoothly.

        Parameters:
            next_ver (str): requested version to be the next release point
            msg (str): the message to go along with the git commit
            dry_run (bool): determine if to fake the release to see if things would go smoothly
            only_meta (bool): determine if to add/commit only metadata file or all unsaved changes
            no_install (bool): determine if to avoid automically installing new release to cache
            skip_changelog (bool): determine if to skip writing to changelog (if exists)
        Returns:
            None
        '''
        #ensure at least one parameter was passed
        if(next_ver == None):
            log.error("No version given for next release point.")
            return

        if(dry_run):
            log.info("Performing dry-run...")
        #variable to store details about the dry-run
        release_report = '--- RELEASE REPORT ---\n'

        #check which command-line argument was used
        inc_major = next_ver.lower() == 'major'
        inc_minor = next_ver.lower() == 'minor'
        inc_patch = next_ver.lower() == 'patch'
        use_version = Block.validVer(next_ver, places=[3])

        #try to locate the vendor
        vndr = None
        for m in self.getWorkspace().getVendors():
            if(self.getMeta('vendor').lower() == m.getName().lower()):
                vndr = m
                break

        #1. Verify security checks and that the repository has the latest commits

        #make sure the metadata looks good
        self.secureMeta()

        #verify user has permission to write to remote if it exists
        if(self._repo.hasWritePermission() == False):
            log.error("Unable to release block due to invalid write permissions for block's remote repository!")
            return

        #look ahead to verify user has permission to write to the vendor if it exists
        if(vndr != None and vndr._repo.hasWritePermission() == False):
            log.error("Unable to release block to vendor "+vndr.getName()+" due to invalid write permissions for vendor's remote repository!")
            return

        #make sure the repository is up to date (silence print to console on none-remote repos to avoid confusion)
        if(self._repo.remoteExists()):
            log.info("Verifying repository is up-to-date...")
        up2date, connected = self._repo.isLatest()
        if(connected == False):
            return
        if(up2date == False):
            log.error("Verify the repository is up-to-date before releasing.")
            return
        if(self._repo.remoteExists()):
            log.info("Success.")

        highest_ver = self.getHighestTaggedVersion()
        p_maj,p_min,p_fix = Block.sepVer(highest_ver)

        #make sure the metadata is not corrupted
        if(self.isCorrupt(highest_ver, disp_err='released')):
            return

        #2. compute next version number

        #make sure the next version is higher than any previous
        if(use_version):
            if(Block.cmpVer(next_ver, highest_ver) == highest_ver):
                log.error("Specified version "+next_ver+" is not higher than latest version "+highest_ver+"!")
                return
        #increment major value +1
        elif(inc_major):
            p_maj += 1
            p_min = p_fix = 0
            next_ver = 'v'+str(p_maj)+'.'+str(p_min)+'.'+str(p_fix)
        #incremente minor value
        elif(inc_minor):
            p_min += 1
            p_fix = 0
            next_ver = 'v'+str(p_maj)+'.'+str(p_min)+'.'+str(p_fix)
        #increment patch value
        elif(inc_patch):
            p_fix += 1
            next_ver = 'v'+str(p_maj)+'.'+str(p_min)+'.'+str(p_fix)
        #ensure at least one parameter was given correctly
        else:
            log.error("Invalid next version given as "+next_ver+'.')
            return

        #check updates on block requirements
        block_reqs = self.updateRequires(dry_run=dry_run, quiet=True)
        #make sure block does not require any 'unstable' blocks
        stable = self.checkStability(block_reqs)
        if(stable == False):
            log.error("Unable to release block due to requiring unstable blocks.\n\
        Release all unstable sub-blocks and disable 'general.multi-develop' or use\n\
        stable versions of every required block before continuing.")
            #exit if this is the real thing
            if(dry_run == False):
                return

        release_report = release_report + "Release point: "+ next_ver+".\n"
        if(dry_run == False):
            log.info("Saving block release point "+next_ver+"...")

        #ensure version has a 'v' in prepended
        next_ver = next_ver.lower()
        if(next_ver[0] != 'v'):
            next_ver = 'v'+next_ver

        #check to write updates to changelog
        changelog_altered = False
        if(skip_changelog == False):
            cl_txt = "Identified no CHANGELOG to edit."
            if(self.getChangelog() != None):
                cl_txt = "Identified CHANGELOG "+self.getChangelog(returnname=True)+" to edit."
            release_report = release_report + cl_txt+"\n"
            if(dry_run == False):
                changelog_altered = self.waitOnChangelog(next_ver)

        #3. Make sure block dependencies/derivatives and metadata are up-to-date

        #update dynamic attributes
        self._V = next_ver
        self._tags += [next_ver]

        self.setMeta('version', next_ver[1:])

        #check updates on block requirements
        block_reqs = self.updateRequires(dry_run=dry_run, quiet=True)
        #add text for block requirements found
        release_report = release_report + 'Block Requirements:\n'
        req_txt = '    N/A'
        if(len(block_reqs)):
            req_txt = '    '+apt.listToStr(block_reqs, delim='\n    ')
        release_report = release_report + req_txt + '\n'

        #save changes if the real deal
        if(dry_run == False):
            self.save(force=True)

        #4. Make a new git commit

        if(only_meta and dry_run == False):
            self._repo.add(apt.MARKER)
            if(changelog_altered):
                self._repo.add(self.getChangelog(rel_path=True))
        elif(dry_run == False):
            self._repo.add('.')

        #insert default message
        if(msg == None):
            msg = "Releases legohdl version "+next_ver

        #get what branch currently on
        cur_branch = self._repo.getBranch()
        release_report = release_report + "Branch: "+cur_branch+"\n"
        release_report = release_report + "Commit message: "+msg+"\n"
        if(dry_run == False):
            self._repo.commit(msg)

        #5. Create a new git tag
        
        release_report = release_report + "Git tag: "+next_ver+apt.TAG_ID+"\n"
        if(dry_run == False):
            self._repo.git('tag',next_ver+apt.TAG_ID)

        #6. Push to remote and to vendor if applicable

        #synch changes with remote repository
        if(dry_run == False):
            self._repo.push()

        #7. install latest version to the cache
        if(no_install == False and dry_run == False):
            #reset inventory
            self.install()

        outcome = 'PASSED' if(stable) else 'FAILED'

        #no vendor to publish to then release algorithm is complete
        if(len(self.getMeta('vendor')) == 0):
            #complete dry-run and print report
            if(dry_run):
                log.info("Dry run complete.")
                release_report = release_report + 'Publish to vendor: N/A\n'
                print(release_report+"Dry run: "+outcome+"\n")
            return

        publish = True

        #check if vendor is found in workspace for publishing
        if(vndr == None):
            log.warning("Unable to publish because vendor "+self.M()+" is not found in this workspace.")
            publish = False

        #check if the block has a remote repo in order to publish to vendor
        if(self._repo.remoteExists() == False):
            log.warning("Unable to publish to vendor "+vndr.getName()+" because a remote repository is not configured.")
            publish = False

        publish_result = 'PASSED' if(publish) else 'FAILED'
        release_report = release_report + 'Publish to vendor: '+publish_result+'\n'
        #complete dry-run and print report
        if(dry_run):
            log.info("Dry run complete.")
            print(release_report+"Dry run: "+outcome+"\n")
        #publish to the vendor
        elif(publish):
            vndr.publish(self)
        pass


    def initMeta(self):
        '''
        Create basic metadata data structure. Fills in placeholders for all
        fields outside and inside of [block].

        Parameters:
            None
        Returns:
            None
        '''
        #fill in placeholders for metadata (two-level sections)
        custom_meta = apt.CFG.get('metadata', dtype=Section)
        for section,keys in custom_meta.items():
            #skip immediate-level keys or add as global keys?
            if(isinstance(keys, Key)):
                continue
            #iterate through all keys for the given section
            for key in keys.values():
                for ph in self.getPlaceholders(tmp_val=''):
                    key._val = key._val.replace(ph[0],ph[1])
                    pass
                custom_meta[section][key._name] = Key(key._name, key._val)
                pass
            pass
        
        #create block's metadata object
        self._meta = Cfg(self.getPath()+apt.MARKER, data=Section(self.LAYOUT))
        
        #merge skeleton metadata and custom configured user-defined metadata
        for sect in custom_meta.values():
            if(isinstance(custom_meta[sect._name], Key)):
                continue
            #unset override to prevent overwriting any required keys
            self._meta.set(sect._name, sect, override=True)
            pass

        #write new metadata file
        self._meta.write(auto_indent=False)
        pass


    def checkStability(self, block_reqs):
        '''
        Return (bool) if any block in the block's requirements uses an 
        'unstable' version (in-development). Non-recursive method to check under
        all block requirements from graph.

        Parameters: 
            block_reqs ([str]): list of current block requirements
        Returns:
            (stable): determine if found zero counts of 'unstable' in all requirements
        '''
        #check current block's requirements first
        #split identifier found in metadata
        spec_vers = []
        #track what blocks to use latest
        use_latest = []
        for r in block_reqs:
            _,_,_,ver = Block.snapTitle(r)
            #the block relies on a block from downloads -> unstable design
            if(ver.lower().count('unstable')):
                return False
            #add the title only as specific version
            at_i = r.rfind('@')
            v_i = r.rfind('(')
            spec_v = r[:v_i+1].lower() + r[at_i:].lower()
            spec_vers += [spec_v]
            #remember which to use latest for
            if(ver.lower().count('latest')):
                use_latest += [spec_v]
            pass

        #print('specific versions:',spec_vers)
        #print('latest:',use_latest)
        #check requirements for neighboring vertices
        next_blocks = Block.Hierarchy.getNeighbors(self.getFull(inc_ver=True)) 
        #ignore edges that aren't matched in requirements
        next_blocks = list(filter(lambda a: a in spec_vers, next_blocks))
        #create stack
        neighbor_blocks = [(next_blocks, use_latest)]
        #print(neighbor_blocks)
        while(len(neighbor_blocks)):
            #grab a block's requirements and the use latest list
            #get a block indentifier ([requirements], [use_latest])
            gs, ul = neighbor_blocks.pop()
            #iterate through every block
            for b_id in gs:
                #access this block from its identifier
                V,L,N,ver = Block.snapTitle(b_id)

                #remove leading '@' symbol
                ver = ver[1:]
                #guaranteed to be from cache because checked for 'unstables' beforehand

                #access the block from installation at the specific version
                if(V in Block.Inventory.keys() and L in Block.Inventory[V].keys() and N in Block.Inventory[V][L].keys()):
                    #print('block id:',b_id)
                    #print("use-latest list:",ul)
                    if(Block.Inventory[V][L][N][Block.Level.INSTL.value] != None):
                        #get latest install block
                        target_block = Block.Inventory[V][L][N][Block.Level.INSTL.value]
                        #grab specific block if not using latest (the latest's specific version may not be installed)
                        if(b_id.lower() not in ul):
                            ver_blocks = Block.Inventory[V][L][N][Block.Level.INSTL.value].getInstalls()
                            #print(ver_blocks)
                            if(ver not in ver_blocks.keys()):
                                #should not encounter this error
                                log.error("Unidentified version '"+ver+"' from block requirement "+b_id)
                                return False
                            target_block = target_block.getInstalls()[ver]
                            pass
                        #access requirements from the target block
                        reqs = target_block.getMeta('requires')
                    else:
                        log.error("Block requirement "+b_id+" not found in the cache.")
                        return False
                else:
                    log.error("Unknown block requirement: "+b_id)
                    return False

                #reset spec_ver list
                spec_vers = []
                #reset use latest list
                use_latest = []

                #check the requirements in metadata
                for r in reqs:
                    #split identifier found in metadata
                    _,_,_,ver = Block.snapTitle(r)
                    #print('reading:',ver)
                    #the block relies on a block from downloads -> unstable design
                    if(ver.lower().count('unstable')):
                        return False
                    #add the title only as specific version
                    at_i = r.rfind('@')
                    v_i = r.rfind('(')
                    spec_v = r[:v_i+1].lower() + r[at_i:].lower()
                    spec_vers += [spec_v]
                    #remember which to use latest for
                    if(ver.lower().count('latest')):
                        use_latest += [spec_v]
                    pass

                #add this block's requirements to stack
                next_blocks = Block.Hierarchy.getNeighbors(b_id)
                #ignore edges that aren't matched in requirements
                next_blocks = list(filter(lambda a: a in spec_vers, next_blocks))
                #add to the list
                neighbor_blocks = [(next_blocks, use_latest)] + neighbor_blocks
                pass

            pass

        return True


    def sortVersions(self, unsorted_vers):
        '''
        Returns a list from highest to lowest using merge sort.
        '''


        def mergeSort(l1, r1):
            '''
            Mergesort (2/2) - begin merging lists.
            '''
            sorting = []
            while len(l1) and len(r1):
                if(Block.cmpVer(l1[0],r1[0]) == r1[0]):
                    sorting.append(r1.pop(0))
                else:
                    sorting.append(l1.pop(0))
            if(len(l1)):
                sorting = sorting + l1
            if(len(r1)):
                sorting = sorting + r1
            return sorting


        #split list
        midpoint = int(len(unsorted_vers)/2)
        l1 = unsorted_vers[:midpoint]
        r1 = unsorted_vers[midpoint:]
        #recursive call to continually split list
        if(len(unsorted_vers) > 1):
            return mergeSort(self.sortVersions(l1), self.sortVersions(r1))
        else:
            return unsorted_vers


    def getHighestAvailVersion(self):
        '''
        Returns highest available version from the AVAIL level. Will return '0.0.0'
        if DNE. Will then return the download's current version if a block is
        not found in the AVAIL level.

        Parameters:
            None
        Returns:
            avail_ver (str): highest available version
        '''
        avail_ver = '0.0.0'
        #check if block has AVAIL status
        b = self.getLvlBlock(Block.Level.AVAIL)
        #return '0.0.0' if not available
        if(b == None):
            #check against downloads latest version
            b = self.getLvlBlock(Block.Level.DNLD)
            #not avail nor dnld, return '0.0.0'
            if(b == None):
                return avail_ver
            #return dnld's version
            return b.getVersion()

        #return first version of already-sorted list
        if(len(b.getMeta('versions'))):
            avail_ver = b.getMeta('versions')[0]
        return avail_ver



    def getTaggedVersions(self):
        '''
        Returns a list of all version #'s that had a valid TAG_ID appended from
        the git repository tags. Dynamically creates attr _tags to be used again.

        Parameters:
            None
        Returns:
            _tags ([str]): list of version values like 'v0.0.0'
        '''
        if(hasattr(self, '_tags')):
            return self._tags
        if(hasattr(self, '_repo') == False):
            return []

        all_tags,_ = self._repo.git('tag','-l')

        #print(all_tags)
        #split into list
        all_tags = all_tags.split("\n")
        self._tags = []

        #only add any tags identified by legohdl
        for t in all_tags:
            if(t.endswith(apt.TAG_ID)):
                #trim off identifier
                t = t[:t.find(apt.TAG_ID)]
                #ensure it is valid version format
                if(self.validVer(t)):
                    self._tags.append(t)

        #print(self._tags)
        #return all tags
        return self._tags


    @classmethod
    def stdVer(cls, ver, add_v=False, rm_v=False, z_ext=False):
        '''
        Standardize the version argument by swapping '_' with '.'. 'add_v' has 
        higher precedence than 'rm_v'.

        Parameters:
            ver (str): word to perform replace on
            add_v (bool): determine if to add 'v' if DNE
            rm_v (bool): detemine if to remove 'v' if exists
            z_ext (bool): write version to have 3 places if less than 3 (zero-extend)
        Returns:
            (str): properly standardized version
        '''
        #swap '_' for '.'
        ver = ver.replace('_','.')

        #optionally remove 'v' from beginning
        if(rm_v and len(ver) and ver[0] == 'v'):
            ver = ver[1:]
        #optionally add 'v' to beginning
        if(add_v and len(ver) and ver[0] != 'v'):
            ver = 'v' + ver

        #remove a trailing '.' if exists
        if(len(ver) and ver[-1] == '.'):
            ver = ver[:len(ver)-1]

        #optionally zero-extend the version number
        diff = 3 - len(ver.split('.'))
        if(z_ext):
            ver = ver + '.0'*diff

        return ver


    @classmethod
    def cmpVer(cls, lver, rver):
        '''
        Compare two versions. Retuns the higher version, or 'rver' if both equal.

        Parameters:
            lver (str): lhs version disregarding format
            rver (str): rhs version disregarding format
        Returns:
            ver (str): the parameter (lver or rver) who had higher values
        '''
        l1,l2,l3 = cls.sepVer(lver)
        r1,r2,r3 = cls.sepVer(rver)
        if(l1 < r1):
            return rver
        elif(l1 == r1 and l2 < r2):
            return rver
        elif(l1 == r1 and l2 == r2 and l3 <= r3):
            return rver
        return lver


    @classmethod
    def validVer(cls, ver, places=[3]):
        '''
        Validates a string to determine if its a valid version format. 'ver' does
        not need to have a 'v' in front.

        Parameters:
            ver (str): the string to test if is valid version format
            places ([int]): the number of version parts to test against
        Returns:
            (bool): if 'ver' meets the version requirements for validation
        '''
        #standardize the version string
        ver = cls.stdVer(ver)
        #split the version into its parts
        parts = ver.split('.')

        #number of parts must equal the number of places being tested
        if(len(parts) not in places):
            return False
        
        #truncate 'v' from beginning of first part
        if(parts[0].lower().startswith('v')):
            parts[0] = parts[0][1:]

        #all sections must only contain digits
        for p in parts:
            if(p.isdecimal() == False):
                return False

        #valid version if passes test for all parts being decimal
        return True
    

    @classmethod
    def sepVer(cls, ver):
        '''
        Separate a version into 3 integer values.

        Parameters:
            ver (str): any type of string, can also be None
        Returns:
            r_major (int): biggest version number
            r_minor (int): middle version number
            r_patch (int): smallest version number
        '''
        ver = cls.stdVer(ver)
        if(ver == '' or ver == None):
            return 0,0,0
        if(ver[0] == 'v'):
            ver = ver[1:]

        first_dot = ver.find('.')
        last_dot = ver.rfind('.')

        try:
            r_major = int(ver[:first_dot])
        except:
            r_major = 0
        try:
            r_minor = int(ver[first_dot+1:last_dot])
        except:
            r_minor = 0
        try:
            r_patch = int(ver[last_dot+1:])
        except:
            r_patch = 0
        return r_major,r_minor,r_patch


    def secureMeta(self):
        '''
        Performs safety measures on the block's metadata. Only runs once before
        dynamically creating an attr.

        Parameters:
            None
        Returns:
            None
        '''
        if(hasattr(self, "_is_secure")):
            return

        if('block' not in self._meta._data.keys()):
            self._meta.set('block', Section())

        #ensure all required fields from 'block' section exist
        for key in Block.REQ_KEYS:
            if(key not in self.getMeta().keys()):
                self._meta.set('block.'+key, Cfg.NULL)

        #ensure requires is a proper list format
        if(self._meta.get('block.requires') == Cfg.NULL):
            self._meta.set('block.requires', '()')
 
        self.save()

        if(hasattr(self, "_repo")):
            #grab highest available version
            correct_ver = self.getHighestTaggedVersion()[1:]   
            #dynamically determine the latest valid release point
            self.setMeta('version', correct_ver)

            #check value in metadata if a valid remote to set different than repo's data
            rem = self.getMeta('remote')
            if(rem != self._repo.getRemoteURL()):
                #validate its remote connection
                if(Git.isValidRepo(rem, remote=True)):
                    self._repo.setRemoteURL(rem)

            #set the remote correctly
            self.setMeta('remote', self._repo.getRemoteURL())
            pass

        #ensure the vendor is valid
        if(self.getMeta('vendor') != Cfg.NULL):
            m = self.getMeta('vendor')
            if(m.lower() not in self.getWorkspace().getVendors(returnnames=True)):
                #log.warning("Vendor "+m+" from "+self.getFull()+" is not available in this workspace.")
                pass
            pass

        #dynamically create attr to only allow operation to occur once
        self._is_secure = True
        return
      

    def loadMeta(self):
        '''
        Load the metadata from the Block.cfg file into the _meta dictionary.

        Also creates backup data _meta_backup for later comparison to determine
        if to save (write to file). Only performs safety checks (like reading a remote
        url) if the block loaded is the current working directory block

        Parameters:
            None
        Returns:
            None
        '''
        if(hasattr(self, '_meta')):
            return self._meta

        self._meta = Cfg(self.getMetaFile(), data=Section())
        self._meta.read()
                
        #performs safety checks only on the block that is current directory
        if(self == self.getCurrent(bypass=True)):
            self.secureMeta()

        self.save()
        pass


    def newFile(self, fpath, tmplt_fpath=None, force=False, not_open=False):
        '''
        Create a new file from a template file to an already existing block.

        Parameters:
            fpath (str): the file to create
            tmpltfpath (str): the file to copy from
            force (bool): determine if to overwrite an existing file of same desired name
            not_open (bool): determine if to not open the file after creation
        Returns:
            success (bool): determine if operation was successful
        '''
        fpath = apt.fs(fpath)

        #make sure path will be used from current directory
        if(fpath.startswith('./') == False):
            fpath = './'+fpath

        base_path,fname = os.path.split(fpath)
        #remove extension from file's name to get template placeholder value
        fname,_ = os.path.splitext(fname)

        #make sure file doesn't already exist
        if(force == False and os.path.exists(fpath)):
            log.error("File already exists.")
            return False
        #make sure if using template file that it does exist
        if(tmplt_fpath != None and tmplt_fpath not in apt.getTemplateFiles(apt.getTemplatePath(), inc_hidden=True, returnnames=True)):
            log.error(tmplt_fpath+" does not exist in the current template.")
            return False

        #create any non-existing directory paths
        os.makedirs(base_path, exist_ok=True)

        #only create a new empty file
        success = False
        if(tmplt_fpath == None):
            log.info("Creating empty file "+fpath+"...")
            with open(fpath, 'w') as f:
                f.close()
            success = True
            pass
        else:
            #get full path for template file
            tmplt_fpath = apt.fs(apt.getTemplatePath()+tmplt_fpath)
            #create file from template file
            log.info("Creating file "+fpath+" from "+tmplt_fpath+"...")
            #copy file
            try:
                shutil.copyfile(tmplt_fpath, fpath)
            except PermissionError:
                log.error("Permission denied trying to write to "+fpath+".")
                exit(1)
            #fill in placeholder values
            success = self.fillPlaceholders(fpath, template_val=fname)
            pass

        #open the file
        if(success and not_open == False):
            log.info("Opening file "+fpath+"...")
            apt.execute(apt.getEditor(), fpath)
        return success

    
    def create(self, title, cp_template=True, remote=None):
        '''
        Create a new block at _path. Creates git repository if DNE and the Block.cfg
        file.

        Parameters:
            title (str): M.L.N.V format
            cp_template (bool): determine if to copy in the template to this location
            remote (str): a git url to try to hook up with the new block
            fork (bool): determine if to drop the given remote url from the block
        Returns:
            success (bool): determine if the operation executed with no flaws
        '''
        #make sure block is invalid here
        if(self.isValid()):
            log.info("Block already exists here!")
            return False

        #make sure path is within the workspace path
        if(apt.isSubPath(self.getWorkspace().getPath(), self.getPath()) == False):
            log.info("Path is not within the workspace!")
            return False

        #make sure Block.cfg files do not exist beyond the current directory
        md_files = glob.glob(self.getPath()+"**/"+apt.MARKER, recursive=True)
        if(len(md_files) > 0 and self.isValid() == False):
            log.error("Cannot initialize a block when sub-directories are blocks.")
            return False

        #:todo: make sure no directories to get to this one are valid Blocks

        #make sure a git repository is empty if passing in a remote
        if(remote != None and Git.isBlankRepo(remote) == False):
            if(Git.isValidRepo(remote, remote=True)):
                log.error("Cannot create a new block from an existing remote repository; see the 'init' command.")
                return False
            else:
                log.warning("Skipping invalid remote repository "+remote+"...")
        
        #will create path if DNE and copy in template files
        if(cp_template and os.path.exists(self.getPath()) == False):
            log.info("Copying in template...")
            template = apt.getTemplatePath()
            shutil.copytree(template, self.getPath())
            #delete any previous git repository that was attached to template
            if(Git.isValidRepo(self.getPath())):
                shutil.rmtree(self.getPath()+"/.git/", onerror=apt.rmReadOnly)
            #delete all folders that start with '.'
            dirs = os.listdir(self.getPath())
            for d in dirs:
                if(os.path.isdir(self.getPath()+d) and d[0] == '.'):
                    shutil.rmtree(self.getPath()+d, onerror=apt.rmReadOnly)
        #ensure this path exists before beginning to create the block
        else:
            os.makedirs(self.getPath(), exist_ok=True)

        #create the Block.cfg file if DNE
        if(self.isValid() == False):
            self.initMeta()

        #load in empty meta
        self.loadMeta()

        #break into 4 title sections
        M,L,N,_ = Block.snapTitle(title)

        #fill in preliminary data for block.cfg metadata

        #check if vendor is in an allowed vendor
        if(M != ''):
            if(M.lower() in self.getWorkspace().getVendors(returnnames=True)):
                self.setMeta("vendor", M)
            else:
                log.warning("Skipping invalid vendor name "+M+"...")

        self.setMeta('library', L)
        self.setMeta('name', N)
        self.setMeta('version', '0.0.0')
        self.setMeta('requires', '()')

        #fill in placeholders
        if(cp_template):
            template_files = glob.glob(self.getPath()+"/**/*", recursive=True)
            for tf in template_files:
                if(os.path.isfile(tf)):
                    self.fillPlaceholders(tf, self.N())

        #configure the remote repository to be origin for new git repo
        self._repo = Git(self.getPath(), clone=remote)

        #update meta's remote url
        self.setMeta('remote', self._repo.getRemoteURL())

        #print(self.getMeta(every=True))
        #save all changes to meta
        self.save(force=True)

        #commit all file changes
        self._repo.add('.')
        self._repo.commit('Creates legohdl block')

        #push to remote repository
        self._repo.push()

        #display to user where the block is located
        log.info("Block "+self.getFull()+" found at: "+self.getPath())
        #operation was successful
        return True


    def download(self, place=None):
        '''
        Download the block to the workspace's local path. Default place to
        put download is {library}/{name}/.

        Creates a new block object if successfully downloads the block.
        
        Parameters:
            place (str): relative path within the current workspace
        Returns:
            (Block): return the downloaded block (if successful) else None
        '''
        #check if the block is already downloaded
        if(self.getLvlBlock(Block.Level.DNLD) != None):
            log.info("Block "+self.getFull()+" is already downloaded!")
            return None

        success = False

        #assign default place to download block
        if(place == None):
            place = self.L()+"/"+self.N()+"/"

        #standardize the path and prepend the workspace's directory
        place = apt.fs(self.getWorkspace().getPath())+apt.fs(place+'/')
        
        #find and clone from the block's remote URL (if exists)
        rem = self.getMeta('remote')
        #validate repo
        is_valid = rem != None and Git.isValidRepo(rem, remote=True)
        #use remote repository
        if(is_valid):
            success = True

            #create temp directory
            tmp = apt.makeTmpDir()
            g = Git(tmp, clone=rem)
            if(g.hasWritePermission() == False):
                log.error("Cannot download the block; write permissions are not granted for this repository.")
                success = False
            pass
        #use this repository itself if INSTL status
        elif(self.getLvl() == Block.Level.INSTL):
            success = True
            tmp = self.getPath()
            pass

        #move from one folder to the folder marked in downloads area
        if(success):
            #move from repo to path
            try:
                shutil.copytree(tmp, place)
            #catch and handle error if the path is taken
            except FileExistsError:
                log.error("Cannot download block to path "+place)
                success = False

        #remove temp directory
        apt.cleanTmpDir()

        #return None if block download failed
        if(success == False):
            return None

        log.info("Downloaded block "+self.getFull()+" to "+place)
        #create and return the new block
        dnld = Block(place, self.getWorkspace(), lvl=Block.Level.DNLD)
        #allow user to edit files if coming from cache
        if(is_valid == False and success == True):
            dnld.modWritePermissions(enable=True)

        return dnld


    def initialize(self, title, remote=None, fork=False, summary=None):
        '''
        Initializes an existing remote repository or current working directory
        into a legohdl block.

        Parameters:
            remote (str): a git url to try to hook up with the new block
            fork (bool): determine if to drop the given remote url from the block
        Returns:
            success (bool): determine if initialization was successful
        '''
        #make sure the current path is within the workspace path
        if(apt.isSubPath(self.getWorkspace().getPath(), self.getPath()) == False):
            log.error("Cannot initialize a block outside of the workspace path.")
            return False

        #make sure Block.cfg files do not exist beyond the current directory
        md_files = glob.glob(self.getPath()+"**/"+apt.MARKER, recursive=True)
        if(len(md_files) > 0 and self.isValid() == False):
            log.error("Cannot initialize a block when sub-directories are blocks.")
            return False

        #two scenarios: block exists already or block does not exist
        already_valid = self.isValid()
        #block currently exists at this folder
        if(already_valid):
            #check if trying to configure remote (must be empty)
            if(remote != None):
                if(Git.isBlankRepo(remote)):
                    success = self._repo.setRemoteURL(remote)
                    #update metadata if successfully set the url
                    if(success):
                        self.setMeta("remote",remote)
                        self._repo.push()
                elif(remote == ''):
                    #clear the remote
                    self._repo.setRemoteURL('', force=True)
                    #update metadata if successfully cleared the url
                    self.setMeta("remote", self._repo.getRemoteURL())
                else:
                    log.error("Cannot set existing block to a non-empty remote.")
                    return False
        #block does not currently exist at this folder
        else:
            exists = False
            #check if trying to use code from a remote repository
            if(remote != None):
                #make sure repository is not empty
                if(Git.isValidRepo(remote, remote=True) and Git.isBlankRepo(remote) == False):
                    #create and clone to temporary spot
                    tmp = apt.makeTmpDir()
                    Git(tmp, clone=remote)

                    #check if there is a block.cfg file here
                    for f in os.listdir(tmp):
                        if(f == apt.MARKER):
                            #print('a block file exists!')
                            exists = True
                            break

                    #check to make sure a valid title was given (repo coverage)
                    if(exists == False and self.validTitle(title) == False):
                            return False

                    #move folder contents to metadata
                    self._repo = Git(self.getPath(), clone=tmp)
                    #clean up temporary spot
                    apt.cleanTmpDir()
                    pass

            #check to make sure a valid title was given (non-remote coverage)
            if(exists == False and self.validTitle(title) == False):
                return False

            #create a Block.cfg file
            if(exists == False):
                self.initMeta()

            #load the new metadata
            self.loadMeta()

            #input all title components into metadata
            if(exists == False):
                M,L,N,_ = Block.snapTitle(title)
                self.setMeta('vendor', M)
                self.setMeta('library', L)
                self.setMeta('name', N)
            pass

        #create a git repository if DNE
        if(Git.isValidRepo(self.getPath()) == False):
            self._repo = Git(self.getPath())

        #perform safety measurements
        self.secureMeta()

        #check if trying to configure the remote for not already initialized block
        if(remote != None and already_valid == False):
            #set the remote URL
            if(fork == False):
                self._repo.setRemoteURL(remote)
                #update metadata if successfully set the url
                self.setMeta("remote", self._repo.getRemoteURL())
            #clear the remote url from this repository
            else:
                self._repo.setRemoteURL('', force=True)
                #update metadata if successfully cleared the url
                self.setMeta("remote", self._repo.getRemoteURL())
                pass

        #check if trying to configure the summary
        if(summary != None):
            self.setMeta("summary", summary)
        
        self.save(force=True)

        #if not previously already valid, add and commit all changes
        if(already_valid == False):
            if(hasattr(self, "_repo") == False):
                self._repo = Git(self.getPath())
            self._repo.add('.')
            self._repo.commit('Initializes legohdl block')
            self._repo.push()

        #operation was successful
        return True


    def fillPlaceholders(self, path, template_val, extra_placeholders=[]):
        '''
        Replace all placeholders in a given file.

        Parameters:
            path (str): the file path who's data to be transformed
            template_val (str): the value to replace the word "template"
            extra_placeholders ([(str, str)]]): additional placeholders to find/replace
        Returns:
            success (bool): determine if operation was successful
        '''
        #make sure the file path exists
        if(os.path.isfile(path) == False):
            log.error(path+" does not exist.")
            return False

        placeholders = self.getPlaceholders(template_val)

        #go through file and update with special placeholders
        fdata = []
        with open(path, 'r') as rf:
            lines = rf.readlines()
            for l in lines:
                for ph in placeholders:
                    #print(ph[0], ph[1])
                    l = l.replace(ph[0], ph[1])
                fdata.append(l)
            rf.close()
        
        #write new lines
        with open(path, 'w') as wf:
            for line in fdata:
                wf.write(line)
            wf.close()

        #replace all file name if contains the word 'TEMPLATE'
        #get the file name
        base_path,fname = os.path.split(path)

        #replace 'template' in file name
        fname_new = fname.replace('TEMPLATE', template_val)
        if(fname != fname_new):
            os.rename(base_path+"/"+fname, base_path+"/"+fname_new)

        #operation was successful
        return True


    @classmethod
    def validTitle(cls, title):
        '''
        Checks if the given title is valid; i.e. it has a least a library and
        name, and it is not already taken.

        Parameters:
            title (str): M.L.N.V format
        Returns:
            valid (bool): determine if the title can be used
        '''
        valid = True

        M,L,N,V = Block.snapTitle(title)

        if(valid and N == ''):
            log.error("Block must have a name component.")
            valid = False
        if(valid and L == ''):
            log.error("Block must have a library component.")
            valid = False

        return valid


    def getMeta(self, key=None, every=False, sect='block'):
        '''
        Returns the value stored in the block metadata's requested key. 
        
        If the key DNE, then it retuns None.
        Returns a (list) for 'requires', 'vhdl-units', 'vlog-units', and 'versions' key under sect='block'.

        Parameters:
            key (str): the case-sensitive key to the cfg dictionary
            all (bool): return entire dictionary
            sect (str): the cfg header that key belongs to in the dictionary
        Returns:
            val (str): the value behind the corresponding key
        '''
        #return everything, even things outside the block: scope
        if(every):
            return self._meta._data #note: returns obj reference
        #return an entire section
        if(key == None):
            return self._meta.get(sect, dtype=Section)

        #auto-cast requirements to list
        dtype = list if(sect == 'block' and (key == 'requires' or key == 'vhdl-units' or key == 'vlog-units' or key == 'versions')) else str
        #access the key
        return self._meta.get(sect+'.'+key, dtype=dtype)


    def setMeta(self, key, value, sect='block'):
        '''
        Updates the block metatdata dictionary. If the key does not exist,
        one will be created.
        
        Parameters:
            key (str): key within sect that covers the value in dictionary
            value (str): value to be at location key
            sect (str): the cfg section header that key belongs to
        Returns:
            None
        '''
        self._meta.set(sect+'.'+key, value)
        pass


    def isValid(self):
        '''Returns true if the requested project folder is a valid block.'''
        return os.path.isfile(self.getMetaFile())


    def getMetaFile(self):
        '''Return the path to the marker file.'''
        return self.getPath()+apt.MARKER

    
    def getRequiresCode(self):
        '''Returns a (str) representing how this block was used.'''
        if(self.getLvl() == Block.Level.DNLD):
            return 'unstable'
        elif(self.getLvl() == Block.Level.INSTL):
            return 'latest'
        elif(self.getLvl() == Block.Level.VER):
            #extract partial version
            path,partial = os.path.split(self.getPath()[:len(self.getPath())-1])
            return partial
        else:
            return 'v'+self.getVersion()


    def getPlaceholders(self, tmp_val):
        '''
        Returns a dictionary of placeholders and their values.

        Parameters:
            tmp_val (str): value for "TEMPLATE" placeholder
        Returns:
            ([(str, str)]): placeholders and their respective values in tuples
        '''
        #determine the date
        today = date.today().strftime("%B %d, %Y")

        phs = [
            ("TEMPLATE", tmp_val), \
            ("%DATE%", today), \
            ("%AUTHOR%",  apt.getAuthor())
        ]

        if(hasattr(self, "_meta")):
            phs += [
                ("%BLOCK%", self.getFull())
            ]

        #get placeholders from settings (one-level section)
        custom_phs = apt.CFG.get('placeholders', dtype=Section)
        for ph in custom_phs.values():
            #ensure no '%' first exist
            ph._name = ph._name.replace('%','')
            #add to list of placeholders
            phs += [('%'+ph._name.upper()+'%', ph._val)]
        #print(phs)
        return phs


    def openInEditor(self):
        '''Opens this block with the configured text-editor.'''
        log.info("Opening "+self.getTitle_old()+" at... "+self.getPath())
        apt.execute(apt.getEditor(), self.getPath())
        pass


    def isCorrupt(self, ver, disp_err='installed'):
        '''
        Determines if the given block's requested version/state is corrupted
        or can be used.

        If disp_err is an empty str, it will not print an errory message.
        
        Parameters:
            ver (str): version under test in proper format (v0.0.0)
            disp_err (str): the requested command that cannot be fulfilled
        Returns:
            corrupt (bool): if the metadata is invalid for a release point
        '''
        corrupt = False

        if(self.isValid() == False):
            corrupt = True
        else:
            #check all required fields are in metadata
            for f in Block.REQ_KEYS:
                if(f not in self._meta.get('block', dtype=Section).keys()):
                    log.error("Missing required metadata key: "+f)
                    corrupt = True
                    break
                elif((f == 'name' or f == 'library') and self.getMeta(f) == ''):
                    log.error("Cannot have empty metadata key: "+f)
                    corrupt = True
                    break
                pass

        #ensure the latest tag matches the version found in metadata (valid release)
        if(not corrupt and ver[1:] != self.getVersion()):
            corrupt = True

        if(len(disp_err) and corrupt):
            log.error("Block's version "+ver+" is corrupted and cannot be "+disp_err+".")

        return corrupt


    def installReqs(self, tracking=[]):
        '''
        Recursive method to install all required blocks.

        Parameters:
            tracking ([string]): list of already installed requirements
        Returns:
            None
        '''
        if(len(tracking) == 0):
            log.info("Collecting requirements...")

        for title in self.getMeta('requires'):
            #skip blocks already identified for installation
            if(title.lower() in tracking):
                continue
            #update what blocks have been identified for installation
            tracking += [title.lower()]

            #break titles into discrete sections
            #print(title)
            M,L,N,V = Block.snapTitle(title)
            #snap version
            at_sym = V.find('@')
            spec_ver = V[at_sym+1:]
            v_ref = V[:at_sym-1].split('-')
            V = spec_ver
            #print(v_ref)

            #get the block associated with the title
            b = self.getWorkspace().shortcut(M+'.'+L+'.'+N, visibility=False)
            #check if the block was found in the current workspace
            if(b == None):
                log.error("Missing block requirement "+title+".")
                continue

            #recursively install requirements
            b.installReqs(tracking)

            #check if an installation already exists
            instllr = b.getLvlBlock(Block.Level.INSTL)
            #install main cache block
            if(instllr == None):
                instllr = b.install()
            #check what versions are already installed
            ready_vers = instllr.getInstalls()

            #cross-compare against what version constraints are required by the design to avoid unnecessary installs
            all_here = True
            for temp_ver in v_ref:
                #latest exists as it was installed if previously DNE
                if(temp_ver.lower() == 'latest'):
                    log.info("Found "+b.getFull()+"(@"+temp_ver+") already satisfied as v"+instllr.getVersion()+".")
                    continue
                #missing a used version and must fill the gap
                if(temp_ver not in ready_vers.keys()):
                    all_here = False
                    log.info("Missing "+b.getFull()+"(@"+temp_ver+"). Using "+V+" to satisfy constraint.")
                #the version constraint was found using a specific version
                else:
                    log.info("Found "+b.getFull()+"(@"+temp_ver+") already satisfied as v"+ready_vers[temp_ver].getVersion()+".")
                pass

            #install specific version block to cache if a constraint was missing
            if(all_here == False):
                instllr.install(ver=V)
            else:
                pass
            pass
        pass


    def install(self, ver=None):
        '''
        Installs this block to the cache. 
        
        If the block has DNLD or AVAIL status, it will install the 
        'latest'/main cache block. If the block has INSTL status, it will install 
        the version according to the 'ver' parameter. Returns None if failed.

        If the block's latest is asking to be installed and it is behind (already
        installed), this method will act as an update to get the latest version 
        up-to-date.

        Parameters:
            ver (str): a valid version format
        Returns:
            (Block): the newly installed block. 
        '''
        #determine if looking to install main cache block
        if(self.getLvl() == Block.Level.DNLD or \
            self.getLvl() == Block.Level.AVAIL):
            log.info("Installing latest version v"+self.getVersion()+" for "+self.getFull()+" to cache...")

            #if a remote is available clone to tmp directory
            rem = self.getMeta('remote')
            if(Git.isValidRepo(rem, remote=True)):
                Git(apt.TMP, clone=rem)
            #else clone the downloaded block to tmp directory
            elif(self.getLvl() == Block.Level.DNLD):
                Git(apt.TMP, clone=self.getPath())
            else:
                log.error("Cannot access block's repository.")
                return None

            #get block's latest release point
            tmp_block = Block(apt.TMP, self.getWorkspace(), lvl=Block.Level.TMP)
            latest_ver = tmp_block.getHighestTaggedVersion()

            #ensure the block has release points (versions)
            if(latest_ver == Block.NULL_VER):
                log.error("This block cannot be installed because it has no release points.")
                apt.cleanTmpDir()
                return None
            
            #checkout from latest legohdl version tag (highest version number)
            tmp_block._repo.git('checkout','tags/'+latest_ver+apt.TAG_ID)

            #make sure block's state is not corrupted
            if(tmp_block.isCorrupt(latest_ver)):
                apt.cleanTmpDir()
                return None

            #delete old installation if exists
            if(self.getLvlBlock(Block.Level.INSTL) != None):
                self.getLvlBlock(Block.Level.INSTL).delete()
            
            #create new cache directory location
            rail = self.M() if(self.M() != '') else '_'
            block_cache_path = self.getWorkspace().getCachePath()+rail+'/'+self.L()+'/'+self.N()+'/'

            os.makedirs(block_cache_path, exist_ok=True)

            #clone git repository to new cache directory
            Git(block_cache_path+self.N(), clone=apt.TMP)

            #clean up tmp directory
            apt.cleanTmpDir()

            #create new block installed block
            instl_block = Block(block_cache_path+self.N(), ws=self.getWorkspace(), lvl=Block.Level.INSTL)

            #make files read-only
            instl_block.modWritePermissions(False)

            log.info("Installation size: "+str(instl_block.getSize())+" KB.")

            #install requirements for this block
            instl_block.installReqs()

            log.info("Success.")
            #return the installed block for potential future use
            return instl_block

        #make sure trying to install a specific 'side' version
        elif(self.getLvl() != Block.Level.INSTL):
            return None

        #ensure version argument has a v prepended
        ver = Block.stdVer(ver, add_v=True)

        #make sure the version is valid
        if(ver not in self.getTaggedVersions()):
            log.error("Version "+ver+" does not exist for "+self.getFull()+".")
            return None
        #make sure the version is not already installed
        if(ver in self.getInstalls(returnvers=True)):
            log.info("Version "+ver+" is already installed for "+self.getFull()+".")
            return None

        log.info("Installing "+self.getFull()+'('+ver+')...')

        #make files write-able
        self.modWritePermissions(True)

        #install the specific version
        b = self.installPartialVersion(ver, places=3)

        #failed if block was corrupted
        if(b == None):
            return b

        #try to update the sub-version associated with this specific version
        self.installPartialVersion(ver, places=1)

        self.installPartialVersion(ver, places=2)

        #re-disable write permissions for installation block
        self.modWritePermissions(False)

        #install requirements for this block
        b.installReqs()

        log.info("Success.")
        return b


    def installPartialVersion(self, ver, places=1):
        '''
        Updates the sub-version to the latest applicable version ver, if
        it exceeds the existing version in sub-version.

        Parameters:
            ver (str): proper version format under test (v0.0.0)
            places (int): number of version sections to evaluate
        Returns:
            (Block): the specific version block installed
        '''
        #clear the jar to act on clean unit data structures for next install
        Unit.resetJar()

        parts = ver.split('.')
        sub_ver = apt.listToStr(parts[:places], delim='.')
        #print(sub_ver)

        #check if the sub version is already installed
        if(sub_ver in self.getInstalls(returnvers=True)):
            #get the version already standing in this subversion spot
            standing_block = self.getInstalls()[sub_ver]
            cur_ver = standing_block.getMeta('version')
            #compare version under test with version here
            if(self.cmpVer(ver, cur_ver) == cur_ver):
                #do not overwrite the version here if 'cur_ver' is greater
                return None
            log.info("Updating partial version "+sub_ver+" from "+cur_ver+" to "+ver+"...")
            #delete old block in this place to install bigger version 'ver'
            standing_block.delete()
        elif(places < 3):
            log.info("Installing partial version "+sub_ver+" as "+ver+"...")

        #proceed to create sub version 

        #create cache directory based on this block's path
        cache_path = self.getPath()+'../'+sub_ver+'/'

        #checkout the correct version
        self._repo.git('checkout','tags/'+ver+apt.TAG_ID)

        #copy in all files from self
        shutil.copytree(self.getPath(), cache_path)

        #delete all files not ending in a supported source code extensions if
        #its a partial version (places < 3)
        if(places < 3):
            all_files = glob.glob(cache_path+"**/*", recursive=True)
            for f in all_files:
                if(os.path.isfile(f) == False):
                    continue
                #get file extension
                _,ext = os.path.splitext(f)
                #get file name (+ extension)
                _,fname = os.path.split(f)
                #keep metadata file
                if(fname == 'Block.cfg'):
                    continue
                #check if extension is one of supported HDL source codes
                if('*'+ext.lower() not in apt.SRC_CODE):
                    os.remove(f)

        #delete specific version's git repository data
        repo = Git(cache_path)
        repo.delete()
        
        #create new block object as a specific version in the cache
        b = Block(cache_path, ws=self.getWorkspace(), lvl=Block.Level.VER)

        #revert last checkout to latest version
        self._repo.git('checkout','-')

        #make sure block's state is not corrupted
        if(b.isCorrupt(ver)):
            shutil.rmtree(cache_path, onerror=apt.rmReadOnly)
            return None

        #get all unit names
        unit_names = b.getUnits(top=None, recursive=False)
        #store the pairs of unit names to find/replace
        mod_unit_names = []
        #store what language objects will need to swap unit names
        lang_files = [] 

        vhdl_units = []
        vlog_units = []
        #iterate through every unit to create find/replace pairings
        for key,u in unit_names.items():
            mod_unit_names += [[key, key+'_'+sub_ver.replace('.','_')]]
            #add its file to the list if not already included
            if(u.getLanguageFile() not in lang_files):
                lang_files += [u.getLanguageFile()]
            if(u.getLang() == Unit.Language.VHDL):
                vhdl_units += [mod_unit_names[-1][1]]
            elif(u.getLang() == Unit.Language.VERILOG):
                vlog_units += [mod_unit_names[-1][1]]

        #modify all entity/unit names within the specific version to reflect
        #that specific version
        for f in lang_files:
            f.swapUnitNames(mod_unit_names)

        #alter fields for toplevel and bench
        for n in mod_unit_names:
            if(b.getMeta('toplevel') != None and n[0].lower() == b.getMeta('toplevel').lower()):
                b.setMeta('toplevel', n[1])
            if(b.getMeta('bench') != None and n[0].lower() == b.getMeta('bench').lower()):
                b.setMeta('bench', n[1])

        #add VHDL units and Verilog units to metadata
        b.setMeta('vhdl-units', vhdl_units)
        b.setMeta('vlog-units', vlog_units)

        b.save(force=True)

        #disable write permissions for specific version block
        b.modWritePermissions(False)

        log.info("Installation size: "+str(b.getSize())+" KB.")

        return b

    
    def uninstall(self, ver):
        '''
        Uninstall the given block from the cache using its INSTL status block.
        
        Also uninstalls a specific version passed by 'ver', and updates partial
        versions when needed.

        Parameters:
            ver (str): version in proper format (v0.0.0)
        Returns:
            (bool): determine if the operation was successful
        '''
        instl = self.getLvlBlock(Block.Level.INSTL)
        #make sure the block is installed
        if(instl == None):
            log.error("Block "+self.getFull()+" is not installed to the cache!")
            return False

        #get the map for what versions exist in cache for this block
        installations = instl.getInstalls()
        uninstallations = Map()
        #scale down to only version
        if(ver != None):
            #ensure version is standardized
            ver = Block.stdVer(ver, add_v=True)

            parts = ver.split('.')
            for v in installations.keys():
                v_parts = v.split('.')
                skip = False
                for i in range(len(parts)):
                    #skip if did not specify enough or parts do not equal
                    if((i >= len(v_parts) and i < len(parts)) or v_parts[i] != parts[i]):
                        skip = True
                        break
                if(skip):
                    continue
                #print(v)
                uninstallations[v] = installations[v]
                pass
            #check if any versions were captured in algorithm
            if(len(uninstallations) == 0):
                log.error("Version "+ver+" may not exist or be installed to the cache!")
                return False
        #includes latest and everything else
        else:
            uninstallations = installations
            uninstallations['latest'] = instl

        #display helpful information to user about what installations will be deleted
        print("From "+self.getFull()+" would remove: \n\t" + \
            apt.listToStr(list(uninstallations.keys()),'\n\t'))

        #prompt to verify action
        yes = apt.confirmation('Proceed to uninstall?',warning=False)
        if(yes == False):
            log.info("Cancelled.")
            return False

        #iterate through every installation to uninstall
        for i in uninstallations.values():
            if(i == instl):
                continue
            print("Uninstalled "+i.getFull(inc_ver=True))
            #delete specific version from cache
            i.delete()
            #:todo: make sure to see if a partial version needs updating (either removed or different version holds it)
            pass

        #remove this block's cache path name if uninstalling the main cache block
        if(instl in uninstallations.values()):
            instl.delete(squeeze=3)

        return True
    

    def save(self, force=False):
        '''
        Write the metadata back to the marker file only if the data has changed
        since initializing this block as an object in python.

        Parameters:
            force (bool): determine if to save no matter _meta_backup status
        Returns:
            success (bool): returns True if the file was written and saved.
        '''
        #do no rewrite meta data if nothing has changed
        if(force == False and self.loadMeta()._modified == False):
            return False

        #rewrite requirements
        self._meta.set('block.requires', Cfg.castList(self._meta.get('block.requires')))
        
        self._meta.write(auto_indent=False)
        return True


    def modWritePermissions(self, enable, path=None):
        '''
        Disable modification/write permissions of all files specified on this
        block's path.

        Hidden files do not get their write permissions modified.

        Parameters:
            enable (bool): determine if files to have write permissions
            path (str): optional path to override default path
        Returns:
            None
        '''
        if(path == None):
            path = self.getPath()
        
        all_files = glob.glob(path+"**/*.*", recursive=True)

        for f in all_files:
            #get current file permissions
            cur_permissions = stat.S_IMODE(os.lstat(f).st_mode)
            if(enable):
                #get write masks and OR with current permissions
                w_permissions = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
                os.chmod(f, cur_permissions | w_permissions)
            else:
                #flip write masks and AND with current permissions
                w_permissions = ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH
                os.chmod(f, cur_permissions & w_permissions)
            pass
        pass


    def updateRequires(self, quiet=False, dry_run=False):
        '''
        Updates the metadata section 'requires' for required blocks needed by
        the current block.

        Only lists the 1st level direct block requirements. These are the neighbors
        in a block graph for this block's vertex.

        Parameters:
            quiet (bool): determine if to display messages to the user
            dry_run (bool): determine if to save any changes (False)
        Returns:
            [(str)] : list of block requirements
        '''
        if(not quiet):
            log.info("Updating block's requirements...")
        #get every unit from this block
        units = self.getUnits(top=None)

        block_reqs = []
        direct_reqs = []
        #get the list of direct requirements
        for u in units.values():
            direct_reqs += u.getReqs()

        #for each direct required unit, add its block
        for dr in direct_reqs:
            if(dr.getLanguageFile().getOwner() not in block_reqs):
                block_reqs += [dr.getLanguageFile().getOwner()]
        #print(block_reqs)
        #store block titles in a map to compare without case sense
        block_titles = Map()

        block_requires = Map()
        for bd in self.getMeta('requires'):
            block_requires[bd] = bd

        #iterate through every block requirement to add its title
        for b in block_reqs:
            #skip listing itself as block dependency
            if(b == self):
                continue
            #add how it was used (latest, unstable, v1, etc.)
            #print(b.getRequiresCode())
            if(b.getFull(inc_ver=True).lower() not in block_titles.keys()):
                block_titles[b.getFull(inc_ver=True)] = [b, []]
            block_titles[b.getFull(inc_ver=True)][1] += [b.getRequiresCode()]
            pass

        #formulate each block identifier into a complete str
        block_ids = Map()
        for b,parts in block_titles.items():
            b_obj = parts[0]
            identifier = b_obj.getFull(inc_ver=True, vers=parts[1])
            block_ids[identifier] = identifier

        update = False
        
        #update if the length of the dependencies has changed
        if(len(block_requires) != len(block_ids)):
            update = True

        #iterate through every already-listed block derivative
        for b in block_requires.keys():
            if(b not in block_ids.keys()):
                update = True
                break

        #iterate through every found block requirement
        for b in block_ids.keys():
            if(b not in block_requires.keys()):
                update = True
                break

        #update the metadata for requirements
        if(update and dry_run == False):
            if(not quiet):
                log.info("Saving new requirements to metadata...")
            #save the changes for the real deal
            self.setMeta('requires', list(block_ids.values()))
            self.save()
            pass
        #inform user that no changes to metadata occurred for block requirements
        elif(quiet == False):
            if(update):
                log.info("Detected changes in block requirements.")
            else:
                log.info("No change in block requirements found.")
            pass
        #return list of block requirements
        return list(block_ids.values())


    def gatherSources(self, ext=apt.SRC_CODE, path=None):
        '''
        Return all files associated with the given extensions from the specified
        path. Ignores the build/ directory directly within a block's path.

        Parameters:
            ext  ([str]): a list of extensions (use * to signify all files of given ext)
            path (str) : where to begin searching for files. Defaults to block's path.
        Returns:
            srcs ([str]): a list of files matching the given ext's
        '''
        if(path == None):
            path = self.getPath()

        srcs = []
        #ignores build folder with filter
        bd = apt.getBuildDirectory()
        #automatically does case insensitivity on glob for windows os
        for e in ext:
            srcs = srcs + glob.glob(path+"/**/"+e, recursive=True)
            pass

        #omit build/ files
        srcs = list(filter(lambda p : apt.fs(p).count(path+bd) == 0, srcs))
        #print(srcs)

        return srcs


    @classmethod
    def snapTitle(cls, title, inc_ent=False, delim='.'):
        '''
        Break a title into its 4 components, if possible. Returns M,L,N,V as
        strings. Returns '' for each missing part.

        Parameters:
            title (str): the string to be parsed into title components
            inc_ent (bool): also return the entity name if found
        Returns:
            M (str): block vendor
            L (str): block library
            N (str): block name
            V (str): block version
            E (str): entity in the title if inc_ent is True
        '''
        if(title == None):
            if(inc_ent):
                return '','','','','' #return 5 blanks
            return '','','','' #return 4 blanks
        V = ''
        #:todo: will not work if (v1.0.0):adder (version and entity together)
        #find version label if possible
        v_index = title.rfind('(')
        if(v_index > -1):
            V = cls.stdVer(title[v_index+1:-1])
            title = title[:v_index]

        #split into pieces
        pieces = title.split(delim)
        sects = ['']*3
        diff = 3 - len(pieces)
        for i in range(len(pieces)-1, -1, -1):
            sects[diff+i] = pieces[i]
        #check final piece if it has an entity attached
        entity = ''
        if(sects[2].count(apt.ENTITY_DELIM)):
            i = sects[2].find(apt.ENTITY_DELIM)
            entity = sects[2][i+1:]
            sects[2] = sects[2][:i]
        #assume only name given is actually the entity
        elif(inc_ent):
            entity = sects[2]
            sects[2] = ''
        if(inc_ent):
            return sects[0],sects[1],sects[2],V,entity

        return sects[0],sects[1],sects[2],V


    def identifyTop(self, verbose=True):
        '''
        Auto-detects the top-level design entity. Returns None if not found.

        Parameters:
            verbose (bool): determine if to print info
        Returns:
            self._top (Unit): unit object that is the top-level for this block
        '''
        #return if already identified
        if(hasattr(self, "_top")):
            return self._top
    
        self._top = None
        #constrain to only current block's units and fill out data on each unit
        units = self.getUnits(recursive=False)
        #get the names of each unit available
        top_contenders = list(units.keys())
        #iterate through each unit and eliminate unlikely top-levels
        for name,unit in units.items():
            #if the entity is value under this key, it is lower-level
            if(unit.isTb() or unit.isPkg()):
                if(name in top_contenders):
                    top_contenders.remove(name)
                continue
                
            for dep in unit.getReqs():
                if(dep.E().lower() in top_contenders):
                    top_contenders.remove(dep.E().lower())

        if(len(top_contenders) == 0):
            if(verbose):
                log.warning("No top level detected.")
        elif(len(top_contenders) > 1):
            log.warning("Multiple top levels detected. "+str(top_contenders))
            try:
                validTop = input("Enter a valid toplevel entity: ").lower()
            except KeyboardInterrupt:
                exit("\nExited prompt.")
            while validTop not in top_contenders:
                try:
                    validTop = input("Enter a valid toplevel entity: ").lower()
                except KeyboardInterrupt:
                    exit("\nExited prompt.")
            
            top_contenders = [validTop]
        #detected a single top-level design unit
        if(len(top_contenders) == 1):
            self._top = units[top_contenders[0]]
            if(verbose):
                log.info("Identified top-level unit: "+self._top.E())
            pass

        return self._top


    def identifyBench(self, entity_name, expl=None, verbose=True):
        '''
        Determine what testbench is used for the top-level design entity (if 
        found). Returns None if not found.

        Parameters:
            entity_name (str): name of entity to be under test
            expl (str): the name of the testbench (if explicitly stated)
            verbose (bool): determine if to print info to console
        Returns:
            self._bench (Unit): testbench unit object
        '''
        #return if already identified
        if(hasattr(self, "_bench")):
            return self._bench

        self._bench = None 
        #load all project-level units
        units = self.getUnits(recursive=False)            

        benches = []
        #iterate through each available unit and eliminate it
        for unit in units.values():
            for dep in unit.getReqs():
                if(dep.E().lower() == entity_name and unit.isTb()):
                    benches.append(unit)
            pass

        #try to find explicit testbench
        if(expl != None):
            benches = []
            if(expl.lower() in units.keys()):
                benches = [units[expl]]
            pass             

        #perfect; only 1 was found  
        if(len(benches) == 1):
            self._bench = benches[0]
        #prompt user to select a testbench
        elif(len(benches) > 1):
            top_contenders = []
            for b in benches:
                top_contenders.append(b.E())
            log.warning("Multiple top level testbenches detected. "+str(top_contenders))
            try:
                validTop = input("Enter a valid toplevel testbench: ").lower()
            except KeyboardInterrupt:
                exit("\nExited prompt.")
            #force ask for the required testbench choice
            while validTop not in top_contenders:
                try:
                    validTop = input("Enter a valid toplevel testbench: ").lower()
                except KeyboardInterrupt:
                    exit("\nExited prompt.")
            #assign the testbench entered by the user
            self._bench = units[validTop]
        #print what the detected testbench is
        if(verbose):
            if(self._bench != None):
                log.info("Identified top-level testbench: "+self._bench.E())
            else:
                log.warning("No testbench detected.")

        #return the Unit object
        return self._bench


    def identifyTopDog(self, top=None, expl_tb=None, inc_tb=True, verbose=True):
        '''
        Determine what unit is utmost highest, whether it be a testbench
        (if applicable) or entity. Returns None if DNE.

        Parameters:
            top (str): a unit identifier
            expl_tb (str): a unit identifier to be the testbench
            inc_tb (bool): determine if to include testbench files
            verbose (bool): determine if to print info to console
        Returns:
            top_dog (Unit): top-level everything
            top_dsgn (Unit): top-level design unit
            top_tb (Unit): top-level testbench for top unit
        '''
        #make sure entities exist to search for
        units = self.getUnits(recursive=False)
        if((top == None or top == '') and len(units) == 0):
            exit(log.error("There are no available units in this block."))

        top_dog = top_dsgn = top_tb = None
        #find top if given
        if(top != None and top != '' and top.lower() in units.keys()):
            top_dog = units[top]
            #assign as testbench if it is one
            if(top_dog.isTb()):
                top_tb = top_dog
            #assign as design otherwise
            elif(top_dog != None):
                top_dsgn = top_dog
                #auto-detect the testbench
                if(inc_tb):
                    top_tb = self.identifyBench(top_dsgn.E(), expl=expl_tb, verbose=verbose)
                    #set top_dog as the testbench if found one and allowed to be included
                    if(top_tb != None):
                        top_dog = top_tb
                    pass
            #reset graph
            Unit.resetHierarchy()
            return top_dog,top_dsgn,top_tb
        #could not find requested unit
        elif(top != None and top != ''):
            exit(log.error("Entity "+top+" does not exist within this block."))

        #auto-detect the top level design
        top_dsgn = self.identifyTop(verbose=verbose)
        
        if(top_dsgn != None and inc_tb):
            #auto-detect the top level's testbench
            top_tb = self.identifyBench(top_dsgn.E(), expl=expl_tb, verbose=verbose)

        #set top_dog as the testbench if found one and allowed to be included
        if(top_tb != None and inc_tb):
            top_dog = top_tb
        else:
            top_dog = top_dsgn

        #reset graph
        Unit.resetHierarchy()
        
        return top_dog,top_dsgn,top_tb


    def getFull(self, inc_ver=False, vers=[]):
        '''
        Returns nicely formatted block title (str).
        
        Parameters:
            inc_ver (bool): determine if to include the version
            vers ([str]): list of version to add as chain when including versions
        Returns:
            (str): formatted block identifier
        '''
        # :todo: store MLNV as tuple and use single function for full-access
        title = ''
        #prepend vendor if not blank
        if(self.M() != ''):
            title = self.M()+'.'
        #join together library and name
        title = title+self.L()+'.'+self.N()
        #append version if requested
        if(inc_ver):
            #describe which versions were based from specific version
            v_chain = '@'+self.V()
            #sort versions
            vers = self.sortVersions(vers)
            for v in vers:
                v_chain = v + '-' + v_chain
            # ignore chain when only a single version was used
            # if(vers = [self.V()]):
            #     v_chain = self.V()
            title = title+"("+v_chain+")"
        return title


    def M(self):
        '''Returns _M (str) attr vendor.'''
        if(hasattr(self, "_M")):
            return self._M 
        #read from metadata
        self._M = self.getMeta('vendor')
        if(self._M == None):
            self._M = ''
        return self._M


    def L(self):
        '''Returns _L (str) attr block library.'''
        if(hasattr(self, "_L")):
            return self._L
        #read from metadata
        self._L = self.getMeta('library')
        return self._L 
    

    def N(self):
        '''Returns _N (str) attr project name.'''
        if(hasattr(self, "_N")):
            return self._N 
        #read from metadata
        self._N = self.getMeta('name')
        return self._N


    def V(self):
        '''Returns _V (str) attr proper version format (v0.0.0).'''
        if(hasattr(self, "_V")):
            return self._V
        #read from metadata
        self._V = 'v'+self.getMeta('version')
        return self._V


    @DeprecationWarning
    def getLangUnitCount(self):
        '''
        Returns the amount of units coded in either VHDL or VERILOG.
        
        Parameters:
            None
        Returns:
            vhdl_cnt (int): number of vhdl units
            vlog_cnt (int): number of vlog units
        '''
        dsgns = self.loadHDL().values()

        vhdl_cnt = 0
        vlog_cnt = 0
        #iterate through each design and tally if the unit is VHDL
        for dsgn in dsgns:
            if(dsgn.getLang() == Unit.Language.VHDL):
                vhdl_cnt += 1
            elif(dsgn.getLang() == Unit.Language.VERILOG):
                vlog_cnt += 1

        return vhdl_cnt, vlog_cnt


    def loadHDL(self, returnnames=False, lang=''):
        '''
        Identify all HDL files within the block and all designs in each file.

        Only loads from HDL once and then will dynamically return its attr _units. If
        'returnnames' is set, then it will skip the attr and first try to find if 'vhdl-units'
        or 'vlog-units' exists in metadata and return the names found there.
        
        Parameters:
            returnnames (bool): determine if to return list of names
            lang (str): filter based on HDL coding language ('vhdl' or 'vlog')
        Returns:
            self._units (Map): the Unit Map object down to M/L/N level
            or
            ([str]): list of unit names if returnnames is True
        '''
        if(returnnames and self.getLvl() != Block.Level.DNLD and self.getLvl() != Block.Level.INSTL):
            unit_names = []
            if(self.getMeta('vhdl-units') != None):
                unit_names += self.getMeta('vhdl-units')
            if(self.getMeta('vlog-units') != None):
                unit_names += self.getMeta('vlog-units')
            if(len(unit_names)):
                return unit_names

        if(hasattr(self, "_units")):
            if(lang != ''):
                #filter between vhdl or verilog units
                tmp_fltr = []
                if(lang.lower() == 'vhdl'):
                    tmp_fltr = list(filter(lambda a: a[1].getLang() == Unit.Language.VHDL, self._units.items()))
                elif(lang.lower() == 'vlog'):
                    tmp_fltr = list(filter(lambda a: a[1].getLang() == Unit.Language.VERILOG, self._units.items()))
                #compile into a Map
                tmp = Map()
                for u in tmp_fltr:
                    tmp[u[0]] = u[1]
                #only return the keys (names)
                if(returnnames):
                    tmp = [u.E() for u in tmp.values()]
                return tmp

            if(returnnames):
                return [u.E() for u in self._units.values()]
            return self._units

        self._hdl_files = []
        #open each found source file and identify their units
        #load all VHDL files
        vhd_files = self.gatherSources(apt.VHDL_CODE, path=self.getPath())
        for v in vhd_files:
            self._hdl_files += [Vhdl(v, self)]
        #load all VERILOG files
        verilog_files = self.gatherSources(apt.VERILOG_CODE, path=self.getPath())
        for v in verilog_files:
            self._hdl_files += [Verilog(v, self)]

        #check if the level exists in the Jar
        if(Unit.jarExists(self.M(), self.L(), self.N())):
            self._units = Unit.Jar[self.M()][self.L()][self.N()]
        else:
            self._units = Map()

        if(lang != ''):
            #filter between vhdl or verilog units
            tmp_fltr = []
            if(lang.lower() == 'vhdl'):
                tmp_fltr = list(filter(lambda a: a[1].getLang() == Unit.Language.VHDL, self._units.items()))
            elif(lang.lower() == 'vlog'):
                tmp_fltr = list(filter(lambda a: a[1].getLang() == Unit.Language.VERILOG, self._units.items()))
            #compile into a Map
            tmp = Map()
            for u in tmp_fltr:
                tmp[u[0]] = u[1]
            #only return the keys (names)
            if(returnnames):
                return [u.E() for u in self._units.values()]
            return tmp
            
        if(returnnames):
            return [u.E() for u in self._units.values()]
        return self._units

    
    def getUnits(self, top=None, recursive=True):
        '''
        Returns a map for all filled HDL units found within the given block.
        
        If a top is specified, it will start deciphering from that Unit. Else, all
        HDL files within the block will be deciphered.

        If recursive is set, it will recursively decode entities upon finding them
        when decoding an architecture.

        Parameters:
            top (Unit): unit object to start with
            recursive (bool): determine if to tunnel through entities
        Returns:
            units (Map): the Unit Map object down to M/L/N level
        '''
        units = self.loadHDL()

        if(top != None and top in units.values()):
            if(top.isChecked() == False):
                top.getLanguageFile().decode(top, recursive)
        else:
            for u in units.values():
                if(u.isChecked() == False):
                    u.getLanguageFile().decode(u, recursive)
        #self.printUnits()
        return units


    def printUnits(self):
        for u in self._units.values():
            print(u)


    @classmethod
    def getAllBlocks(cls):
        '''Returns _all_blocks ([Block]) attr of every block in valid level.'''
        if(hasattr(cls, '_all_blocks')):
            return cls._all_blocks
        cls._all_blocks = []
        for vndrs in cls.Inventory.values():
            for libs in vndrs.values():
                for blks in libs.values():
                    for lvl in blks:
                        if(lvl != None):
                            cls._all_blocks += [lvl]
                            break
                        pass
        return cls._all_blocks


    def get(self, entity, no_about, list_arch, inst, comp, lang, edges):
        '''
        Get various pieces of information about a given entity as well as any
        compatible code for instantiations.

        Parameters:
            entity (str): name of entity to be fetched
            no_about (bool): determine if to skip the about section
            list_arch (bool): determine if to list the architectures
            inst (bool): determine if to print instantiation
            comp (bool): determine if to print component declaration
            lang (str): VHDL or VLOG style language
            edges (bool): determine if to print graph information
        Returns:
            success (bool): determine if operation was successful
        '''
        #get quick idea of what units exist for this block
        units = self.loadHDL()
        #print(units)
        if(entity.lower() not in units.keys()):
            log.error("Entity "+entity+" not found in block "+self.getFull()+"!")
            return False

        def_lang = apt.CFG.get('HDL-styling.default-language').lower()

        #determine the language for outputting compatible code
        if(lang != None):
            if(lang.lower() == 'vhdl'):
                lang = Unit.Language.VHDL
            elif(lang.lower() == 'vlog'):
                lang = Unit.Language.VERILOG
            pass
        #see if a default language is set in settings
        elif(def_lang == 'vhdl'):
            lang = Unit.Language.VHDL
        elif(def_lang == 'verilog'):
            lang = Unit.Language.VERILOG

        #collect data about requested entity
        self.getUnits(top=units[entity])
        #grab the desired entity from the Map
        ent = units[entity]

        hang_end = apt.CFG.get('HDL-styling.hanging-end', dtype=bool)
        auto_fit = apt.CFG.get('HDL-styling.auto-fit', dtype=bool)
        alignment = apt.CFG.get('HDL-styling.alignment', dtype=int)
        maps_on_newline = apt.CFG.get('HDL-styling.newline-maps', dtype=int)
        inst_name = apt.CFG.get('HDL-styling.instance-name')

        g_mod = apt.CFG.get('HDL-styling.generic-modifier')
        p_mod = apt.CFG.get('HDL-styling.port-modifier')

        #swap placeholders in inst name
        for ph in self.getPlaceholders(ent.E()):
            inst_name = inst_name.replace(ph[0],ph[1])
            pass

        #print comment header (about)
        if(no_about == False):
            print("--- ABOUT ---")
            print(ent.readAbout())
        #print dependencies
        if(edges):
            print("--- EDGES ---")
            print(ent.readReqs())
            print()
            print(ent.readReqs(upstream=True))
            print()
        #print list of architectures
        if(list_arch):
            print('--- ARCHITECTURES ---')
            print(ent.readArchitectures())
        #do not continue to try to print instantiation or component code for packages
        if(ent.getDesign() == Unit.Design.PACKAGE):
            return
        if(comp or inst):
            print('--- CODE ---')
        if(comp):
            print(ent.getInterface().writeDeclaration(form=lang, \
                align=auto_fit, \
                hang_end=hang_end))
            print()
        if(inst):
            print(ent.getInterface().writeConnections(form=lang, \
                align=auto_fit, \
                g_name=g_mod, \
                p_name=p_mod))
            lib = None
            #determine the entity's library name
            if(comp == False):
                lib = ent.L()
                #try to see if within the current block (skip error)
                if(Block.getCurrent(bypass=True) != None):
                    #use 'work' if the entity is in from the current block 
                    if(ent in (Block.getCurrent().loadHDL().values())):
                        lib = 'work'

            print(ent.getInterface().writeInstance(lang=lang, \
                entity_lib=lib, \
                inst_name=inst_name, \
                fit=auto_fit, \
                hang_end=hang_end, \
                maps_on_newline=maps_on_newline, \
                alignment=alignment, \
                g_name=g_mod, \
                p_name=p_mod))

        return True


    def getSize(self):
        '''Returns Block's total file size (int) in kilobytes.'''
        #return unknown value if the block is created from 'AVAILABLE' level
        if(self.getLvl() == Block.Level.AVAIL):
            return '?'
        #returns in terms of KILOBYTES
        return round(float(apt.getPathSize(self.getPath())/1000), 2)


    def readInfo(self, stats=False, versions=False, ver_range=['0.0.0',''], see_changelog=False, 
        only_instls=False, only_avail=False):
        '''
        Return information relevant to the current block (metadata).

        Parameters:
            stats (bool): determine if to print additional stats
            versions (bool): determine if to print the available versions
            only_instls (bool): filter to only show specific version installs
            only_avail (bool): filter to only show specific versions not installed
            ver_range (str): a constraint string for how to filter available versions (v1.0.0:1.9.0)
            see_changelog (bool): determine if to read the changelog file (if exists)
        Returns:
            info_txt (str): information text to be printed to console
        '''
        #make sure the metadata is properly formatted
        self.secureMeta()

        all_versions = self._meta.get('block.versions', dtype=list)
        if(all_versions == None):
            all_versions = []

        #try to find size from file
        size = self._meta.get('block.size', dtype=str)
        #get directory's size
        if(size == None):
            size = self.getSize()

        vhdl_units = self._meta.get('block.vhdl-units', dtype=list)
        vlog_units = self._meta.get('block.vlog-units', dtype=list)

        #only print changelog information if requested
        if(see_changelog):
            info_txt = '--- CHANGELOG ---\n'
            #no changelog available (N/A)
            if(self.getChangelog() == None):
                return info_txt+'N/A'
            #dump changelog file contents to be printed
            return info_txt + apt.listToStr(open(self.getChangelog(), 'r').readlines(), '')

        #read the metadata by default
        info_txt = '--- METADATA ---\n'
        in_sect = ''
        in_key = ''
        #open and dump the metadata contents into 'info_txt'
        with open(self.getMetaFile(), 'r') as file:
            for line in file:
                #detect when entering a section
                if(len(line) > 1 and line.strip()[0] == '[' and line.strip()[-1] == ']'):
                    in_sect = line.strip()
                #detect when finding a key
                elif(line.count('=')):
                    in_key = line[:line.find('=')].strip()
                #print(in_header+'|'+in_key)
                #avoid printing extra keys in metadata section
                if(in_sect.lower() == '[block]' and in_key.lower() in Block.EXTRA_KEYS):
                    #do not write to metadata section (but do write empty lines)
                    if(len(line.strip()) > 0):
                        continue
                info_txt = info_txt + line

        #read relevant stats
        if(stats):
            info_txt = info_txt + '\n--- STATS ---'
           
            #read location
            info_txt = info_txt + '\nLocation = '+self.getPath()+'\n'
            #read size
            info_txt = info_txt + 'Size     = '+str(size)+' KB\n'
            #read workspace level
            info_txt = info_txt + 'Level    = '+str(self.getLvl().name)+'\n'
            
            #read what blocks require this block
            info_txt = info_txt + 'Required by:\n'
            block_up_reqs = Block.Hierarchy.getNeighbors(self.getFull(inc_ver=True), upstream=True)
            info_txt = info_txt + apt.listToGrid(block_up_reqs, cols=-1, limit=80, min_space=4, offset='\t')
            if(len(block_up_reqs) == 0):
                info_txt = info_txt + ' '*4 + 'N/A'
            info_txt = info_txt + '\n'

            #read the units found in this block
            if(self.getLvl() == Block.Level.DNLD or self.getLvl() == Block.Level.INSTL):
                if(vhdl_units == None):
                    vhdl_units = self.loadHDL(lang='vhdl', returnnames=True)
                if(vlog_units == None):
                    vlog_units = self.loadHDL(lang='vlog', returnnames=True)

            if(vhdl_units != None and len(vhdl_units) > 0):
                txt = '\nVHDL units:\n'
                info_txt = info_txt + txt + apt.listToGrid(vhdl_units, cols=-1, \
                    limit=80, min_space=4, offset='\t')
                
            if(vlog_units != None and len(vlog_units) > 0):
                txt = '\nVERILOG units:\n'
                info_txt = info_txt + txt + apt.listToGrid(vlog_units, cols=-1, \
                    limit=80, min_space=4, offset='\t')
            pass

        #read the list of versions implemented and obtainable
        if(versions):
            info_txt = '{:<12}'.format("Version")+' '+'{:<2}'.format("I")+' '+'{:<18}'.format("Partials")
            info_txt = info_txt + '\n' + "-"*12+" "+"-"*2+" "+"-"*18 + '\n'
            
            instl_versions = []
            #try to see if there are any installation versions
            instller = self.getLvlBlock(Block.Level.INSTL)
            if(instller != None):
                instl_versions = instller.getInstalls(returnvers=True)
                #additionally add what version the main cached block is
                instl_versions += [instller.getHighestTaggedVersion()]
                pass

            #sort the versions available in cache
            instl_versions = self.sortVersions(instl_versions)
            
            #sort the versions found on the self block
            if(len(all_versions) == 0):
                all_versions = self.sortVersions(self.getTaggedVersions())

            #try to see if there are any available versions
            avail = self.getLvlBlock(Block.Level.AVAIL)
            if(avail != None):
                avail_vers = avail.getMeta('versions')
                if(isinstance(avail_vers, list)):
                    all_versions += avail_vers
                all_versions = self.sortVersions(list(set(all_versions)))
                pass

            #track what partial versions have been identified
            logged_part_vers = []
            #iterate through all versions
            for x in all_versions:
                status = ''
                partials = []
                
                #check if this specific version is installed to cache
                if(x in instl_versions and \
                    (x != instl_versions[0] or instl_versions.count(x) > 1)):
                    status = '*'
                    #identify what version are partial versions (maj and min partials)
                    for i in range(1,3):
                        part_ver = apt.listToStr(x.split('.')[:i], delim='.')
                        if(part_ver in instl_versions and part_ver not in logged_part_vers):
                            partials += [part_ver]
                            logged_part_vers.append(part_ver)
                
                #latest is the highest version from instl_versions
                if(len(instl_versions) and x == instl_versions[0]):
                    partials += ['latest']
                
                #do not write version if constrained to list only installed specific versions
                if(only_instls and (len(status) + len(partials) == 0) and not only_avail):
                    continue

                #do not write version if constrained to list only non-installed specific versions
                if(only_avail and (len(status) + len(partials) > 0) and not only_instls):
                    continue

                #constrain to version range
                if(self.cmpVer(ver_range[0], x) == x and (ver_range[1] == '' or self.cmpVer(ver_range[1], x) == ver_range[1])):
                    pass
                #zoom to only singular version
                elif(Block.stdVer(x, rm_v=True) == ver_range[0] and ver_range[1] == '-'):
                    pass
                #do not add this version to the text
                else:
                    continue

                #add new line for next version to be formatted
                info_txt = info_txt + '{:<12}'.format(x)+' '+ \
                    '{:<2}'.format(status)+' '+ \
                    '{:<18}'.format(apt.listToStr(partials, delim=' '))
                info_txt = info_txt + '\n'
                pass
            pass

        return info_txt


    # uncomment to use for debugging
    # def __str__(self):
    #     return f'''
    #     id: {hex(id(self))}
    #     block: {self.M()+'.'+self.L()+'.'+self.N()+'('+self.V()+')'}
    #     path: {self.getPath()}
    #     '''


    pass