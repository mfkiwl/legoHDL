# ------------------------------------------------------------------------------
# Project: legohdl
# Script: graph.py
# Author: Chase Ruskin
# Description:
#   This script is a graph module mainly used to generate a flat dependency
#   tree from the DAG generated by legohdl. Performs topological sort.
# ------------------------------------------------------------------------------

import logging as log

from .map import Map


class Graph:


    def __init__(self):
        '''
        Create a Graph instance. Uses adjacency lists for sparse graph
        representation.
        '''
        #store with adjacency list (list of vertices...sparse graph)
        self._adj_list = Map()
        #store the reverse connections in an adjacency list
        self._rev_adj_list = Map()
        pass


    def clear(self):
        '''Empty the graph data structures.'''
        self._adj_list = Map()
        self._rev_adj_list = Map()
        pass


    def addVertex(self, u):
        '''
        Adds the unit to the graph's adjacency list if DNE.

        Parameters:
            u (Unit): unit object to add to adjacency list structure
        Returns:
            None
        '''
        if(u not in self._adj_list.keys()):
            self._adj_list[u] = []
        #store up-stream variation
        if(u not in self._rev_adj_list.keys()):
            self._rev_adj_list[u] = []
        pass
    

    def addEdge(self, integral, derivative):
        '''
        Creates a relationship between two units.

        Parameters:
            integral (Unit): upper-level unit
            derivative (Unit): lower-level unit (dependency)
        Returns:
            None
        '''
        #make sure vertices exist in the graph
        self.addVertex(integral)
        self.addVertex(derivative)
        #add dependency relation between derivative and integral
        if(derivative not in self._adj_list[integral]):
            self._adj_list[integral].append(derivative)
        #store up-stream variation
        if(integral not in self._rev_adj_list[derivative]):
            self._rev_adj_list[derivative].append(integral)
        pass


    def removeVertex(self, u):
        '''
        Removes the unit from the graph's adjacency list if exists.

        Parameters:
            u (Unit): unit object to remove from adjacency list structure
        Returns:
            None
        '''
        if(u in self._adj_list.keys()):
            del self._adj_list[u]
        #store up-stream variation
        if(u in self._rev_adj_list.keys()):
            del self._rev_adj_list[u]
        pass


    def removeEdge(self, integral, derivative):
        '''
        Removes a relationship between two units.

        Parameters:
            integral (Unit): upper-level unit
            derivative (Unit): lower-level unit (dependency)
        Returns:
            None
        '''
        if(derivative in self._adj_list[integral]):
            self._adj_list[integral].remove(derivative)
        #remove from upstream variation
        if(integral in self._adj_list[derivative]):
            self._adj_list[derivative].remove(integral)
        pass


    def topologicalSort(self):
        '''
        Topologically sort the graph to compute a hierarchical build order.

        If no units are found, then the program exits with error. The current
        block (block linked to last unit in order) will be the last block
        in the block_order.

        Parameters:
            None
        Returns:
            order ([Unit]): sorted build order of Unit entity-type objects
            block_order ([Block]): sorted order of blocks required for build
        '''
        #store list of design entities in their correct order
        order = [] 
        #store list of blocks in their correct order
        block_order = [] 

        nghbr_cnt = Map()
        #determine number of dependencies a vertex has
        for v in self._adj_list.keys():
            nghbr_cnt[v] = len(self._adj_list[v])

        #continue until all are transferred
        while len(order) < len(self._adj_list):
            #if a vertex has zero dependencies, add it to the list
            for unit in nghbr_cnt.keys():
                if nghbr_cnt[unit] == 0:
                    #add unit object to list
                    order.append(unit)
                    #add block name to list
                    if(unit.getLanguageFile().getOwner() not in block_order):
                        block_order += [unit.getLanguageFile().getOwner()]
                    #will not be recounted
                    nghbr_cnt[unit] = -1 
                    #who all depends on this module?
                    for k in self._adj_list.keys():
                        if(unit in self._adj_list[k]):
                            #decrement every vertex dep count that depended on recently added vertex
                            nghbr_cnt[k] = nghbr_cnt[k] - 1
                    continue
                pass

        if(len(block_order) == 0):
            exit(log.error("Invalid current block, try adding an HDL file."))
            
        #ensure current block is last in the order
        block_order.remove(order[-1].getLanguageFile().getOwner())
        block_order.append(order[-1].getLanguageFile().getOwner())

        return order,block_order


    #only display entities in the tree (no package units)
    def output(self, top, leaf='+-', disp_full=False, ref_points=Map(), compress=False):
        '''
        Formats and prints the current entity's dependency graph.

        Recursive method.

        Parameters:
            top (Unit): top-level unit to start graph from
            leaf (str): inner-recursive parameter to see what parent leaf was
            disp_full (bool): determine how to display entity (with full block title?)
            ref_points (Map): mapping for unit names/branchs to letters
            compress (bool): determine if to compress graph using reference points
        Returns:  
            None
        '''
        edge_branch = '\-'
        reg_branch = '+-'
        twig = '|'
        spaces = 2
        first = (leaf == reg_branch)
        txt = ''

        #print title if method is on top-level entity
        if(first):
            txt = '--- DEPENDENCY TREE ---' + '\n'
        
        #make sure a unit is passed as top
        if(top == None):
            return 'N/A'

        #start with top level
        if(top not in self._adj_list.keys()):
            exit(log.error('Entity '+top.E()+' may be missing an architecture.'))

        #skip reference point if compress is not set
        ref = ''
        if(compress == False):
            pass
        #add to reference points
        elif(top in ref_points.keys()):
            ref = str(ref_points[top])
        #do not use reference if lowest-level entity
        elif(len(self._adj_list[top]) == 0):
            ref = ''
        #create new reference point
        else:
            ref = '['+str(len(ref_points))+']'

        #only display units
        if(not top.isPkg()):
            temp_leaf = leaf
            #skip first bar because everything is under top-level entity
            if(not first):
                temp_leaf = ' '+leaf[1:]
            else:
                temp_leaf = temp_leaf.replace(reg_branch, edge_branch)
            #print to console
            node = top.getFull()
            if(compress):
                pass
            elif(disp_full):
                node = top.getTitle()
            #add this graph-line to the text
            txt = txt + temp_leaf+' '+node+' '+ref+'\n'
            pass

        #return if no children exist or already referenced in compression
        if(len(self._adj_list) == 0 or (compress and top in ref_points.keys())):
            return txt

        #add the point to the reference mapping
        if(top not in ref_points.keys()):
            ref_points[top] = ref

        #go through all entity's children
        for sub_entity in self._adj_list[top]:
            #add twig if the parent was not an edge branch
            if(leaf.count(reg_branch)):
                next_leaf = leaf[0:len(leaf)-2] + twig
            else:
                next_leaf = leaf[0:len(leaf)-2] + ' '

            #add extra spacing between parent and its children levels
            next_leaf = next_leaf + ' '*spaces
                
            #add \ if its an edge branch
            if(sub_entity == self._adj_list[top][-1]): 
                next_leaf = next_leaf + edge_branch
            #use + if a regular branch
            else:
                next_leaf = next_leaf + reg_branch

            #recursive call
            txt = txt + self.output(sub_entity, next_leaf, ref_points=ref_points, compress=compress, disp_full=disp_full)
            pass

        #clean up the graph during compression
        if(compress and first):
            #remove all reference points that only appear once
            remap_cnt = 0
            for i in range(0,len(ref_points)):
                rp = '['+str(i)+']'
                rp_cnt = txt.count(rp)
                #delete the reference point if was unused (not appear >1)
                if(rp_cnt <= 1):
                    txt = txt.replace(rp, '')
                    continue
                #compute reference point into string of characters
                ascii_len = remap_cnt
                new_rp = str(chr((ascii_len%26)+65))
                #continuously divide to get next character
                while(ascii_len >= 26):
                    ascii_len = int(int(ascii_len)/26)-1
                    new_rp = str(chr((ascii_len%26)+65)) + new_rp
                #replace old reference with new reference point
                txt = txt.replace(rp, '['+str(new_rp)+']')
                #increment the number of reference remaps
                remap_cnt += 1
                pass
            
        return txt


    def getNeighbors(self, vertex, upstream=False):
        '''
        Returns the list of vertices connected to the `vertex` Unit object.

        Parameters:
            vertex (Unit): a vertex within the graph
        Returns:
            _adj_list[vertex] ([Unit]): list of vertices connected to `vertex`
        '''
        adj = self._adj_list
        #print upstream variation
        if(upstream == True):
            adj = self._rev_adj_list

        if(vertex in adj.keys()):
            return list(adj[vertex])
        #return empty if not found as vertex
        return []


    def getVertices(self):
        '''Return list of all objects belonging to the graph.'''
        return list(self._adj_list.keys())

    pass