import os
import random

import numpy as np
import pandas
from pyOSPParser.logging_configuration import OspLoggingConfiguration
from pyOSPParser.scenario import OSPScenario, OSPEvent

from pycosim.osp_command_line_interface import get_model_description, run_single_fmu, ModelVariables, run_cosimulation, \
    LoggingLevel

path_to_fmu = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'fmus',
    'ControlVolume.fmu'
)

path_to_system_structure = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'fmus'
)


def test_get_model_description():
    model_description = get_model_description(path_to_fmu)
    assert model_description.name == 'ControlVolume'
    assert model_description.uuid != ''
    assert type(model_description.model_variable) is ModelVariables
    assert len(model_description.model_variable.parameters) > 0
    assert len(model_description.model_variable.inputs) > 0
    assert len(model_description.model_variable.outputs) > 0
    assert len(model_description.model_variable.others) > 0
    print('Parameters:')
    for param in model_description.model_variable.get_parameters_names():
        print('\t%s' % param)
    print('Inputs:')
    for param in model_description.model_variable.get_input_names():
        print('\t%s' % param)
    print('Outputs:')
    for param in model_description.model_variable.get_output_names():
        print('\t%s' % param)
    print('Others:')
    for param in model_description.model_variable.get_other_variable_names():
        print('\t%s' % param)


def test_run_single_fmu():
    result, log = run_single_fmu(path_to_fmu)

    # Check if the output file does not exist if the output_file_path is not given
    assert not os.path.isfile('model-output.csv')
    print('')
    print(result)

    # Check if the file exists if the output_file_path is given
    output_file_path = 'output.csv'
    run_single_fmu(path_to_fmu, output_file_path=output_file_path)
    assert os.path.isfile(output_file_path)
    os.remove(output_file_path)

    # Check if the initial values are effective
    initial_values = {
        'p_loss.T': 330,
        'p_in.dQ': 100,
    }
    result, _ = run_single_fmu(path_to_fmu, initial_values=initial_values)
    # Collect the column names that matches the initial value specified
    columns = [column for column in result.columns if any(list(map(lambda x: column.startswith(x), initial_values)))]
    for column in columns:
        for key in initial_values:
            if column.startswith(key):
                break
        # Compare the initial value
        # noinspection PyUnboundLocalVariable
        comparison = result[column].values == initial_values[key]
        assert all(comparison.tolist())

    # Check if the duration arg is effective
    # Duration is rounded to the second decimal place because the
    # step size is 0.01 by default.
    duration = np.round(random.random() * 10, 2)
    result, _ = run_single_fmu(path_to_fmu, duration=duration)
    assert result['Time'].values[-1] == duration

    # Check if the step size arg is effective
    step_size = 0.05
    result, _ = run_single_fmu(path_to_fmu, step_size=step_size)
    step_size_sim = np.diff(result['Time'].values)
    assert np.any(step_size_sim == step_size)


def test_run_cosimulation():
    duration = random.randint(5, 10)
    result, log = run_cosimulation(
        path_to_system_structure=path_to_system_structure,
        duration=duration,
        logging_level=LoggingLevel.info,
        logging_stream=True
    )
    for each in result:
        assert type(result[each]) is pandas.DataFrame
        assert result[each]['Time'].values[-1] == duration
    assert type(log) is str
    assert len(log) > 0

    # Test with logging configuration and output directory
    path_to_sim_temp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sim_temp')
    path_to_logging_config = os.path.join(path_to_sim_temp, 'LogConfig.xml')
    logging_config = OspLoggingConfiguration(xml_source=path_to_logging_config)
    result, log = run_cosimulation(
        path_to_system_structure=path_to_system_structure,
        output_file_path=path_to_sim_temp,
        logging_config=logging_config,
        logging_level=LoggingLevel.info,
        logging_stream=True
    )
    output_files = [file_name for file_name in os.listdir(path_to_sim_temp) if file_name.endswith('.csv')]
    for file_name in output_files:
        os.remove(os.path.join(path_to_sim_temp, file_name))
    os.remove(os.path.join(path_to_system_structure, 'LogConfig.xml'))
    assert len(output_files) == len(logging_config.simulators)
    for simulator in logging_config.simulators:
        assert len(result[simulator.name].columns) == len(simulator.variables) + 2
        for variable in simulator.variables:
            assert variable.name in result[simulator.name].columns

    # Test with a scenario
    duration = 50
    model = 'chassis'
    variable = 'C.mChassis'
    scenario = OSPScenario(name='test scenario', end=50)
    scenario.add_event(
        OSPEvent(time=5, model=model, variable=variable, action=OSPEvent.OVERRIDE, value=500)
    )
    scenario.add_event(
        OSPEvent(time=15, model=model, variable=variable, action=OSPEvent.OVERRIDE, value=600)
    )
    scenario.add_event(
        OSPEvent(time=30, model=model, variable=variable, action=OSPEvent.OVERRIDE, value=700)
    )
    scenario.add_event(
        OSPEvent(time=45, model=model, variable=variable, action=OSPEvent.OVERRIDE, value=800)
    )
    result, log = run_cosimulation(
        path_to_system_structure=path_to_system_structure,
        duration=duration,
        scenario=scenario,
        logging_level=LoggingLevel.info,
        logging_stream=True
    )
    print(log)
    os.remove(os.path.join(path_to_system_structure, scenario.get_file_name()))

    time_array = result[model]['Time'].values
    for i, event in enumerate(scenario.events):
        if i < len(scenario.events) - 1:
            next_event = scenario.events[i + 1]
            index = np.bitwise_and(time_array > event.time, time_array <= next_event.time)
        else:
            index = time_array > event.time
        assert np.all(result[model][variable].values[index] == event.value)
