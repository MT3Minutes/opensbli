#!/usr/bin/env python

#    AutoFD: An automatic code generator for solving differential equations.
#    Copyright (C) 2016 Satya P. Jammy, Christian T. Jacobs

#    This file is part of AutoFD.

#    AutoFD is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    AutoFD is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with AutoFD.  If not, see <http://www.gnu.org/licenses/>.

import os
import subprocess
from sympy import *
from sympy.parsing.sympy_parser import *

import logging
LOG = logging.getLogger(__name__)

from .equations import *
from .opsc import *
from .latex import LatexWriter
from .array import MutableDenseNDimArray
from .timestepping import *

class Scheme():
    def __init__(self,scheme, order):
        self.scheme = scheme
        self.order = order
        return

class NumericalGrid():
    def __init__(self, ndim):
        shape = tuple(symbols('nx0:%d'%ndim, integer=True))
        self.indices = [Symbol('i%d'%ind, integer = True) for ind, val in enumerate(shape)]
        self.shape = shape
        self.uniform = [True for ind,val in enumerate(shape)]
        self.time_grid = self.indices + [symbols('Time',integer=True)]
        et = EinsteinTerm('deltai_i');et.is_constant = True
        self.deltas = et.get_array(et.get_indexed(len(shape)))
        self.halos = []
        # works fine now. But need a better idea
        self.Idx = [Idx('idx[%d]'%ind) for ind, val in enumerate(shape)]
        return
    def work_array(self,name):
        '''
        No shape information will be provided; as the shape of the arrays might change based
        on the computations (including Halos or excluding halos)
        '''
        out = IndexedBase('%s'%name)[self.indices]
        out.is_grid = True
        return out
class IndexedBase(IndexedBase):
    is_grid = True
    is_constant = False

class SpatialDerivative():
    """
    This initializes the spatial derivatives of an arbitrary function 'F'
    on the numerical grid with the provided spatial scheme.
    For wall boundary condition this will have a dependency on grid range need to think of
    that
    """
    def __init__(self, spatial,grid, max_order):
        """
        This initializes the spatial derivative class, which gives the equations
        of spatial Derivatives for combinations of

        Spatial scheme, and order of accuracy
        """
        # stencil should be formula dependant
        self.stencil = [[] for dim in grid.shape]
        self.update_stencil(spatial,grid)
        self.derivatives = []
        self.der_direction = grid.indices
        self.deltas = grid.deltas
        fn = IndexedBase('f',shape = grid.shape)[grid.indices]
        self.fn = fn
        self.Derivative_formulas(fn,max_order, grid)
        return

    def update_stencil(self,spatial, grid):
        for dim, val in enumerate(grid.shape):
            if spatial.scheme == 'central':
                points = list(i for i in range(-spatial.order/2, spatial.order/2+1))
                grid.halos.append(tuple([-spatial.order/2, spatial.order/2]))
            else:
                raise NotImplementedError("Only central difference schemes are supported")
            self.stencil[dim] = [grid.indices[dim] + i for i in points]
            #print points, grid.indices[dim], self.stencil[dim]
        return
    def Derivative_formulas(self, fn, max_order, grid):
        derivatives = []
        derivatives += [fn] # later change this to interpolation
        derivative_formula = []
        derivative_formula += [fn]
        comp_kernels = []
        comp_kernels += [fn]
        for order in range(1,max_order+1):
            shape = tuple( [len(grid.indices) for ind in range(order)])
            array = MutableDenseNDimArray.zeros(*shape)
            fdarray = MutableDenseNDimArray.zeros(*shape)
            deriv_kernel = MutableDenseNDimArray.zeros(*shape)
            for ind in np.ndindex(*array.shape):
                der_args = [grid.indices[i] for i in ind]
                name = [str(arg) for arg in ind]
                #name = tuple(ind)
                name = "[%d][%s]"%(order,','.join(name))
                deriv_kernel[ind] = Symbol(name)
                array[ind] = fn.diff(*der_args)
                # find the finite difference formula
                if order == 1 or len(set(der_args)) ==1:
                    fdarray[ind] = as_finite_diff(array[ind], self.stencil[ind[0]])*pow(grid.deltas[ind[0]],-order)
                else:
                    newder = array[ind].subs(derivatives[order-1][ind[:-1]],derivative_formula[order-1][ind[:-1]])
                    fdarray[ind] = as_finite_diff(newder,self.stencil[ind[-1]], wrt=grid.indices[ind[-1]])*pow(grid.deltas[ind[-1]],-1)
            derivatives.append(array)
            derivative_formula.append(fdarray)
            comp_kernels.append(deriv_kernel)
        self.derivatives = derivatives
        self.derivative_formula = derivative_formula
        self.deriv_kernel = comp_kernels
        return
    def get_derivativeformula(self, derivative, order):
        '''This returns the formula for the derivative using the functions provided
        for getting a symbolic derivative for a general function use get_derivative
        used for ceval stuff
        '''
        order = len(derivative.args[1:])
        inds = []
        for arg in derivative.args[1:]:
            inds = inds + [self.der_direction.index(arg)]
        if order == 1 or len(set(inds)) ==1:
            formula = as_finite_diff(derivative, self.stencil[inds[0]])*pow(self.deltas[inds[0]],-order)
        else:
            loweder = Derivative(derivative.args[0], *inds[:-1])
            raise ValueError("first update the derivative of %s before calling %s"%(loweder, derivative))
        return formula
    def get_derivative(self, derivative):
        '''
        This returns a tuple to which the derivaitve formula exists in
        already evaluated derivatives.
        '''
        order = len(derivative.args[1:])
        inds = []
        for arg in derivative.args[1:]:
            inds = inds + [self.der_direction.index(arg)]
        generalformula = []
        subevals = []
        requires = []
        if order == 1 or len(set(inds)) ==1:
            generalformula += [order,tuple(inds)]
            if len(derivative.args[0].atoms(Indexed)) >1:
                subevals += [derivative.args[0]]
                requires += list(derivative.args[0].atoms(Indexed))
            else:
                subevals += [None]
                requires += [derivative.args[0]]
        else:
            if len(derivative.args[0].atoms(Indexed)) >1:
                subevals += [derivative.args[0]]
                requires += list(derivative.args[0].atoms(Indexed))

            else:
                subevals += [None]
                requires += [derivative.args[0]]
            generalformula += [order-1,tuple([inds[-1]])]
            requires += [self.derivatives[order-1][inds[:-1]].subs(self.fn,derivative.args[0])]

        return generalformula, subevals, requires

class Evaluations():
    def __init__(self, lhs,rhs, requires,subevals = None, wk=None):
        self.store = True
        if isinstance(lhs, Derivative):
            self.is_der = True
            self.is_formula = False
            if subevals:
                self.subevals = subevals
            else:
                self.subevals = [None]
            if wk:
                self.work = wk
            else:
                self.work = None
            self.formula = rhs
            self.requires = requires
            self.evaluation_range = []
        else:
            self.is_formula = True
            self.is_der = False
            if subevals:
                self.subevals = subevals
            else:
                self.subevals = [None]
            if wk:
                self.work = wk
            else:
                self.work = None
            self.formula = rhs
            self.requires = requires
            self.evaluation_range = []
        return


class SpatialDiscretisation():
    def __init__(self, equations, formulas, grid, spatial_scheme):
        alleqs = flatten(list(e.expanded for e in equations))
        allformulas = flatten(list(e.expanded for e in formulas))
        max_order = maximum_derivative_order(alleqs)
        SD = SpatialDerivative(spatial_scheme,grid,max_order)
        grid_arrays = {}
        range_used = {}
        grid_variables, variable_count = get_grid_variables(alleqs+allformulas)
        for atom in grid_variables:
            grid_arrays[atom] = vartoGridArray(atom, grid)
        spatialders, dercount, time_derivatives = self.get_spatial_derivatives(alleqs+allformulas)
        # Define the formulas on the grid, this is substituting the old with new
        # TODO do a sanity check of the formulas, i.e. remove all the formulas that
        # are not used in the equations
        evals = {}
        for form in allformulas:
            out = form
            for atom in form.atoms(Indexed):
                out = out.subs(atom, grid_arrays[atom])
            evaluated = Evaluations(out.lhs,out.rhs, list(out.rhs.atoms(Indexed)), None,out.lhs)
            evals[out.lhs] = evaluated
        # TODO again a way of passing the coordinates
        et = EinsteinTerm('x_i');et.is_constant = True
        coord = et.get_array(et.get_indexed(len(grid.shape)))
        coord = coord.tolist()
        # Work array is always named as wk
        wkarray = 'wk'; wkind = 0;
        for der in spatialders:
            out = der # Modify the derivative to be a derivative on grid
            wk = grid.work_array('%s%d'%(wkarray,wkind)); wkind = wkind +1
            for atom in der.atoms(Indexed):
                out = out.subs(atom, grid_arrays[atom])
            for arg in out.args[1:]:
                out = out.subs(arg, grid.indices[coord.index(arg)])
            generalformula, subevals, requires = SD.get_derivative(out)
            grid_arrays[der] = out
            evaluated = Evaluations(out,generalformula,requires, subevals, wk)
            evals[out] = evaluated
        # we will assume that all the functions in time derivative are known at the start
        known = [grid_arrays[d.args[0]] for d in time_derivatives]
        for val in known:
            evaluated = Evaluations(val,val, None, None,val)
            evals[val] =  evaluated
        # Sort the Formulas
        order_of_evaluations = [grid_arrays[d.args[0]] for d in time_derivatives]
        order_of_evaluations = sort_evaluations(order_of_evaluations,evals, Indexed)
        # sort the derivatives
        order_of_evaluations = sort_evaluations(order_of_evaluations,evals, Derivative)
        # update the range of evaluations for each evaluation
        range_of_evaluation(order_of_evaluations, evals,grid, SD)
        # now define a Kernel for each of the evaluations

        ''' All the variables (IndexedObjects) in the equations
        excluding those which have a time derivative are stored into a kernel
        '''
        forms = [ev for ev in order_of_evaluations if isinstance(ev, Indexed) and ev not in known]
        ranges = [evals[ev].evaluation_range for ev in forms]
        subevals = flatten([evals[ev].subevals for ev in forms])
        subeval_truth = [ev == None for ev in subevals]
        # check if all the ranges of evaluation are the same for the Formulas
        range_truth = [ranges[0][i] == val[i] for val in ranges for i in range(len(ranges[0]))]
        computations = []
        eqs = []
        eqs = [Eq(evals[ev].work, evals[ev].formula) for ev in forms]
        if forms:
            # if same range then combine them into a single computation else store into different computations
            if all(range_truth) and all(subeval_truth):
                computations.append(Kernel(eqs, ranges[0], "Formula Evaluation"))
            else:
                for number,eq in enumerate(eqs):
                    computations.append(Kernel(eq, ranges[number]))
        # Now process the Derivatives
        # TODO this can be moved out into a seperate function. Which can be used for Diagnostics/Genearalized
        # coordinate equations evaluations
        derivatives = [ev for ev in order_of_evaluations if isinstance(ev, Derivative) and ev not in known]
        ranges = [evals[ev].evaluation_range for ev in derivatives]
        subevals = [evals[ev].subevals for ev in derivatives]
        require = [evals[ev].requires for ev in derivatives]
        for number,der in enumerate(derivatives):
            if not any(isinstance(req, Derivative) for req in require[number]):
                if all(subev == None for subev in subevals[number]):
                    rhs = SD.get_derivativeformula(der,evals[der].formula[0])
                    eq = Eq(evals[der].work,rhs)
                    computations.append(Kernel(eq, ranges[number], "Derivative Evaluation"))
                else:
                    # store into temporary array the sub evaluation
                    eqs = []
                    tempwkind = wkind
                    for subev in subevals[number]:
                        wk = grid.work_array('%s%d'%(wkarray,tempwkind));tempwkind = tempwkind +1
                        for req in require[number]:
                            local_range = evals[req].evaluation_range
                            subev = subev.subs(req,evals[req].work)
                        eqs.append(Eq(wk,subev))
                    computations.append(Kernel(eqs, local_range, "Temporary formula Evaluation"))
                    for eq in eqs:
                        newder = der.subs(eq.rhs,eq.lhs)
                    rhs = SD.get_derivativeformula(newder,evals[der].formula[0])
                    eq = Eq(evals[der].work,rhs)
                    computations.append(Kernel(eq, ranges[number], "Derivative Evaluation"))
            else:
                newder = der
                if all(subev == None for subev in subevals[number]):
                    for req in require[number]:
                        newder = newder.subs(req,evals[req].work)
                else:
                    raise NotImplementedError("Sub evaluations in a mixed derivative")
                rhs = SD.get_derivativeformula(newder,evals[der].formula[0])
                eq = Eq(evals[der].work,rhs)
                computations.append(Kernel(eq, ranges[number], "Nested Derivative evaluation"))

        # All the spatial computations are evaluated by this point now get the updated equations
        updated_eq = [eq for eq in alleqs]
        for eqno,eq in enumerate(updated_eq):
            spatialders, dercount, time_derivatives = self.get_spatial_derivatives([eq])
            grid_variables, variable_count = get_grid_variables([eq])
            spatialders = (sorted(spatialders, cmp = decreasing_order))
            # substitute spatial ders first
            for var in spatialders+grid_variables:
                new = evals[grid_arrays[var]].work
                updated_eq[eqno] = updated_eq[eqno].subs(var,new)
        # The final computations of the residual (change in the rhs terms of the equations)
        # The residual equations are also named as work arrays
        # The residual arrays are tracked to for use in evaluation of temporal scheme
        residual_eqs = []
        residual_arrays = []
        for eq in updated_eq:
            wk = grid.work_array('%s%d'%(wkarray,wkind)); wkind = wkind + 1
            residual_arrays.append({eq.lhs:wk})
            residual_eqs.append(Eq(wk,eq.rhs))
        eval_range = [tuple([0,s]) for s in grid.shape]
        computations.append(Kernel(residual_eqs, eval_range, "Residual of equation"))

        # update the required computations and residual arrays to class
        self.computations = computations
        self.residual_arrays = residual_arrays
        return

    def get_spatial_derivatives(self, equations):
        ders = []
        count = {}
        time_ders = []
        for eq in equations:
            pot = preorder_traversal(eq)

            for p in pot:
                if p in ders:
                    pot.skip()
                    count[p] = count[p]+1
                    continue
                elif isinstance(p, Derivative):
                    if all(arg != EinsteinTerm('t') for arg in p.args):
                        pot.skip()
                        ders.append(p)
                        count[p] = 1
                    else:
                        pot.skip()
                        time_ders.append(p)
                else:
                    continue
        return ders, count, time_ders
    


class Exchange(object):
    def __init__(self, grid):
        range_of_evaluation = [tuple([0 + grid.halos[i][0], s + grid.halos[i][1]]) for i, s in enumerate(grid.shape)]
        # Size of transfers
        self.transfer_size = [r[1] - r[0] for r in range_of_evaluation]
        self.transfer_from = [grid.halos[i][0] for i, s in enumerate(grid.shape)]
        self.transfer_to = [grid.halos[i][0] for i, s in enumerate(grid.shape)]
        self.transfer_arrays = []
        return

class BoundaryConditions():
    types = {"periodic":"exchange_self", "symmetry":"exchange_self"}
    def __init__(self, bcs, grid, arrays):
        if len(bcs) != len(grid.shape):
            raise ValueError("Boundary conditions and the dimensions of grid mismatch")
        ndim = len(grid.shape)
        self.boundaries = bcs
        self.computations = [None for b in bcs for a in b]
        self.transfers = [None for b in bcs for a in b]
        self.get_type()
        for ind,bc in enumerate(self.boundaries):
            if bc[0] == bc[1] and bc[0] == "periodic":
                left, right = self.periodic_bc(ind,grid, arrays)
                self.transfers[ind*ndim + 0] = left
                self.transfers[ind*ndim + 1] = right
            else:
                raise NotImplementedError("Implement boundary conditions :",bc)
        return
    def get_type(self):
        types = BoundaryConditions.types
        self.type_of_boundary = [[types[bc[0]], types[bc[1]]] for bc in self.boundaries]
        self.type_of_boundary = flatten(self.type_of_boundary)
        return
    def periodic_bc(self, direction, grid,arrays):
        transfers = []
        # generic transfer for the grid
        transfers_left = Exchange(grid)
        transfers_right = Exchange(grid)
        # the left transfers are from from start of grid to end of grid (nx)
        transfers_left.transfer_size[direction] = abs(grid.halos[direction][0])
        transfers_left.transfer_from[direction] = 0
        transfers_left.transfer_to[direction] = grid.shape[direction]
        transfers_left.transfer_arrays = arrays
        # Right transfers are from end of grid- halo points to the starting of halo points
        transfers_right.transfer_size[direction] = abs(grid.halos[direction][0])
        transfers_right.transfer_from[direction] = grid.shape[direction]+ grid.halos[direction][0]
        transfers_right.transfer_to[direction] = grid.halos[direction][0]
        transfers_right.transfer_arrays = arrays
        return transfers_left, transfers_right

class GridBasedInitialization():
    def __init__(self, grid, Ics):
        self.computations = []
        initialization_eq =[]
        for ic in Ics:
            initialization_eq.append(parse_expr(ic, local_dict= {'grid':grid}))
        range_ofevaluation = [tuple([0+grid.halos[i][0],s+grid.halos[i][1]]) for i,s in enumerate(grid.shape)]
        self.computations.append(Kernel(initialization_eq,range_ofevaluation,"Initialization"))

        return
class Fileio():
    '''
    Saves the arrays provided after every n iterations into a HDF5 file. If niter is None
    it is saved at the end of simulation
    '''
    def __init__(self, arrays, niter = None):
        self.save_after = []
        self.save_arrays = []
        self.save_after += [Symbol('niter', integer=True)]
        if isinstance(arrays, list):
            self.save_arrays += arrays
        else:
            self.save_arrays += [arrays]
        return

def range_of_evaluation(order_of_evaluations, evaluations, grid, sdclass):
    '''
    First the ranges of derivatives are updated, then other ranges are updated
    '''
    ders = []
    for ev in order_of_evaluations:
        if isinstance(ev, Derivative):
            ders.append(ev)
        evaluations[ev].evaluation_range = [tuple([0,s]) for s in grid.shape]
    # Update the range for the derivatives
    grouped_ders = group_derivatives(ders)
    for key, value in grouped_ders.iteritems():
        for val in value:
            require = evaluations[val].requires
            form  = evaluations[val].formula
            dire = form[1][0]
            halos = grid.halos[dire]
            for req in require:
                erange = list(evaluations[req].evaluation_range[dire])
                if erange[0] == 0 and erange[1] == grid.shape[dire]:
                    erange[0] = erange[0]+halos[0]
                    erange[1] = erange[1]+halos[1]
                evaluations[req].evaluation_range[dire] = tuple(erange)
    #update the range for the formulas
    for ev in order_of_evaluations:
        if isinstance(ev, Indexed):
            require = evaluations[ev].requires
            if require:
                for req in require:
                    evaluations[req].evaluation_range = evaluations[ev].evaluation_range

    return

def sort_evaluations(evaluated, evaluations, typef):
    for key in evaluations.keys():
        if isinstance(key, typef) and not key in evaluated:
            if all(ev in evaluated for ev in evaluations[key].requires):
                evaluated.append(key)
            else:
                for val in evaluations[key].requires:
                    if not val in evaluated:
                        sort_evaluations(evaluated, {val:evaluations[val]}, typef)
                evaluated.append(key)
    return evaluated

def decreasing_order(s1, s2):
    return cmp(len(s2.args), len(s1.args))

def increasing_order(s1, s2):
    return cmp(len(s1.args), len(s2.args))

def group_derivatives(spatialders):
    spatial_der_dict ={}
    for der in spatialders:
        if der.args[0] in spatial_der_dict.keys():
            spatial_der_dict[der.args[0]] += [der]
        else:
            spatial_der_dict[der.args[0]] = [der]

    for key,value in spatial_der_dict.iteritems():
        if len(value)>1:
            spatial_der_dict[key] = (sorted(value, cmp=increasing_order))
    return spatial_der_dict



def vartoGridArray(variable,grid):
    '''
    Converts a variable/ function or Indexed Object to a Indexed base on the Grid
    inputs: variable, grid
    returns: the Grid array
    '''
    if isinstance(variable, Indexed):
        return IndexedBase('%s'%variable.base)[grid.indices]
    elif isinstance(variable, Function):
        return IndexedBase('%s'%variable.func)[grid.indices]
    else:
        raise ValueError("Only functions or Indexed Objects are supported", variable)
    return


def get_grid_variables(equations):
    variables = []
    count = {}
    for eq in equations:
        pot = preorder_traversal(eq)
        for p in pot:
            if p in variables:
                pot.skip()
                count[p] = count[p]+1
                continue
            elif isinstance(p, Indexed):
                pot.skip()
                variables.append(p)
                count[p] = 1
            else:
                continue
    return variables, count
