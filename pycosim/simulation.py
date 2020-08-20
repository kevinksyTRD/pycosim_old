import os
import shutil
import uuid
from enum import Enum
from sys import platform
from typing import NamedTuple, Union, List, Dict, Tuple

import pandas
from pyOSPParser.logging_configuration import OspLoggingConfiguration
from pyOSPParser.model_description import OspModelDescription, OspVariableGroupsType
from pyOSPParser.scenario import OSPScenario
from pyOSPParser.system_configuration import OspSystemStructure, OspSimulator

from .osp_command_line_interface import get_model_description, run_cosimulation, LoggingLevel, run_single_fmu

COSIM_FILE_NAME = 'cosim' if platform.startswith("linux") else 'cosim.exe'

PATH_TO_COSIM = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'cosim', COSIM_FILE_NAME
)


class FMU:
    """Class for managing FMU"""
    osp_model_description: OspModelDescription = None

    def __init__(self, fmu_file: str):
        """Constructor for FMU"""
        assert fmu_file.endswith('.fmu')
        self.fmu_file = fmu_file
        if os.path.isfile(fmu_file):
            self.get_fmu_information_from_file()
            # Check if there is OSP Model description file in the same directory
            osp_model_description_file = os.path.join(
                os.path.dirname(self.fmu_file),
                '%s_OspModelDescription.xml' % self.name
            )
            if os.path.isfile(osp_model_description_file):
                self.get_osp_model_description(osp_model_description_file)

        else:
            self.name = None
            self.uuid = None
            self.description = None
            self.parameters = None
            self.inputs = None
            self.outputs = None
            self.other_variables = None

    def get_fmu_information_from_file(self):
        model_description = get_model_description(self.fmu_file)
        self.name = model_description.name
        self.uuid = model_description.uuid
        self.description = model_description.description
        self.parameters = model_description.model_variable.parameters
        self.inputs = model_description.model_variable.inputs
        self.outputs = model_description.model_variable.outputs
        self.other_variables = model_description.model_variable.others

    def get_osp_model_description(self, xml_source: str):
        """Import OSP Model Description file or string

        Args:
            xml_source: Path to the file or string content of the OSP model description
        """
        self.osp_model_description = OspModelDescription(xml_source=xml_source)

    def get_endpoint_dict(self):
        return {
            'input': self.inputs,
            'output': self.outputs,
            'variable_group': self.osp_model_description.to_dict().get('VariableGroups', None)
            if self.osp_model_description is not None else None
        }

    def add_variable_group(self, var_group: OspVariableGroupsType):
        if self.osp_model_description is None:
            self.osp_model_description = OspModelDescription(VariableGroups=[var_group])
        else:
            self.osp_model_description.add_interface(var_group)

    def run_simulation(
            self,
            initial_values: Dict[str, Union[float, bool]] = None,
            output_file_path: str = None,
            duration: float = None,
            step_size: float = None,
    ) -> Tuple[pandas.DataFrame, str]:
        """Runs a single FMU simulation

        Args:
            initial_values(Dict[str, Union[float, bool]], optional): dictionary of initial values
            output_file_path(str, optional): file path for the output including the file name
            duration(float, optional): duration of simulation in seconds
            step_size(float, optional): duration
        Return:
            (tuple): tuple containing:
                result(pandas.DataFrame) simulation result
                log(str) simulation logging
        """
        return run_single_fmu(
            path_to_fmu=self.fmu_file,
            initial_values=initial_values,
            output_file_path=output_file_path,
            duration=duration,
            step_size=step_size
        )


class Component(NamedTuple):
    name: str
    fmu: FMU


class Causality(Enum):
    input = "input"
    output = "output"
    indefinite = "indefinite"


class InitialValues(NamedTuple):
    component: str
    variable: str
    value: Union[float, int, bool, str]


class SimulationOutput(NamedTuple):
    result: Dict[str, pandas.DataFrame]
    log: str
    output_file_path: str


class SimulationConfiguration:
    """Class for running simulation"""
    components: List[Component] = []
    initial_values: List[InitialValues] = []
    system_structure: OspSystemStructure = None
    _scenario: OSPScenario = None
    _logging_config: OspLoggingConfiguration = None
    _current_sim_path: str = None

    # add_component(name: str, fmu: fmu)
    # add_initial_value(comp_name: str, variable_name: str, value: float)
    # get_initial_values()
    # add_variable_interface(source: VariableInterface, target: VariableInterface)
    # get_variable_interfaces()

    def __init__(
            self,
            system_structure: str = None,
            path_to_fmu: str = None,
            components: List[Component] = None,
            initial_values: List[InitialValues] = None,
            scenario: OSPScenario = None,
            logging_config: OspLoggingConfiguration = None,
    ):
        """Constructor for SimulationConfiguration class

        Args:
            system_structure(optional): A source for the system structure, either string content of the
            XML file or path to the file. Must be given together with the path_to_fmu argument..
            path_to_fmu(optional): A path to the FMUs for the given system structure.
            components(optional): Components for the system given as a list of Component instance
            initial_values(optional): Initial values for the simulation given as a list of InitialValues instance
            scenario(optional): A scenario for the simulation given as a OSPScenario instance
            logging_config(optional): A logging configuration for the output of the simulation given as a
            OSPScenario instance
        """
        if system_structure:
            assert path_to_fmu is not None, "The path to fmu should be given together with the system structure"
            self.system_structure = OspSystemStructure(xml_source=system_structure)
            self.components = []
            self.initial_values = []
            for Simulator in self.system_structure.Simulators:
                self.components.append(Component(
                    name=Simulator.name,
                    fmu=FMU(os.path.join(path_to_fmu, Simulator.source))
                ))
                if Simulator.InitialValues:
                    self.initial_values.extend([InitialValues(
                        component=Simulator.name,
                        variable=initial_value.variable,
                        value=initial_value.value.value
                    ) for initial_value in Simulator.InitialValues])
            if len(self.initial_values) == 0:
                # noinspection PyTypeChecker
                self.initial_values = None
        else:
            if components:
                for comp in components:
                    assert type(comp) is Component
                self.components = components
            if initial_values:
                for init_value in initial_values:
                    assert type(init_value) is InitialValues
                self.initial_values = initial_values
        if scenario:
            self.scenario = scenario
        if logging_config:
            self.logging_config = logging_config

    def __del__(self):
        """Destructor for the class

        Deletes the deployed directory and files for the simulation.
        """
        if self._current_sim_path:
            if os.path.isdir(self._current_sim_path):
                shutil.rmtree(self._current_sim_path)

    @property
    def scenario(self):
        return self._scenario

    @scenario.setter
    def scenario(self, value):
        assert type(value) is OSPScenario
        self._scenario = value

    @property
    def logging_config(self):
        return self._logging_config

    @logging_config.setter
    def logging_config(self, value):
        assert type(value) is OspLoggingConfiguration
        self._logging_config = value

    @property
    def current_simulation_path(self):
        return self._current_sim_path

    @staticmethod
    def prepare_temp_dir_for_simulation() -> str:
        base_dir_name = os.path.join('pycosim_tmp', f'sim_{uuid.uuid4().__str__()}')

        if platform.startswith('win'):
            path = os.path.join(os.environ.get('TEMP'), base_dir_name)
        else:
            path = os.path.join(os.environ.get('TMPDIR'), base_dir_name) if os.environ.get('TMPDIR') \
                else os.path.join('/var', 'tmp', base_dir_name)
        if not os.path.isdir(path):
            os.makedirs(path)
        return path

    @staticmethod
    def get_fmu_rel_path(path_to_deploy: str, path_to_sys_struct: str):
        if len(path_to_deploy) > len(path_to_sys_struct):
            rel_path = path_to_deploy[len(path_to_sys_struct):].replace(os.sep, "/")[1:]
            if len(rel_path) > 0:
                return f'{rel_path}/'
            else:
                return ''
        else:
            rel_path = path_to_sys_struct[len(path_to_deploy):]
            depth = rel_path.count(os.sep)
            return '../' * depth

    def deploy_files_for_simulation(
            self,
            path_to_deploy: str,
            rel_path_to_system_structure: str = '',
    ) -> str:
        """Deploy files for the simulation

        Returns:
            str: path to the system structure file
        """
        # Update the state for the current path
        if self._current_sim_path:
            if os.path.isdir(self._current_sim_path):
                shutil.rmtree(self._current_sim_path)
        self._current_sim_path = path_to_deploy

        # Create a fmu list from the components
        fmus = []
        fmu_names = []
        for comp in self.components:
            if comp.fmu.name not in fmu_names:
                fmus.append(comp.fmu)
                fmu_names.append(comp.fmu.name)
        for fmu in fmus:
            destination_file = os.path.join(path_to_deploy, os.path.basename(fmu.fmu_file))
            shutil.copyfile(fmu.fmu_file, destination_file)

        # Check out with the path for the system structure file. If it doesn't exist
        # create the directory.
        path_to_sys_struct = os.path.join(path_to_deploy, rel_path_to_system_structure)
        if not os.path.isdir(path_to_sys_struct):
            os.mkdir(path_to_sys_struct)

        # Create a system structure file
        fmu_rel_path = self.get_fmu_rel_path(path_to_deploy, path_to_sys_struct)
        for component in self.system_structure.Simulators:
            component.fmu_rel_path = fmu_rel_path
        with open(os.path.join(path_to_sys_struct, 'OspSystemStructure.xml'), 'wt') as file:
            file.write(self.system_structure.to_xml_str())

        return path_to_sys_struct

    def run_simulation(
            self,
            duration: float,
            rel_path_to_sys_struct: str = '',
            logging_level: LoggingLevel = LoggingLevel.warning
    ):
        path = self.prepare_temp_dir_for_simulation()
        path_to_sys_struct = self.deploy_files_for_simulation(
            path_to_deploy=path,
            rel_path_to_system_structure=rel_path_to_sys_struct,
        )
        result, log = run_cosimulation(
            path_to_system_structure=path_to_sys_struct,
            logging_config=self.logging_config,
            output_file_path=path_to_sys_struct,
            scenario=self._scenario,
            duration=duration,
            logging_level=logging_level,
            logging_stream=True
        )

        return SimulationOutput(
            result=result,
            log=log,
            output_file_path=path_to_sys_struct
        )

    def add_component(
            self,
            name: str,
            fmu: FMU,
            stepSize: float = None,
            rel_path_to_fmu: str = ''
    ) -> Component:
        """Add a component to the system structure

        Args:
            name: Name of the component
            fmu: The model for the component given as FMU instance
            stepSize(optional): Step size for the simulator in seconds. If not given, its default value is used.
            rel_path_to_fmu(optional): Relative path to fmu from a system structure file.
        Return:
            Component: the created component.
        """
        # Add component only in case the name is unique.
        if name not in [component.name for component in self.components]:
            # Create the instance and add it to the member
            component = Component(name=name, fmu=fmu)
            self.components.append(component)

            # Update the system_structure instance. Create one if it has not been initialized.
            if not self.system_structure:
                self.system_structure = OspSystemStructure()
            self.system_structure.add_simulator(OspSimulator(
                name=name,
                source=os.path.basename(fmu.fmu_file),
                stepSize=stepSize,
                fmu_rel_path=rel_path_to_fmu
            ))
            return component
        else:
            raise NameError('The name duplicates with the existing components.')
