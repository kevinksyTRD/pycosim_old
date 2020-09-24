"""This example demonstrate how to identify model parameters.

The system model consists of two control volumes connected each other and each
has heat input from the environment and heat loss to the environment. The
system model is given with prescribed output for a given step temperature change.
The task is to find the model parameters for each control volume using optimiztion
method.

See jupyter notebook (model_identificaiton.ipynb) file for more detail.
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyOSPParser.logging_configuration import OspLoggingConfiguration
from pyOSPParser.system_configuration import OspVariableEndpoint
from scipy.interpolate import interp1d
from scipy.optimize import minimize_scalar

from pycosim.osp_command_line_interface import LoggingLevel, SimulationError
from pycosim.simulation import FMU, SimulationConfiguration

PLOT_SIZE = (12, 8)

PATH_TO_DIR = os.getcwd()
PATH_TO_DATA1 = os.path.join(PATH_TO_DIR, 'experiment1_1000W_5_10.csv')
PATH_TO_DATA2 = os.path.join(PATH_TO_DIR, 'experiment2_2000W_5_10.csv')

df_scenario1 = pd.read_csv(PATH_TO_DATA1)
df_scenario2 = pd.read_csv(PATH_TO_DATA2)

df_scenario1.plot(x='time{s}', figsize=PLOT_SIZE)
df_scenario2.plot(x='time{s}', figsize=PLOT_SIZE)

PATH_TO_FMU_CV = os.path.join(PATH_TO_DIR, '..', 'fmus', 'thermal', 'ControlVolume.fmu')
PATH_TO_FMU_PULSE = os.path.join(PATH_TO_DIR, '..', 'fmus', 'signals', 'Pulse.fmu')
PATH_TO_FMU_WALL = os.path.join(PATH_TO_DIR, '..', 'fmus', 'thermal', 'WallHeatTransfer.fmu')
PATH_TO_CONSTANT = os.path.join(PATH_TO_DIR, '..', 'fmus', 'signals', 'Constant.fmu')

# Create fmu instances for the models
control_volume_fmu = FMU(PATH_TO_FMU_CV)  # For control volumes
wall_heat_transfer_fmu = FMU(PATH_TO_FMU_WALL)  # For heat transfer between the control volumes
pulse_signal_fmu = FMU(PATH_TO_FMU_PULSE)  # For heat source
constant_signal_fmu = FMU(PATH_TO_CONSTANT)  # For ambient temperature

# Examine each FMU
for fmu in [control_volume_fmu, wall_heat_transfer_fmu, pulse_signal_fmu, constant_signal_fmu]:
    print('------------------------------')
    print(f'{fmu.name}')
    print(f'  input: {fmu.get_input_names()}')
    print(f'  output: {fmu.get_output_names()}')
    print(f'  parameters: {fmu.get_parameter_names()}')

# Create an simulation configuration instance with empty system configuration
sim_config = SimulationConfiguration()

# Now we will add components
sim_config.add_component(name='ControlVolume1', fmu=control_volume_fmu)
sim_config.add_component(name='ControlVolume2', fmu=control_volume_fmu)
sim_config.add_component(name='WallHeatTransfer', fmu=wall_heat_transfer_fmu)
sim_config.add_component(name='HeatLossCV1', fmu=wall_heat_transfer_fmu)
sim_config.add_component(name='HeatLossCV2', fmu=wall_heat_transfer_fmu)
sim_config.add_component(name='HeatSource', fmu=pulse_signal_fmu)
sim_config.add_component(name='AmbientCondition', fmu=constant_signal_fmu)

# Now we add connections
sim_config.add_connection(  # Heat source dQ to control volume 1
    source=OspVariableEndpoint(simulator='HeatSource', name='output'),
    target=OspVariableEndpoint(simulator='ControlVolume1', name='p_in.dQ'),
    group=False
)
sim_config.add_connection(  # Control volume 1 temperature to heat loss from control volume 1
    target=OspVariableEndpoint(simulator='HeatLossCV1', name='p_in.T'),
    source=OspVariableEndpoint(simulator='ControlVolume1', name='p_loss.T'),
    group=False
)
sim_config.add_connection(  # Heat loss from CV 1 heat flow to control volume 1
    source=OspVariableEndpoint(simulator='HeatLossCV1', name='p_in.dQ'),
    target=OspVariableEndpoint(simulator='ControlVolume1', name='p_loss.dQ'),
    group=False
)
sim_config.add_connection(  # Ambient temperature to heat loss from control volume 1
    source=OspVariableEndpoint(simulator='AmbientCondition', name='output'),
    target=OspVariableEndpoint(simulator='HeatLossCV1', name='p_out.T'),
    group=False
)
sim_config.add_connection(  # Control volume 1 temperature to wall
    source=OspVariableEndpoint(simulator='ControlVolume1', name='p_transfer_out.T'),
    target=OspVariableEndpoint(simulator='WallHeatTransfer', name='p_in.T'),
    group=False
)
sim_config.add_connection(  # Wall heat transfer dQ to control volume 1
    source=OspVariableEndpoint(simulator='WallHeatTransfer', name='p_in.dQ'),
    target=OspVariableEndpoint(simulator='ControlVolume1', name='p_transfer_out.dQ'),
    group=False
)
sim_config.add_connection(  # Wall heat transfer dQ to control volume 2
    source=OspVariableEndpoint(simulator='WallHeatTransfer', name='p_out.dQ'),
    target=OspVariableEndpoint(simulator='ControlVolume2', name='p_transfer_in.dQ'),
    group=False
)
sim_config.add_connection(  # Control volume 2 temperature to wall
    source=OspVariableEndpoint(simulator='ControlVolume2', name='p_transfer_in.T'),
    target=OspVariableEndpoint(simulator='WallHeatTransfer', name='p_out.T'),
    group=False
)
sim_config.add_connection(  # Ambient temperature to control volume 2
    source=OspVariableEndpoint(simulator='ControlVolume2', name='p_loss.T'),
    target=OspVariableEndpoint(simulator='HeatLossCV2', name='p_in.T'),
    group=False
)
sim_config.add_connection(  # Ambient temperature to control volume 2
    source=OspVariableEndpoint(simulator='HeatLossCV2', name='p_in.dQ'),
    target=OspVariableEndpoint(simulator='ControlVolume2', name='p_loss.dQ'),
    group=False
)
sim_config.add_connection(  # Ambient temperature to control volume 2
    source=OspVariableEndpoint(simulator='AmbientCondition', name='output'),
    target=OspVariableEndpoint(simulator='HeatLossCV2', name='p_out.T'),
    group=False
)

# Logging configuration
sim_config.logging_config = OspLoggingConfiguration()
sim_config.add_logging_variable(
    component_name='ControlVolume1',
    variable_name='p_transfer_out.T'
)
sim_config.add_logging_variable(
    component_name='ControlVolume2',
    variable_name='p_transfer_in.T'
)

# Initial values or parameter setting
sim_config.add_update_initial_value(  # Specific heat capacity of CV1
    component_name='ControlVolume1',
    variable='c',
    value=1003.5,
    type_value=float
)
sim_config.add_update_initial_value(  # Mass of CV1
    component_name='ControlVolume1',
    variable='m',
    value=3.5,
    type_value=float
)
sim_config.add_update_initial_value(  # Initial temperature of CV1
    component_name='ControlVolume1',
    variable='T0',
    value=300,
    type_value=float
)
sim_config.add_update_initial_value(  # Specific heat capacity of CV1
    component_name='ControlVolume2',
    variable='c',
    value=1003.5,
    type_value=float
)
sim_config.add_update_initial_value(  # Mass of CV1
    component_name='ControlVolume2',
    variable='m',
    value=2.4,
    type_value=float
)
sim_config.add_update_initial_value(  # Initial temperature of CV1
    component_name='ControlVolume2',
    variable='T0',
    value=300,
    type_value=float
)
sim_config.add_update_initial_value(  # Heat transfer coefficient for CV1 toward surrounding
    component_name='HeatLossCV1',
    variable='h_wall',
    value=60,
    type_value=float
)
sim_config.add_update_initial_value(  # Area of CV1 toward surrounding
    component_name='HeatLossCV1',
    variable='A_wall',
    value=3,
    type_value=float
)
sim_config.add_update_initial_value(  # Heat transfer coefficient for CV2 toward surrounding
    component_name='HeatLossCV2',
    variable='h_wall',
    value=60,
    type_value=float
)
sim_config.add_update_initial_value(  # Area of CV2 toward surrounding
    component_name='HeatLossCV2',
    variable='A_wall',
    value=3,
    type_value=float
)
sim_config.add_update_initial_value(  # Area between CV1 and CV2
    component_name='WallHeatTransfer',
    variable='A_wall',
    value=1,
    type_value=float
)
sim_config.add_update_initial_value(  # heat transfer coefficient between CV1 and CV2
    component_name='WallHeatTransfer',
    variable='h_wall',
    value=240,
    type_value=float
)
sim_config.add_update_initial_value(  # Start time for heat flow into CV1
    component_name='HeatSource',
    variable='start_time',
    value=5,
    type_value=float
)
sim_config.add_update_initial_value(  # Stop time for heat flow into CV1
    component_name='HeatSource',
    variable='stop_time',
    value=10,
    type_value=float
)
sim_config.add_update_initial_value(  # Heat flow during the pulse
    component_name='HeatSource',
    variable='amplitude',
    value=1000,
    type_value=float
)
sim_config.add_update_initial_value(  # Ambient temperature
    component_name='AmbientCondition',
    variable='C',
    value=330,
    type_value=float
)

# Run simulation and plot the result
sim_output = sim_config.run_simulation(duration=100, logging_level=LoggingLevel.info)
if len(sim_output.error) > 0:
    raise SimulationError(f'There was an error running the simulation\n{sim_output.error}')
df_result = sim_output.result

fig, ax = plt.subplots()
df_scenario1.plot(x='time{s}', ax=ax, figsize=PLOT_SIZE)  # Referece
df_result['ControlVolume1'].drop(['StepCount'], axis=1).plot(x='Time', ax=ax, figsize=PLOT_SIZE)
df_result['ControlVolume2'].drop(['StepCount'], axis=1).plot(x='Time', ax=ax, figsize=PLOT_SIZE)
plt.show()

# Change the parameter for the heat source
sim_config.add_update_initial_value(  # Heat flow into CV1
    component_name='HeatSource',
    variable='amplitude',
    value=2000,
    type_value=float
)

# Run simulation, retrieve the result and plot it
sim_output = sim_config.run_simulation(duration=100, logging_level=LoggingLevel.info)
if len(sim_output.error) > 0:
    raise SimulationError(f'There was an error running the simulation\n{sim_output.error}')
df_result = sim_output.result
_, ax = plt.subplots()
df_scenario2.plot(x='time{s}', ax=ax, figsize=PLOT_SIZE)  # Reference plot
df_result['ControlVolume1'].drop(['StepCount'], axis=1).plot(x='Time', ax=ax, figsize=PLOT_SIZE)
df_result['ControlVolume2'].drop(['StepCount'], axis=1).plot(x='Time', ax=ax, figsize=PLOT_SIZE)
plt.show()

# Cost function
def cost(c_cv2: float) -> float:
    """Cost function for the optimiaztion"""
    sim_config.add_update_initial_value(  # Specific heat capacity of CV1
        component_name='ControlVolume2',
        variable='c',
        value=c_cv2,
        type_value=float
    )
    output = sim_config.run_simulation(duration=100)
    if len(output.error) > 0:
        raise SimulationError(f'There was an error running the simulation\n{sim_output.error}')
    time_ref = df_scenario2['time{s}'].values
    temp_cv1_ref = df_scenario2['ControlVolume1\C\p.T{K}'].values
    time_sim = output.result['ControlVolume1']['Time'].values
    temp_cv1_sim = output.result['ControlVolume1']['p_transfer_out.T'].values
    interp = interp1d(x=time_sim, y=temp_cv1_sim, kind='cubic', fill_value="extrapolate")
    temp_cv1_sim_int = interp(time_ref)
    temp_cv2_ref = df_scenario2['ControlVolume2\C\p.T{K}'].values
    time_sim = output.result['ControlVolume2']['Time'].values
    temp_cv2_sim = output.result['ControlVolume2']['p_transfer_in.T'].values
    interp = interp1d(x=time_sim, y=temp_cv2_sim, kind='cubic', fill_value='extrapolate')
    temp_cv2_sim_int = interp(time_ref)
    square_error = np.sum(
        np.square(temp_cv1_ref - temp_cv1_sim_int) +
        np.square(temp_cv2_ref - temp_cv2_sim_int)
    )
    print(f'c: {c_cv2}, square_error: {square_error}')
    return square_error

# Run optimization
res = minimize_scalar(cost, bounds=(0, 10000), method='bounded')
print(f'Heat capacity of the control volume 2 is {res.x}.')
sim_config.add_update_initial_value(
    component_name='ControlVolume2',
    variable='c',
    value=res.x,
    type_value=float
)

# Run simulation with the parameter found and show the result
sim_output = sim_config.run_simulation(duration=100)
df_result = sim_output.result
_, ax = plt.subplots()
df_scenario2.plot(x='time{s}', ax=ax, figsize=PLOT_SIZE)  # Reference plot
df_result['ControlVolume1'].drop(['StepCount'], axis=1).plot(x='Time', ax=ax, figsize=PLOT_SIZE)
df_result['ControlVolume2'].drop(['StepCount'], axis=1).plot(x='Time', ax=ax, figsize=PLOT_SIZE)
plt.show()
