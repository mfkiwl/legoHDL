#graph module used to generate flat dependency tree, topologically sort it
from ordered_set import OrderedSet
import logging as log

class Graph:
    def __init__(self):
        #store with adj list (list of vertices)
        self.__adj_list = dict()
        self._unit_bank = dict()
        pass
    
    #takes in two entities and connects them [entity, dep-name]
    def addEdge(self, to, fromm): #to->upper-level module... from->lower-level module
        #add to list if vertex does not exist
        if(to not in self.__adj_list.keys()):
            self.__adj_list[to] = list()
        if(fromm not in self.__adj_list.keys()):
            self.__adj_list[fromm] = list()
        
        if(fromm not in self.__adj_list[to]):
            self.__adj_list[to].append(fromm)
            pass
        pass

    def addLeaf(self, to):
        self._unit_bank[to.getFull()] = to

    def removeEdge(self, to, fromm):
        if(fromm in self.__adj_list[to]):
            self.__adj_list[to].remove(fromm)
        pass

    def topologicalSort(self):
        order = list()
        block_order = OrderedSet()
        nghbr_count = dict()
        #print(len(self.__adj_list))
        #determine number of dependencies a vertex has
        for v in self.__adj_list.keys():
            nghbr_count[v] = len(self.__adj_list[v])
        #no connections were made, just add all units found
        if(len(self.__adj_list) == 0):
            log.warning("No edges found.")
            for u in self._unit_bank.values():
                order.append(u)
                block_order.add(u.getLib()+"."+u.getBlock())
  
        #continue until all are transferred
        while len(order) < len(self.__adj_list):
            #if a vertex has zero dependencies, add it to the list
            for v in nghbr_count.keys():
                if nghbr_count[v] == 0:
                    unit = self._unit_bank[v]
                    if(not unit.isPKG() or True):
                        #print(unit)
                        #add actual unit object to list
                        order.append(unit) 
                    #add block name to ordered set
                    block_order.add(unit.getLib()+"."+unit.getBlock())
                    #will not be recounted
                    nghbr_count[v] = -1 
                    #who all depends on this module?
                    for k in self.__adj_list.keys():
                        if(v in self.__adj_list[k]):
                            #decrement every vertex dep count that depended on recently added vertex
                            nghbr_count[k] = nghbr_count[k] - 1
                    continue

        if(len(block_order) == 0):
            exit(log.error("Invalid toplevel for current block"))
        return order,block_order

    #only display entities in the tree (no package units)
    def output(self):
        print('---DEPENDENCY TREE---')
        for v in self.__adj_list.keys():
            if(not self._unit_bank[v].isPKG()):
                print("vertex: [",v,"]",end=' <-- ')
                for u in self.__adj_list[v]:
                    if(not self._unit_bank[u].isPKG()):
                        print(u,end=' ')
                print()

    def getVertices(self):
        return len(self.__adj_list)

    pass