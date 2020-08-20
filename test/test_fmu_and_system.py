import json
import os
import random
import string
from functools import reduce

import pytest
from pyOSPParser.logging_configuration import OspLoggingConfiguration, OspSimulatorForLogging, OspVariableForLogging
from pyOSPParser.scenario import OSPScenario, OSPEvent
from pyOSPParser.system_configuration import OspSystemStructure

from pycosim.osp_command_line_interface import LoggingLevel
from pycosim.simulation import FMU, SimulationConfiguration


PATH_TO_FMU = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fmus', 'chassis.fmu')
PATH_TO_FMU_DIR = os.path.dirname(PATH_TO_FMU)
PATH_TO_SYSTEM_STRUCTURE_FILE = os.path.join(PATH_TO_FMU_DIR, 'OspSystemStructure.xml')
PATH_TO_LOG_CONFIG = os.path.join(PATH_TO_FMU_DIR, 'LogConfig.xml')


def get_random_string(length: int = 5):
    return ''.join(random.sample(string.ascii_lowercase, k=length))


def test_fmu():
    fmu = FMU(PATH_TO_FMU)

    # Check if the fmu has correct reference, name and uuid
    assert os.path.isfile(fmu.fmu_file)
    assert fmu.name is not None
    assert fmu.uuid is not None
    assert fmu.osp_model_description is not None

    endpoints = fmu.get_endpoint_dict()
    print(json.dumps(endpoints, indent=2))
    assert endpoints.get('input') == fmu.inputs
    assert endpoints.get('output') == fmu.outputs
    assert endpoints.get('variable_group') == fmu.osp_model_description.to_dict().get('VariableGroups')

    # Test running a single FMU simualtion
    finish_time = 10.0
    output_file_path = os.path.join(os.path.dirname(fmu.fmu_file), 'output.csv')
    result, log = fmu.run_simulation(
        initial_values={fmu.inputs[0].get('name'): random.random() * 10},
        output_file_path=output_file_path,
        duration=finish_time,
    )
    assert result['Time'].values[-1] == finish_time
    assert os.path.isfile(output_file_path)
    os.remove(output_file_path)


def test_simulation_configuration_initialization():
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


def test_simulation_configuration_get_fmu_rel_path():
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


def test_simulation_configuration_deployment():
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
            lambda x: os.path.isfile(os.path.join(path_to_deploy, os.path.basename(x.fmu.fmu_file))),
            sim_config.components
        )))

    # deploy again and see if the previous directory has been deleted.
    path_to_deploy_again = sim_config.prepare_temp_dir_for_simulation()
    sim_config.deploy_files_for_simulation(path_to_deploy_again)
    assert path_to_deploy != path_to_deploy_again
    assert not os.path.isdir(path_to_deploy)
    assert os.path.isdir(path_to_deploy_again)


def test_simulation_configuration_run():

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
    output_files = [file_name for file_name in os.listdir(output.output_file_path) if file_name.endswith('.csv')]
    assert len(output_files) == len(sim_config.logging_config.simulators)
    assert len(output.result) == len(sim_config.logging_config.simulators)
    assert simulation_end_time == pytest.approx(
        output.result[sim_config.components[0].name]['Time'].values[-1], rel=1e-3
    )

    print(output.result)
