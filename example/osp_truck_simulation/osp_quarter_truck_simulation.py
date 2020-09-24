"""Simulation Example for Selection of a Proper Time Step"""

#%% Create FMU Instances
import os

import matplotlib.pyplot as plt
from pyOSPParser.system_configuration import OspVariableEndpoint

from pycosim.osp_command_line_interface import LoggingLevel, SimulationError
from pycosim.simulation import FMU, SimulationConfiguration

PATH_TO_DIR = os.getcwd()

PATH_TO_CHASSIS = os.path.join(PATH_TO_DIR, '..', 'fmus', 'osp_truck_simulation', 'chassis.fmu')
PATH_TO_WHEEL = os.path.join(PATH_TO_DIR, '..', 'fmus', 'osp_truck_simulation', 'wheel.fmu')
PATH_TO_GROUND = os.path.join(PATH_TO_DIR, '..', 'fmus', 'osp_truck_simulation', 'ground.fmu')

chassis_fmu = FMU(PATH_TO_CHASSIS)
wheel_fmu = FMU(PATH_TO_WHEEL)
ground_fmu = FMU(PATH_TO_GROUND)

# Inspecting the FMUs
for fmu in [chassis_fmu, wheel_fmu, ground_fmu]:
    print('---------------')
    print(fmu.name)
    print(f'  inputs: {fmu.get_input_names()}')
    print(f'  outputs: {fmu.get_output_names()}')
    print(f'  variable_groups: {fmu.get_variable_group_names()}')
    print(f'  parameters: {fmu.get_parameter_names()}')
    print(f'  others: {fmu.get_other_variable_names()}')

# Create a simulation setup with a empty system inside
sim_config = SimulationConfiguration()

# Add components to the system
sim_config.add_component(name='chassis', fmu=chassis_fmu)
sim_config.add_component(name='wheel', fmu=wheel_fmu)
sim_config.add_component(name='ground', fmu=ground_fmu)

# Add connections between components
sim_config.add_connection(
    source=OspVariableEndpoint(simulator='chassis', name='linear mechanical port'),
    target=OspVariableEndpoint(simulator='wheel', name='chassis port'),
    group=True
)
sim_config.add_connection(
    source=OspVariableEndpoint(simulator='wheel', name='ground port'),
    target=OspVariableEndpoint(simulator='ground', name='linear mechanical port'),
    group=True
)

# Set parameters as initial value setting
sim_config.add_update_initial_value(
    component_name='chassis', variable='C.mChassis', value=400, type_value=float
)
sim_config.add_update_initial_value(
    component_name='chassis', variable='C.kChassis', value=15000, type_value=float
)
sim_config.add_update_initial_value(
    component_name='chassis', variable='R.dChassis', value=1000, type_value=float
)
sim_config.add_update_initial_value(
    component_name='wheel', variable='C.mWheel', value=40, type_value=float
)
sim_config.add_update_initial_value(
    component_name='wheel', variable='C.kWheel', value=150000, type_value=float
)
sim_config.add_update_initial_value(
    component_name='wheel', variable='R.dWheel', value=0, type_value=float
)

# Set logging configuration
sim_config.add_logging_variable(component_name='chassis', variable_name='zChassis')
sim_config.add_logging_variable(component_name='wheel', variable_name='zWheel')
sim_config.add_logging_variable(component_name='ground', variable_name='zGround')

# Run simulation
sim_config.set_base_step_size(0.01)
output = sim_config.run_simulation(
    duration=10, logging_level=LoggingLevel.info
)
result_0_01 = output.result
if len(output.error) > 0:
    raise SimulationError(f'An error or errors occurred during the simulation: {output.error}')
print(output.log)

# Set decimation factor for the logging
sim_config.set_decimation_factor(component_name='chassis', decimation_factor=10)
sim_config.set_decimation_factor(component_name='wheel', decimation_factor=10)
sim_config.set_decimation_factor(component_name='ground', decimation_factor=10)

# Run simulation
sim_config.set_base_step_size(0.001)
output = sim_config.run_simulation(
    duration=10, logging_level=LoggingLevel.info
)
result_0_001 = output.result
if len(output.error) > 0:
    raise SimulationError(f'An error or errors occurred during the simulation: {output.error}')
print(output.log)

# Plot result
fig, ax = plt.subplots()
for comp_name in ['chassis', 'wheel', 'ground']:
    result_0_01[comp_name].drop(['StepCount'], axis=1).plot(x='Time', ax=ax, figsize=(12, 8))
    result_0_001[comp_name].drop(['StepCount'], axis=1).plot(x='Time', ax=ax, figsize=(12, 8))
plt.show()
