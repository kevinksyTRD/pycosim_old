# pycosim

pycosim is a package for running co-simulation using cosim-cli from [Open Simulation Project](https://open-simulation-platform.github.io/). It provides an user friendly interface for creating the simulation setups such as logging configuration, scenario, interfaces between models and initial values. 

## Features
- Importing an FMU, getting information of the model description and running a single FMU simulation,
- Importing a system configuration, configuring output logging and scenario, running co-simulation and retrieving the results,

## Getting Started
### Prerequisite
- Operation system: Windows 7 or later 
- Python > 3.6
### Installation
The package can be installed by `pip`:
```bash
> pip install pyCOSIM --extra-index-url=https://test.pypi.org/simple/
```
### Basic Usage
The package provides a SimulationConfiguration class that manages the system configuration and the settings for the simulation, deploys necessary files and run simulations.
To use the class, import the class as follows:
```python
from pycosim.simulation import SimulationConfiguration 
```
A target system can be built up bottom-up from scratch or imported using a system structure file that is usually named, `OspSystemStruct.xml`.
Importing file can be done as follows:
```python
import os
from pycosim.simulation import SimulationConfiguration 

path_or_str_content_of_system_structure_file = os.path.join('base', 'system')  # Path where the systm structure file if found
path_to_dir_for_fmu = 'base' # Path where the fmus are found

sim_config = SimulationConfiguration(
    system_structure=path_or_str_content_of_system_structure_file,
    path_to_fmu=path_to_dir_for_fmu,
)


``` 
Note that the path to the directories that contain all the relevant FMUs should be provided together with the source for the system structure file.
When the system is configured, you can run the simulation for a given simulation time with default settings:
```python
from pycosim.simulation import SimulationConfiguration 

sim_config = SimulationConfiguration(
    system_structure='system_path',
    path_to_fmu='base_path',
)

output = sim_config.run_simulation(duration=10.0)
result_comp1 = output.result.get('comp1')  # Get result DataFrame for the component, naemd 'comp1'
log = output.log                           # Logging during the simulation
path_to_output_files = output.output_file_path #Path for the ouput files
```
Default setting for the simulation is:
- No scenario
- No logging configuration (All variables will be logged at each time step.)
- The system structure and output files are saved in the same directory as the temporary one where FMUs are deployed.
- Only warning from simulation setting up and progress messages are logged.

The `run_simulation` method returns NamedTuple instance of output. It has three members:
- result: The result of the simulation given in a dictionary instance. The dictionary has key of names of the components in the system and DataFrame as value for each key that contains all the numerical outputs.
- log: Logged message during setting up and running simulation
- output_file_path: Path to the temporary directory that contains fmus, settings and output csv files.
 
### Scenario configuration
A scenario is a collection of events that override / bias / reset a variable of components in the target system. A scenario can be created as follows:
```python
# Creating a scenario instance
import os
from pyOSPParser.scenario import OSPScenario, OSPEvent
from pycosim.simulation import SimulationConfiguration

sim_config = SimulationConfiguration(
    system_structure='system_path',
    path_to_fmu='base_path',
)

simulation_end_time = 10
scenario = OSPScenario(name='test_scenario', end=simulation_end_time)

# Adding an event to the scenario
scenario.add_event(OSPEvent(
    time=5,  # Time when the event happens
    model='component',  # Name_of_the_component
    variable='variable1', # name_of_the_variable,
    action=OSPEvent.OVERRIDE, # Type of actions among OVERRIDE, BIAS, RESET
    value=19.4 # Value (only for OVERRIDE and BIAS)
))

sim_config.scenario = scenario
``` 
Finally, the scenario instance can be assigned to the system configuration.

### Logging configuration
A logging configuration specifies which variables will be logged as output of the simulation. A logging configuration can be 
defined using OspLoggingConfiguration class:
```python
from pyOSPParser.logging_configuration import OspVariableForLogging, OspSimulatorForLogging, OspLoggingConfiguration
from pycosim.simulation import SimulationConfiguration

sim_config = SimulationConfiguration(
    system_structure='system',
    path_to_fmu='base',
)
# Create a variable object for logging
variable_name = 'variable1'
variable = OspVariableForLogging(name=variable_name)

# Create a logging configuration of a component
name_of_component = 'component1'
logging_config_comp = OspSimulatorForLogging(
    name=name_of_component,
    decimation_factor=1,
    variables=[variable]
)

# Create a logging configuration instance for the system
logging_config = OspLoggingConfiguration(simulators=[logging_config_comp])

sim_config.logging_config = logging_config
```

### Logging level setting
You can set the logging level for the messages during setting up and running a simulation. You can do that
by passing the `LoggingLevel` member when running the simulation. If not specified, it will be 'warning' by default.
```python
    from pycosim.simulation import SimulationConfiguration, LoggingLevel
    
    sim_config = SimulationConfiguration(
    system_structure='system',
    path_to_fmu='base',
)

sim_config.run_simulation(duration=10.0, logging_level=LoggingLevel.info)
```  

## License
Copyright Kevin Koosup Yum, SINTEF Ocean and others 2020

Distributed under the terms of the Apache license 2.0, pycosim is free and open source software.