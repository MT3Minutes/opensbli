#!/usr/bin/env python
import sys, os
from math import ceil

# Import local utility functions
#import opensbli as base
from opensbli.core import *
from opensbli.core.bcs import *
from opensbli.physical_models.euler_eigensystem import *
from sympy import *
from opensbli.initialisation import *


ndim = 1
weno_order = 3
weno = True
Euler_eq = EulerEquations(ndim, weno)
ev_dict, LEV_dict, REV_dict = Euler_eq.generate_eig_system()
Avg = SimpleAverage([0, 1])
LLF = LLFCharacteristic(ev_dict, LEV_dict, REV_dict, weno_order, ndim, Avg)

sc1 = "**{\'scheme\':\'Weno\'}"
# Define the compresible Navier-Stokes equations in Einstein notation.
a = "Conservative(rhou_j,x_j,%s)"%sc1
mass = "Eq(Der(rho,t), - %s)"%(a)
a = "Conservative(rhou_i*u_j + KD(_i,_j)*p,x_j , %s)"%sc1
momentum = "Eq(Der(rhou_i,t) , -%s  )"%(a)
a = "Conservative((p+rhoE)*u_j,x_j, %s)"%sc1
energy = "Eq(Der(rhoE,t), - %s  )"%(a)
# Substitutions
substitutions = []

# Define all the constants in the equations
constants = ["gama", "Minf"]

# Define coordinate direction symbol (x) this will be x_i, x_j, x_k
coordinate_symbol = "x"

# Formulas for the variables used in the equations
velocity = "Eq(u_i, rhou_i/rho)"
pressure = "Eq(p, (gama-1)*(rhoE - rho*(1/2)*(KD(_i,_j)*u_i*u_j)))"
speed_of_sound = "Eq(a, (gama*p/rho)**0.5)"

simulation_eq = SimulationEquations()
eq = Equation()
eqns = eq.expand(mass, ndim, coordinate_symbol, substitutions, constants)
simulation_eq.add_equations(eqns)

eqns = eq.expand(momentum, ndim, coordinate_symbol, substitutions, constants)
simulation_eq.add_equations(eqns)

eqns = eq.expand(energy, ndim, coordinate_symbol, substitutions, constants)
simulation_eq.add_equations(eqns)

constituent = ConstituentRelations()
eqns = eq.expand(velocity, ndim, coordinate_symbol, substitutions, constants)
constituent.add_equations(eqns)

eqns = eq.expand(pressure, ndim, coordinate_symbol, substitutions, constants)
constituent.add_equations(eqns)

eqns = eq.expand(speed_of_sound, ndim, coordinate_symbol, substitutions, constants)
# constituent.add_equations(eqns)
pprint(srepr(eqns))
# exit()


schemes = {}
schemes[LLF.name] = LLF
rk = RungeKutta(3)
schemes[rk.name] = rk

block= SimulationBlock(ndim, block_number = 0)
block.sbli_rhs_discretisation = True

# Initial conditions
initial = GridBasedInitialisation()

x0 = "Eq(GridVariable(x0), block.deltas[0]*block.grid_indexes[0])"
p = "Eq(GridVariable(p), Piecewise((10.33, x0<1.0),(1, x0>=1.0),(0,True)))"
u0 = "Eq(GridVariable(u0), Piecewise((2.629369, x0<1.0),(0, x0>=1.0),(0,True)))"
d = "Eq(GridVariable(d), Piecewise((3.857143, x0<1.0),(1+0.2*sin(5*x0), x0>=1.0),(0,True)))"
rho = "Eq(DataObject(rho), d)"
rhou0 = "Eq(DataObject(rhou0), d*u0)"
rhoE ="Eq(DataObject(rhoE), p/(gama-1) + 0.5* d *(u0**2))"

eqns = [x0, u0, p, d, rho, rhou0, rhoE]

local_dict = {"block" : block, "GridVariable" : GridVariable, "DataObject" : DataObject}
initial_equations = [parse_expr(eq, local_dict=local_dict) for eq in eqns]
pprint(initial_equations)
initial = GridBasedInitialisation()
initial.add_equations(initial_equations)


boundaries = []
# Create boundaries, one for each side per dimension
for direction in range(ndim):
	boundaries += [LinearExtrapolateBoundaryConditionBlock(direction, 0)]
	boundaries += [LinearExtrapolateBoundaryConditionBlock(direction, 1)]

block.set_block_boundaries(boundaries)
block.set_equations([copy.deepcopy(constituent),copy.deepcopy(simulation_eq), initial])
block.set_discretisation_schemes(schemes)

block.discretise()

alg = TraditionalAlgorithmRK(block)
SimulationDataType.set_datatype(Double)
print "hello"
OPSC(alg)