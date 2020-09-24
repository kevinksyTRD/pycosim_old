"""Testing SimulationConfiguration Class"""

import json
import os
import random
import string
from functools import reduce
from typing import Tuple

import pytest
import numpy as np
from pyOSPParser.logging_configuration import OspLoggingConfiguration, OspSimulatorForLogging, \
    OspVariableForLogging
from pyOSPParser.model_description import OspLinearMechanicalPortType, OspForceType, \
    OspVariableType, OspLinearVelocityType
from pyOSPParser.scenario import OSPScenario, OSPEvent
from pyOSPParser.system_configuration import OspSystemStructure, OspVariableEndpoint, FunctionType,\
    OspSignalEndpoint

from pycosim.osp_command_line_interface import LoggingLevel, SimulationError
from pycosim.simulation import FMU, SimulationConfiguration, Component

PATH_TO_FMU = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fmus', 'chassis.fmu')
PATH_TO_FMU_DIR = os.path.dirname(PATH_TO_FMU)
PATH_TO_SYSTEM_STRUCTURE_FILE = os.path.join(PATH_TO_FMU_DIR, 'OspSystemStructure.xml')
PATH_TO_LOG_CONFIG = os.path.join(PATH_TO_FMU_DIR, 'LogConfig.xml')


def get_random_string(length: int = 5):
    """Generates a random string of given length"""
    return ''.join(random.sample(string.ascii_lowercase, k=length))


def test_initialization():
    with pytest.raises(AssertionError):
        sim_config = SimulationConfiguration(
            system_structure=PATH_TO_SYSTEM_STRUCTURE_FILE
        )
    sim_config = SimulationConfiguration(
        system_structure=PATH_TO_SYSTEM_STRUCTURE_FILE,
        path_to_fmu=PATH_TO_FMU_DIR
    )
    system_struct = OspSystemStructure(
        xml_source=PATH_TO_SYSTEM_STRUCTURE_FILE
    )
    assert sim_config.system_structure.to_xml_str() == system_struct.to_xml_str()
    assert len(sim_config.components) == len(sim_config.system_structure.Simulators)
    num_initial_values = sum(map(
        lambda x: len(x.InitialValues) if x.InitialValues else 0,
        system_struct.Simulators
    ))
    assert len(sim_config.initial_values) == num_initial_values
    with pytest.raises(AssertionError):
        sim_config.scenario = ''
    with pytest.raises(AssertionError):
        sim_config.logging_config = ''


@pytest.fixture
def sim_config_from_xml() -> SimulationConfiguration:
    return SimulationConfiguration(
        system_structure=PATH_TO_SYSTEM_STRUCTURE_FILE,
        path_to_fmu=PATH_TO_FMU_DIR
    )


@pytest.fixture
def sim_config_empty() -> SimulationConfiguration:
    """Fixture for pytest"""
    return SimulationConfiguration()


def choose_variable_and_value_not_found_in_other_initial_values(
        sim_config: SimulationConfiguration,
        component: Component
) -> Tuple[str, float]:
    """Chooses a variable and a value from a component that are not found in other initial values"""
    while True:  # Make sure the new initial value is not found in the existing ones
        variable = random.choice(component.fmu.get_parameter_names())
        value = random.random() * 100
        try:
            sim_config.get_initial_value_by_variable(
                component=component.name,
                variable=variable
            )
        except TypeError:
            break
    return variable, value


def test_simulation_configuration_add_delete_component(sim_config_from_xml):
    """Test adding a component that has the same name as one of those that exist already."""
    component_exists = random.choice(sim_config_from_xml.components)
    with pytest.raises(TypeError):
        sim_config_from_xml.add_component(name=component_exists.name, fmu=component_exists.fmu)

    # Test adding a component with a different name
    num_components_before = len(sim_config_from_xml.components)
    component_added = sim_config_from_xml.add_component(
        name=get_random_string(), fmu=component_exists.fmu
    )
    num_components_after = len(sim_config_from_xml.components)
    assert num_components_after == num_components_before + 1
    assert num_components_after == len(sim_config_from_xml.system_structure.Simulators)

    # Test deleting a component
    num_components_before = num_components_after
    assert sim_config_from_xml.delete_component(component_added.name)
    with pytest.raises(TypeError):
        sim_config_from_xml.delete_component(component_added.name)
    assert num_components_before == len(sim_config_from_xml.components) + 1


def test_add_update_delete_initial_value(sim_config_from_xml):
    """Test adding an invalid initial value"""
    component = random.choice(sim_config_from_xml.components)
    with pytest.raises(TypeError):
        sim_config_from_xml.add_update_initial_value(
            component_name=component.name,
            variable=get_random_string(5),  # insensible variable name
            value=10.0
        )
    with pytest.raises(TypeError):
        sim_config_from_xml.add_update_initial_value(
            component_name=get_random_string(5),  # insensible component name
            variable=random.choice(component.fmu.get_parameter_names()),
            value=12.0
        )


def test_adding_an_initial_value(sim_config_from_xml):
    """Test adding an initial value"""
    num_initial_values_before = len(sim_config_from_xml.initial_values)
    component = random.choice(sim_config_from_xml.components)
    variable, value = choose_variable_and_value_not_found_in_other_initial_values(
        sim_config_from_xml, component
    )
    sim_config_from_xml.add_update_initial_value(
        component_name=component.name,
        variable=variable,
        value=value
    )
    num_initial_values_after = len(sim_config_from_xml.initial_values)
    assert num_initial_values_before == num_initial_values_after - 1
    component = sim_config_from_xml.system_structure.get_component_by_name(component.name)
    # Check if the initial variable is found with the new name in the system structure attribute
    next(init_value for init_value in component.InitialValues if init_value.variable == variable)


def test_updating_the_initial_value(sim_config_from_xml):
    """Test updating the initial value"""
    initial_value_to_update = random.choice(sim_config_from_xml.initial_values)
    num_initial_values_before = len(sim_config_from_xml.initial_values)
    init_value = sim_config_from_xml.add_update_initial_value(
        component_name=initial_value_to_update.component,
        variable=initial_value_to_update.variable,
        value=random.random()
    )
    init_value_updated = sim_config_from_xml.get_initial_value_by_variable(
        component=init_value.component,
        variable=init_value.variable
    )
    assert init_value.value == init_value_updated.value
    component = sim_config_from_xml.system_structure.get_component_by_name(
        initial_value_to_update.component
    )
    init_value_sys_struct = next(
        value for value in component.InitialValues if value.variable == init_value.variable
    )
    assert init_value.value == init_value_sys_struct.value.value
    num_initial_values_after = len(sim_config_from_xml.initial_values)
    assert num_initial_values_before == num_initial_values_after
    num_initial_values_after = sum(map(
        lambda comp: len(comp.InitialValues) if comp.InitialValues else 0,
        sim_config_from_xml.system_structure.Simulators
    ))
    assert num_initial_values_before == num_initial_values_after


def test_deleting_the_initial_value(sim_config_from_xml):
    """Test deleting the initial value"""
    component = random.choice(sim_config_from_xml.components)
    init_value_to_be_deleted = random.choice(sim_config_from_xml.initial_values)
    num_initial_values_before = len(sim_config_from_xml.initial_values)
    sim_config_from_xml.delete_initial_value(
        component=init_value_to_be_deleted.component,
        variable=init_value_to_be_deleted.variable
    )
    assert num_initial_values_before == len(sim_config_from_xml.initial_values) + 1
    with pytest.raises(TypeError):
        sim_config_from_xml.get_initial_value_by_variable(
            component=init_value_to_be_deleted.component,
            variable=init_value_to_be_deleted.variable
        )
    component = sim_config_from_xml.system_structure.get_component_by_name(component.name)
    if component.InitialValues is not None:
        num_initial_values_after = sum(map(
            lambda comp: len(comp.InitialValues) if comp.InitialValues else 0,
            sim_config_from_xml.system_structure.Simulators
        ))
        assert num_initial_values_before == num_initial_values_after + 1
        with pytest.raises(StopIteration):
            next(
                init_value for init_value in component.InitialValues
                if init_value.variable == init_value_to_be_deleted.variable
            )


def test_simulation_configurtion_add_delete_connection():
    """Testing adding/deleting connection for SimulationConfiguration"""
    sim_config = SimulationConfiguration()
    component_names = ['chassis.fmu', 'wheel.fmu', 'ground.fmu']
    for comp in component_names:
        sim_config.add_component(
            fmu=FMU(os.path.join(PATH_TO_FMU_DIR, comp)),
            name=os.path.splitext(comp)[0]
        )
    # Test adding a proper connection
    [source_comp, target_comp] = random.sample(sim_config.components, k=2)
    source_endpoint = OspVariableEndpoint(
        simulator=source_comp.name,
        name=random.choice(source_comp.fmu.get_output_names())
    )
    target_endpont = OspVariableEndpoint(
        simulator=target_comp.name,
        name=random.choice(target_comp.fmu.get_input_names())
    )
    var_connection = sim_config.add_connection(source_endpoint, target_endpont, group=False)
    number_connections_after = len(sim_config.system_structure.Connections.VariableConnection)
    assert var_connection in sim_config.system_structure.Connections.VariableConnection
    assert number_connections_after == 1

    # Test adding the same connection
    with pytest.raises(TypeError):
        sim_config.add_connection(source_endpoint, target_endpont, group=False)

    # Test adding a variable group connection
    var_group1 = OspLinearMechanicalPortType(
        name='contact_to_wheel',
        Force=OspForceType(
            name='linear_force',
            Variable=[OspVariableType(ref='p.e')]
        ),
        LinearVelocity=OspLinearVelocityType(
            name='linear_velocity',
            Variable=[OspVariableType(ref='p.f')]
        )
    )
    var_group2 = OspLinearMechanicalPortType(
        name='contact_to_chassis',
        Force=OspForceType(
            name='linear_force',
            Variable=[OspVariableType(ref='p1.e')]
        ),
        LinearVelocity=OspLinearVelocityType(
            name='linear_velocity',
            Variable=[OspVariableType(ref='p1.f')]
        )
    )
    sim_config.components[0].fmu.add_variable_group(var_group1)
    sim_config.components[1].fmu.add_variable_group(var_group2)
    var_group_connection = sim_config.add_connection(
        source=OspVariableEndpoint(simulator='chassis', name='contact_to_wheel'),
        target=OspVariableEndpoint(simulator='wheel', name='contact_to_chassis'),
        group=True
    )
    assert len(sim_config.system_structure.Connections.VariableGroupConnection) == 1

    # Test adding a signal connection
    sim_config.add_function(
        function_name='linear_transform',
        function_type=FunctionType.LinearTransformation,
        factor=1.5,
        offset=0.0
    )
    var_endpoint = OspVariableEndpoint(simulator='chassis', name='p.e')
    sig_endpoint = OspSignalEndpoint(function='linear_transform', name='in')
    sig_connection = sim_config.add_connection(
        source=var_endpoint, target=sig_endpoint, group=False
    )
    assert len(sim_config.system_structure.Connections.SignalConnection) == 1

    # Test deleting a signal connection
    sim_config.delete_connection(
        endpoint1=sig_connection.Signal,
        endpoint2=sig_connection.Variable
    )
    assert sim_config.system_structure.Connections.SignalConnection is None

    # Test deleting a variable group connection
    sim_config.delete_connection(
        endpoint1=var_group_connection.VariableGroup[0],
        endpoint2=var_group_connection.VariableGroup[1]
    )
    assert sim_config.system_structure.Connections.VariableGroupConnection is None

    # Test deleting a variable connection
    sim_config.delete_connection(
        endpoint1=var_connection.Variable[0],
        endpoint2=var_connection.Variable[1]
    )
    assert sim_config.system_structure.Connections is None


def test_get_fmu_rel_path():
    """Testng get_fmu_rel_path method"""
    sim_config = SimulationConfiguration()
    for _ in range(3):
        num_depth = random.randint(0, 5)
        path_to_deploy = 'abc'
        path_to_sys_struct = path_to_deploy
        for _ in range(num_depth):
            path_to_sys_struct = os.path.join(path_to_sys_struct, get_random_string())
        fmu_rel_path = sim_config.get_fmu_rel_path(path_to_deploy, path_to_sys_struct)
        num_depth_calculated = fmu_rel_path.count('../')
        assert num_depth == num_depth_calculated
        fmu_rel_path = sim_config.get_fmu_rel_path(path_to_sys_struct, path_to_deploy)
        if len(fmu_rel_path) == 0:
            assert path_to_deploy == path_to_sys_struct
        else:
            assert path_to_sys_struct == os.path.join(
                path_to_deploy,
                reduce(os.path.join, fmu_rel_path.split('/')[:-1])
            )


def test_deployment():
    """Test deployment of files for simulation"""
    sim_config = SimulationConfiguration(
        system_structure=PATH_TO_SYSTEM_STRUCTURE_FILE,
        path_to_fmu=PATH_TO_FMU_DIR
    )
    path_to_deploy = sim_config.prepare_temp_dir_for_simulation()
    assert os.path.isdir(path_to_deploy)

    # Test deploy_files_for_simulation method
    path_to_system_structure = sim_config.deploy_files_for_simulation(
        path_to_deploy=path_to_deploy,
        rel_path_to_system_structure='system_structure'
    )
    assert os.path.isdir(path_to_system_structure)
    assert os.path.join(path_to_deploy, 'system_structure') == path_to_system_structure
    assert os.path.isfile(os.path.join(path_to_system_structure, 'OspSystemStructure.xml'))
    assert all(
        list(map(
            lambda x: os.path.isfile(
                os.path.join(path_to_deploy, os.path.basename(x.fmu.fmu_file))
            ),
            sim_config.components
        )))

    # deploy again and see if the previous directory has been deleted.
    path_to_deploy_again = sim_config.prepare_temp_dir_for_simulation()
    sim_config.deploy_files_for_simulation(path_to_deploy_again)
    assert path_to_deploy != path_to_deploy_again
    assert not os.path.isdir(path_to_deploy)
    assert os.path.isdir(path_to_deploy_again)


def test_adding_event_without_scenario(sim_config_from_xml):
    """Test adding event without scenario"""
    component = random.choice(sim_config_from_xml.components)
    with pytest.raises(TypeError):
        sim_config_from_xml.add_event(
            time=random.random(),
            component=component.name,
            variable=random.choice(component.fmu.get_parameter_names()),
            action=OSPEvent.OVERRIDE,
            value=random.random() * 10
        )

def test_adding_event_with_invalid_model_name(sim_config_from_xml):
    """Test with wrong model name"""
    component = random.choice(sim_config_from_xml.components)
    sim_config_from_xml.set_scenario(name='test_scenario', end=100)
    with pytest.raises(TypeError):
        sim_config_from_xml.add_event(
            time=random.random() * sim_config_from_xml.scenario.end,
            component=get_random_string(5),
            variable=random.choice(component.fmu.get_parameter_names()),
            action=OSPEvent.OVERRIDE,
            value=random.random() * 10
        )

def test_adding_event_with_invalid_variable_name(sim_config_from_xml):
    """Test with a invalid variable name"""
    component = random.choice(sim_config_from_xml.components)
    sim_config_from_xml.set_scenario(name='test_scenario', end=100)
    with pytest.raises(TypeError):
        sim_config_from_xml.add_event(
            time=random.random() * sim_config_from_xml.scenario.end,
            component=component.name,
            variable=get_random_string(5),
            action=OSPEvent.OVERRIDE,
            value=random.random() * 10
        )

def test_adding_updating_and_deleting_event(sim_config_from_xml):
    """Test adding/updating/deleting events"""
    sim_config_from_xml.set_scenario(name='test_scenario', end=100)
    number_events = random.randint(5, 10)
    events = []
    for _ in range(number_events):
        component = random.choice(sim_config_from_xml.components)
        events.append(sim_config_from_xml.add_event(
            time=random.random() * sim_config_from_xml.scenario.end,
            component=component.name,
            variable=random.choice(component.fmu.get_parameter_names()),
            action=OSPEvent.OVERRIDE,
            value=random.random() * 10
        ))
    assert len(sim_config_from_xml.scenario.events) == number_events

    event_to_update = random.choice(sim_config_from_xml.scenario.events)
    time = event_to_update.time
    component = event_to_update.model
    variable = event_to_update.variable
    new_action = random.choice([OSPEvent.OVERRIDE, OSPEvent.BIAS, OSPEvent.RESET])
    new_value = random.random()
    updatd_event = sim_config_from_xml.scenario.update_event(
        time=time, component=component, variable=variable, action=new_action, value=new_value
    )
    assert len(sim_config_from_xml.scenario.events) == number_events
    assert updatd_event.action == new_action
    assert updatd_event.value == new_value

    component = random.choice(sim_config_from_xml.components)
    events_deleted = sim_config_from_xml.delete_events(component=component.name)
    assert len(sim_config_from_xml.scenario.events) == number_events - len(events_deleted)
    assert all(map(lambda event: event.model == component.name, events_deleted))


def test_run():

    simulation_end_time = 10 + random.random() * 90

    sim_config = SimulationConfiguration(
        system_structure=PATH_TO_SYSTEM_STRUCTURE_FILE,
        path_to_fmu=PATH_TO_FMU_DIR,
    )

    scenario = OSPScenario(
        name='test_scenario',
        end=0.5*simulation_end_time
    )

    scenario.add_event(OSPEvent(
        time=0.5 * scenario.end,
        model=sim_config.components[0].name,
        variable=random.choice(sim_config.components[0].fmu.parameters).get('name'),
        action=OSPEvent.OVERRIDE,
        value=random.random() * 10
    ))
    sim_config.scenario = scenario

    assert type(scenario.events[0].variable) is str

    sim_config.logging_config = OspLoggingConfiguration(
        simulators=list(
            map(
                lambda comp: OspSimulatorForLogging(
                    name=comp.name,
                    variables=[
                        OspVariableForLogging(name=variable.get('name'))
                        for variable in random.choices(comp.fmu.outputs, k=4)
                    ]
                ),
                sim_config.components
            )
        )
    )

    output = sim_config.run_simulation(
        duration=simulation_end_time,
        rel_path_to_sys_struct="system_structure",
        logging_level=LoggingLevel.info
    )
    assert os.path.isdir(output.output_file_path)
    path_to_scenario_file = os.path.join(output.output_file_path, scenario.get_file_name())
    assert os.path.isfile(path_to_scenario_file)
    path_to_logging_config_file = os.path.join(output.output_file_path, 'LogConfig.xml')
    assert os.path.isfile(path_to_logging_config_file)
    output_files = [
        file_name for file_name in os.listdir(output.output_file_path)
        if file_name.endswith('.csv')
    ]
    assert len(output_files) == len(sim_config.logging_config.simulators)
    assert len(output.result) == len(sim_config.logging_config.simulators)
    assert simulation_end_time == pytest.approx(
        output.result[sim_config.components[0].name]['Time'].values[-1], rel=1e-3
    )

    print(output.result)

    # Test if the time step option is effective
    sim_config.set_base_step_size(0.02)
    output = sim_config.run_simulation(
        duration=simulation_end_time,
        rel_path_to_sys_struct="system_structure",
        logging_level=LoggingLevel.info
    )
    if len(output.error) > 0:
        raise SimulationError(f'An error or errors occured during the simulation: {output.error}')
    assert np.all(
        np.round(np.diff(output.result[sim_config.components[0].name]['Time'].values), 3) == 0.02
    )
