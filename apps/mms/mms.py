#!/usr/bin/env python
import sys
from math import ceil

# Import local utility functions
import opensbli
from opensbli.problem import *
from opensbli.latex import LatexWriter
from opensbli.spatial import *
from opensbli.bcs import *
from opensbli.grid import *
from opensbli.timestepping import *
from opensbli.io import *

def dt(dx, c):
    """ Given a grid spacing dx and the wave speed c, return the value of dt such that the CFL condition is respected. """
    courant_number = 0.1
    return (dx*courant_number)/c

BUILD_DIR = os.getcwd()

opensbli.LOG.info("Generating code for the 2D MMS simulation...")
start_total = time.time()

# Problem dimension
ndim = 2

# Define the advection-diffusion equation in Einstein notation.

phi_analytical = "sin(x_j)"
advection_diffusion = "Eq( Der(phi,t), -Der(phi*u_j,x_j) + k*Der(Der(phi,x_j),x_j) + analy )" 

equations = [advection_diffusion]

# Substitutions
substitutions = []

# Define all the constants in the equations
constants = ["k", "u_j","analy"]

# Coordinate direction symbol (x) this will be x_i, x_j, x_k
coordinate_symbol = "x"

# Metrics
metrics = [False, False]

# Formulas for the variables used in the equations
formulas = ["Eq(analy, Der(l_j,x_j))"]

# Create the problem and expand the equations.
problem = Problem(equations, substitutions, ndim, constants, coordinate_symbol, metrics, formulas)
expanded_equations, expanded_formulas = problem.get_expanded()


# Output equations in LaTeX format.
latex = LatexWriter()
latex.open(path=BUILD_DIR + "/equations.tex")
metadata = {"title": "Equations", "author": "", "institution": ""}
latex.write_header(metadata)
temp = flatten(expanded_equations)
latex.write_expression(temp)
temp = flatten(expanded_formulas)
latex.write_expression(temp)
latex.write_footer()
latex.close()

# Discretise the equations
start = time.time()

spatial_scheme = Central(4) # Fourth-order central differencing in space.
temporal_scheme = RungeKutta(3) # Third-order Runge-Kutta time-stepping scheme.

# Create a numerical grid of solution points
length = [2*pi]*ndim
np = [10]*ndim
deltas = [length[i]/np[i] for i in range(len(length))]

grid = Grid(ndim,{'delta':deltas, 'number_of_points':np})
# Modify the expanded equations to be functions of grid 
# create a temporart term 
temp = EinsteinTerm('x_j')
x1 = temp.get_array(temp.get_indexed(ndim))
#make the array sin 
arr = [sin(x1[j]) for j,val in enumerate(x1)]
pprint(arr)
# use this temporart variable in the equation (named as l_j)
temp = EinsteinTerm('l_j')
# as these are returnded as a function make temporary coordinate function
coordinates = tuple([EinsteinTerm('x%d' % dim) for dim in range(ndim)] + [EinsteinTerm('t')])
l_j = temp.get_array(temp.get_indexed(ndim), coordinates)
su = dict(zip(l_j, arr))
# Substitute l_j into equations
expanded_formulas = [eq.subs(su).doit() for eq in expanded_formulas[0]]
pprint(expanded_formulas)
# now do the substitutions for x0, x1 that are grid evaluations
su = dict(zip(x1, [grid.Idx[0]*grid.deltas[0], grid.Idx[1]*grid.deltas[1]]))
expanded_formulas = [eq.subs(su).doit() for eq in expanded_formulas]
pprint(expanded_formulas)
expanded_equations = [eq.subs(f.lhs, f.rhs) for f in expanded_formulas for eq in expanded_equations[0]] 
# Perform the spatial discretisation
spatial_discretisation = SpatialDiscretisation(expanded_equations, expanded_formulas, grid, spatial_scheme)

# Perform the temporal discretisation
const_dt = True
temporal_discretisation = TemporalDiscretisation(temporal_scheme, grid, const_dt, spatial_discretisation)

# Apply Boundary conditions
bcs = [("periodic", "periodic"), ("periodic", "periodic")]
boundary = BoundaryConditions(bcs, grid, temporal_discretisation.prognostic_variables)

# Initial conditions to be consistent we use x0, an x1
x0 = "(grid.Idx[0]*grid.deltas[0])"
x1 = "(grid.Idx[1]*grid.deltas[1])"
initial_conditions = ["Eq(grid.work_array(phi), sin(%s))" % x0]
initial_conditions = GridBasedInitialisation(grid, initial_conditions)

# I/O save conservative variables at the end of simulation
io = FileIO(temporal_discretisation.prognostic_variables)

# Grid parameters like number of points, length in each direction, and delta in each direction
deltat = dt(max(deltas), 1)
T = 5.0
niter = ceil(T/deltat)
print "Going to do %d iterations." % niter

u0 = 1.0
u1 = 0.0
k = 0.5
simulation_parameters = {"niter":niter, "k":k, "u0":u0, "u1":u1, "deltat":deltat, "precision":"double", "name":"mms"}

# Generate the code.
opsc = OPSC(grid, spatial_discretisation, temporal_discretisation, boundary, initial_conditions, io, simulation_parameters)

end = time.time()
LOG.debug('The time taken to prepare the system in %d dimensions is %.2f seconds.' % (problem.ndim, end - start))

end_total = time.time()
LOG.debug('The time taken for the entire process for %d dimensions is %.2f seconds.' % (problem.ndim, end_total - start_total))