"""Simulation Module

This module contains two main classes to set up a system and run co-simulation using OSP Cosim.
First FMUs must be created to refer to the actual fmus and retrieve necessary data from them.
Then SimulationConfiguration instance can be created. With the SimulationConfiguration, one may
construct a system in a bottom-up way or load a system from the OspSystemStructure file. When
the system is configured, one may configure logging outputs or create a scenario to run simulation.

Example:
    Building a system

    A system structure can be built in a bottom-up way where an empty system structure is declared
    and component, function, connection, initial values are added afterward.

        from pycosim.simulation import SimulationConfiguration, FMU

        fmu_chassis = FMU(PATH_TO_CHASSIS_FMU_FILE)
        fmu_wheel = FMU(PATH_TO_WHEEL_FMU_FILE)

        sim_config = SimulationConfiguration()  # Creates the instance that contains an empty system
        sim_config.add_component(name='chassis', fmu=fmu_chassis)
        sim_config.add_component(name='wheel', fmu=fmu_wheel)
        sim_config.add_connection(
            source=OspVariableEndpoint(simulator='wheel', name='p1.f'),
            target=OspVariableEndpoint(simulator='chassis', name='p.f'),
            group=False
        )
        sim_config.add_connection(
            source=OspVariableEndpoint(simulator='chassis', name='p.e'),
            target=OspVariableEndpoint(simulator='wheel', name='p1.e'),
            group=False
        )

    Adding an initial value

        sim_config.add_update_initial_value(
            component_name='chassis',
            variable='I1.moment_initial',
            value=12
        )

    If xml file is already available, you can create the system from the file. Note that you should
    provice a path to the directory that contains all fmu files.

        sim_config = SimulationConfiguration(
            system_structure=PATH_TO_XML_FILE,
            path_to_fmy=PATH_TO_ALL_FMUS
        )
"""

import os
import shutil
import uuid
from enum import Enum
from sys import platform
from typing import NamedTuple, Union, List, Dict, Tuple, Type

import pandas
from pyOSPParser.logging_configuration import OspLoggingConfiguration, OspSimulatorForLogging
from pyOSPParser.model_description import OspModelDescription, OspVariableGroupsType, \
    OspTorqueType, OspGenericType, OspForceType, OspVoltageType, OspHydraulicPowerPortType, \
    OspPressureType, OspLinearVelocityType, OspAngularVelocityType, OspCurrentType, \
    OspVolumeFlowRateType, OspLinearDisplacementType, OspAngularDisplacementType, OspChargeType, \
    OspVolumeType, OspLinearMechanicalPortType, OspAngularMechanicalPortType, \
    OspElectromagneticPortType, OspHydraulicPortType, OspLinearMechanicalQuasiPortType, \
    OspAngularMechanicalQuasiPortType, OspElectromagneticQuasiPortType, OspHydraulicQuasiPortType, \
    OspLinearMechanicalPowerPortType, OspAngularMechanicalPowerPortType, \
    OspElectromagneticPowerPortType
from pyOSPParser.scenario import OSPScenario, OSPEvent
from pyOSPParser.system_configuration import OspSystemStructure, OspSimulator, OspVariableEndpoint,\
    OspVariableConnection, OspVariableGroupConnection, OspInitialValue, OspSignalEndpoint, \
    OspSignalConnection, OspSignalGroupConnection, FunctionType, OspLinearTransformationFunction, \
    OspSumFunction, OspVectorSumFunction, OspReal, OspInteger, OspString, OspBoolean

from .osp_command_line_interface import get_model_description, run_cosimulation, LoggingLevel, \
    run_single_fmu

COSIM_FILE_NAME = 'cosim' if platform.startswith("linux") else 'cosim.exe'

PATH_TO_COSIM = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'cosim', COSIM_FILE_NAME
)


def convert_value_to_osp_type(
        value: Union[float, int, bool, str],
        type_var: Union[Type[float], Type[int], Type[bool], Type[str]] = None
) -> Union[OspReal, OspInteger, OspString, OspBoolean]:
    """Convert a generic python variable type to OspVariable type used in the initial values

    Args:
        value: Value of the variable
        type_var(Optional): Specify a type of the variable if one wants to force or make sure
            that the type is defined as intended.
    """
    if type_var is not None:
        value = type_var(value)
    if isinstance(value, float):
        return OspReal(value=value)
    if isinstance(value, int):
        return OspInteger(value=value)
    if isinstance(value, str):
        return OspString(value=value)
    if isinstance(value, bool):
        return OspBoolean(value=value)


class SimulationConfigurationError(Exception):
    """Exception for simulation configuration error"""


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
            raise TypeError(f'The FMU file cannot be found. {self.fmu_file}')

    def get_fmu_information_from_file(self):
        """Adding the fmu information read from the model description file"""
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

    def get_endpoint_dict(self) -> Dict[str, List[Dict[str, str]]]:
        """Returns endpoint information as a dictionary with keys:
        'input', 'output', 'variable_group'"""
        return {
            'input': self.inputs,
            'output': self.outputs,
            'parameters': self.parameters,
            'others': self.other_variables,
            'variable_group': self.osp_model_description.to_dict().get('VariableGroups', None)
                              if self.osp_model_description is not None else None
        }

    def get_input_names(self) -> List[str]:
        """Returns input names as a list"""
        return [input['name'] for input in self.inputs]

    def get_output_names(self) -> List[str]:
        """Returns output names as a list"""
        return [output['name'] for output in self.outputs]

    def get_parameter_names(self) -> List[str]:
        """Returns parameter names as a list"""
        return [parameter['name'] for parameter in self.parameters]

    def get_other_variable_names(self) -> List[str]:
        """Returns other variable names as a list"""
        return [variable['name'] for variable in self.other_variables]

    def add_variable_group(self, var_group: Union[
                OspGenericType, OspForceType, OspTorqueType, OspVoltageType,
                OspPressureType, OspLinearVelocityType, OspAngularVelocityType, OspCurrentType,
                OspVolumeFlowRateType, OspLinearDisplacementType, OspAngularDisplacementType,
                OspChargeType, OspVolumeType, OspLinearMechanicalPortType,
                OspAngularMechanicalPortType, OspElectromagneticPortType,
                OspHydraulicPortType, OspLinearMechanicalQuasiPortType,
                OspAngularMechanicalQuasiPortType, OspElectromagneticQuasiPortType,
                OspHydraulicQuasiPortType, OspLinearMechanicalPowerPortType,
                OspAngularMechanicalPowerPortType, OspElectromagneticPowerPortType,
                OspHydraulicPowerPortType
    ]):
        """Adds a varuabke group for the OspModelDescription"""
        if self.osp_model_description is None:
            self.osp_model_description = OspModelDescription(
                VariableGroups=OspVariableGroupsType()
            )
            self.osp_model_description.add_interface(var_group)
        else:
            self.osp_model_description.add_interface(var_group)

    def delete_variable_groups(self, var_group_name: str) -> Union[
            OspGenericType, OspForceType, OspTorqueType, OspVoltageType,
            OspPressureType, OspLinearVelocityType, OspAngularVelocityType, OspCurrentType,
            OspVolumeFlowRateType, OspLinearDisplacementType, OspAngularDisplacementType,
            OspChargeType, OspVolumeType, OspLinearMechanicalPortType,
            OspAngularMechanicalPortType, OspElectromagneticPortType,
            OspHydraulicPortType, OspLinearMechanicalQuasiPortType,
            OspAngularMechanicalQuasiPortType, OspElectromagneticQuasiPortType,
            OspHydraulicQuasiPortType, OspLinearMechanicalPowerPortType,
            OspAngularMechanicalPowerPortType, OspElectromagneticPowerPortType,
            OspHydraulicPowerPortType
    ]:
        """Delete a variable group"""
        if self.osp_model_description is None:
            raise TypeError('OspModelDescription has not been defined yet.')
        if self.osp_model_description.VariableGroups is None:
            raise TypeError('There is no variable group to delete.')
        return self.osp_model_description.delete_interface(var_group_name)

    def get_variable_groups(self) -> List[Union[
            OspGenericType, OspForceType, OspTorqueType, OspVoltageType,
            OspPressureType, OspLinearVelocityType, OspAngularVelocityType, OspCurrentType,
            OspVolumeFlowRateType, OspLinearDisplacementType, OspAngularDisplacementType,
            OspChargeType, OspVolumeType, OspLinearMechanicalPortType,
            OspAngularMechanicalPortType, OspElectromagneticPortType,
            OspHydraulicPortType, OspLinearMechanicalQuasiPortType,
            OspAngularMechanicalQuasiPortType, OspElectromagneticQuasiPortType,
            OspHydraulicQuasiPortType, OspLinearMechanicalPowerPortType,
            OspAngularMechanicalPowerPortType, OspElectromagneticPowerPortType,
            OspHydraulicPowerPortType
    ]]:
        """Returns all the variable groups"""
        if self.osp_model_description is None:
            return []
        variable_groups = vars(self.osp_model_description.VariableGroups)
        if len(variable_groups) == 0:
            return []
        return [
            var_group for field, var_group_list in variable_groups.items()
            if var_group_list is not None for var_group in var_group_list
        ]

    def get_variable_group_names(self) -> List[str]:
        """Return a list of variable groups"""
        var_groups = self.get_variable_groups()
        return [var_group.name for var_group in var_groups]

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
    """Component used in SimulationConfiguration"""
    name: str
    fmu: FMU


class Causality(Enum):
    """Causality used for variable connection"""
    input = "input"
    output = "output"
    indefinite = "indefinite"


class InitialValues(NamedTuple):
    """InitialValue used in SimulationConfiguration"""
    component: str
    variable: str
    value: Union[float, int, bool, str]


class SimulationOutput(NamedTuple):
    """Return type of run_simulation"""
    result: Dict[str, pandas.DataFrame]
    log: str
    error: str
    output_file_path: str


class Function(NamedTuple):
    """Function used in SimulationConfiguration"""
    type: FunctionType
    name: str
    factor: float = None
    offset: float = None
    inputCount: int = None
    dimension: int = None


class SimulationConfiguration:
    """Class for running simulation"""
    components: List[Component]
    initial_values: List[InitialValues]
    functions: List[Function]
    system_structure: OspSystemStructure = None
    _scenario: OSPScenario = None
    _logging_config: OspLoggingConfiguration = None
    _current_sim_path: str = None

    # add_initial_value(comp_name: str, variable_name: str, value: float)
    # get_initial_values()
    # add_variable_interface(source: VariableInterface, target: VariableInterface)
    # get_variable_interfaces()

    def __init__(
            self,
            system_structure: Union[str, OspSystemStructure] = None,
            path_to_fmu: str = None,
            components: List[Component] = None,
            initial_values: List[InitialValues] = None,
            scenario: OSPScenario = None,
            logging_config: OspLoggingConfiguration = None,
    ):
        """Constructor for SimulationConfiguration class

        Args:
            system_structure(optional): A source for the system structure,
                either string content of the XML file or path to the file.
                Must be given together with the path_to_fmu argument..
            path_to_fmu(optional): A path to the FMUs for the given system structure.
            components(optional): Components for the system given as a list of Component instance
            initial_values(optional): Initial values for the simulation given as a
                list of InitialValues instance
            scenario(optional): A scenario for the simulation given as a OSPScenario instance
            logging_config(optional): A logging configuration for the output of the simulation
                given as a OSPScenario instance
        """
        if system_structure:
            assert path_to_fmu is not None, \
                "The path to fmu should be given together with the system structure"
            self.system_structure = OspSystemStructure(xml_source=system_structure)
            self.components = []
            self.initial_values = []
            self.functions = []
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
            self.system_structure = OspSystemStructure()
            self.components = []
            self.initial_values = []
            self.functions = []
            if components:
                for comp in components:
                    assert isinstance(comp, Component)
                self.components = components
            if initial_values:
                for init_value in initial_values:
                    assert isinstance(init_value, InitialValues)
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
        """scenario"""
        return self._scenario

    @scenario.setter
    def scenario(self, value):
        assert isinstance(value, OSPScenario)
        self._scenario = value

    @property
    def logging_config(self):
        """logging configuration"""
        return self._logging_config

    @logging_config.setter
    def logging_config(self, value):
        assert isinstance(value, OspLoggingConfiguration)
        self._logging_config = value

    @property
    def current_simulation_path(self):
        """get current simulation path"""
        return self._current_sim_path

    @staticmethod
    def prepare_temp_dir_for_simulation() -> str:
        """create a temporatry directory for the simulation"""
        base_dir_name = os.path.join('pycosim_tmp', f'sim_{uuid.uuid4().__str__()}')

        if platform.startswith('win'):
            path = os.path.join(os.environ.get('TEMP'), base_dir_name)
        else:
            path = os.path.join(
                os.environ.get('TMPDIR'),
                base_dir_name
            ) if os.environ.get('TMPDIR') else os.path.join('/var', 'tmp', base_dir_name)
        if not os.path.isdir(path):
            os.makedirs(path)
        return path

    @staticmethod
    def get_fmu_rel_path(path_to_deploy: str, path_to_sys_struct: str):
        """Get relative path of fmus from the system structure file"""
        if path_to_deploy.endswith(os.sep):
            path_to_deploy = path_to_deploy[:path_to_deploy.rfind(os.sep)]
        if path_to_sys_struct.endswith(os.sep):
            path_to_sys_struct = path_to_sys_struct[:path_to_sys_struct.rfind(os.sep)]
        if len(path_to_deploy) >= len(path_to_sys_struct):
            rel_path = path_to_deploy[len(path_to_sys_struct):].replace(os.sep, "/")[1:]
            if len(rel_path) > 0:
                return f'{rel_path}/'
            return ''

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
            # Deploy OspDescriptionFiles if there is
            if fmu.osp_model_description is not None:
                destination_file = os.path.join(
                    path_to_deploy,
                    f'{fmu.name}_OspModelDescription.xml'
                )
                with open(destination_file, 'wt') as osp_model_file:
                    osp_model_file.write(fmu.osp_model_description.to_xml_str())

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
        """Runs a simulation"""
        path = self.prepare_temp_dir_for_simulation()
        path_to_sys_struct = self.deploy_files_for_simulation(
            path_to_deploy=path,
            rel_path_to_system_structure=rel_path_to_sys_struct,
        )
        result, log, error = run_cosimulation(
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
            error=error,
            output_file_path=path_to_sys_struct
        )

    def get_component_names(self) -> List[str]:
        """Get component names"""
        return [component.name for component in self.components]

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
            stepSize(optional): Step size for the simulator in seconds. If not given, its default
            value is used.
            rel_path_to_fmu(optional): Relative path to fmu from a system structure file.
        Return:
            Component: the created component.
        """
        # Add component only in case the name is unique.
        if name not in self.get_component_names():
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

        raise TypeError('The name duplicates with the existing components.')

    def delete_component(self, component_name: str) -> bool:
        """Delete a component in the system"""
        if component_name not in self.get_component_names():
            raise TypeError('No component is found with ')
        # Delete from its attributes
        component = self.get_component_by_name(component_name)
        self.components.pop(self.components.index(component))

        # Delete from the system structure attribute
        self.system_structure.delete_simulator(component_name)

        return True

    def validate_variable_endpoint(
            self,
            endpoint: OspVariableEndpoint,
            causality: Causality
    ) -> bool:
        """Validate endpoint if it has a correct component and variable name"""
        # Check if the component and variable for its causality exists
        try:
            fmu = next(
                component.fmu for component in self.components
                if component.name == endpoint.simulator
            )
            variable_names = fmu.get_input_names() if causality == Causality.input \
                else fmu.get_output_names()
            if endpoint.name not in variable_names:
                raise TypeError(f'The input variable does not match the names of '
                                f'inputs of the component: {variable_names}')
        except StopIteration:
            raise TypeError('The component name given in the input does not match '
                            f'the names of components in the system: {self.get_component_names()}.')

        # Check if there is any other input of the same name in case of input causality
        if causality == Causality.input:
            target_endpoints = self.get_variable_endpoints_of_component_for_variable_connection(
                component_name=endpoint.simulator,
                causality=Causality.input
            )
            if endpoint.name in [ep.name for ep in target_endpoints]:
                raise TypeError('An endpoint already exists for this target.')

        return True

    def get_variable_endpoints_of_component_for_variable_connection(
            self,
            component_name: str,
            causality: Causality = None
    ) -> List[OspVariableEndpoint]:
        """Returns variable endpoints used for variable connections

        Args:
            component_name
            causality(Optional): Indicates if the endpoints are input or output.
        """
        try:
            endpoints = self.system_structure.get_all_endpoints_for_component(component_name)
        except TypeError:
            return []
        if causality == Causality.input:
            target_endpoint = []
            for endpoint in endpoints:
                component = self.get_component_by_name(endpoint.simulator)
                if endpoint.name in component.fmu.get_input_names():
                    target_endpoint.append(endpoint)
            return target_endpoint
        if causality == Causality.output:
            source_endpoint = []
            for endpoint in endpoints:
                component = self.get_component_by_name(endpoint.simulator)
                if endpoint.name in component.fmu.get_output_names():
                    source_endpoint.append(endpoint)
            return source_endpoint
        return endpoints

    def validate_variable_group_endpoint(
            self,
            endpoint: OspVariableEndpoint,
            causality: Causality
    ) -> bool:
        """Validate endpoint if it has a correct component and variable group name"""
        # todo implement this code
        # try:
        #     fmu = next(
        #         component.fmu for component in self.components
        #         if component.name == endpoint.simulator
        #     )
        #     names = fmu.get_variable_group_names() if causality == Causality.input \
        #         else fmu.get_output_names()
        #     if endpoint.name not in names:
        #         raise TypeError(f'The input variable does not match the names of '
        #                         f'inputs of the component: {names}')
        # except StopIteration:
        #     raise TypeError('The component name given in the input does not match '
        #                     'the names of components in the system: '
        #                     f'{self.get_component_names()}.')
        # return True

        raise NotImplementedError('This method is not implemented yet.')

    def add_connection(
            self,
            source: Union[OspVariableEndpoint, OspSignalEndpoint],
            target: Union[OspVariableEndpoint, OspSignalEndpoint],
            group: bool
    ) -> Union[
        OspVariableConnection,
        OspSignalConnection,
        OspVariableGroupConnection,
        OspSignalGroupConnection
    ]:
        """Add a connection to the system for variable input/output

        type of connection       | source             | target              | group
        variable connection      | OspVariableEndpoint | OspVariableEndpoint | False
        variable group connection| OspVariableEndpoint | OspVariableEndpoint | True
        singal connection        | OspVariableEndpoint | OspSignalEndpoint   | False
        signal connection        | OspSingalEndpoint   | OspVariableEndpoint | False
        singal group connection  | OspVariableEndpoint | OspSignalEndpoint   | True
        signal group connection  | OspSingalEndpoint   | OspVariableEndpoint | True
        """
        # Check if the input has a correct component name and variable name
        if isinstance(source, OspVariableEndpoint) and not group:
            self.validate_variable_endpoint(source, Causality.output)
        if isinstance(target, OspVariableEndpoint) and not group:
            self.validate_variable_endpoint(target, Causality.input)
        connection = self.system_structure.add_connection(source=source, target=target, group=group)
        return connection

    def delete_connection(
            self,
            endpoint1: OspVariableEndpoint,
            endpoint2: OspVariableEndpoint
    ):
        """Deletes a connection having the given endpoints"""
        return self.system_structure.delete_connection(
            endpoint1=endpoint1,
            endpoint2=endpoint2
        )

    def add_update_initial_value(
            self,
            component_name: str,
            variable: str,
            value: Union[float, int, bool, str],
            type_value: Union[Type[float], Type[int], Type[bool], Type[str]] = None
    ) -> InitialValues:
        """Add or update initial value. Returns True if successful

        Args:
            component_name: Name of the component
            variable: Name of the variable
            value: Value
            type_value(optional): type of the value if one wants to make sure to have a
                correct type for the value
        """

        # Check if the initial value is valid
        component = self.get_component_by_name(component_name)
        if variable not in component.fmu.get_parameter_names() and \
                variable not in component.fmu.get_input_names():
            raise TypeError(
                f'No variable is found in the inputs / parameters of '
                f'the model with the name {variable}. You cannot set '
                f'initial value for outputs.'
            )

        # Search for an initial value that already exists. Otherwise, create a new instance
        try:
            init_value = self.get_initial_value_by_variable(component_name, variable)
            self.initial_values.pop(self.initial_values.index(init_value))
            init_value = InitialValues(
                component=component_name,
                variable=variable,
                value=value
            )
        except TypeError:
            init_value = InitialValues(
                component=component_name,
                variable=variable,
                value=value
            )

        self.initial_values.append(init_value)
        value_osp_type = convert_value_to_osp_type(value=value, type_var=type_value)
        self.system_structure.add_update_initial_value(
            component_name=component_name,
            init_value=OspInitialValue(variable=variable, value=value_osp_type)
        )

        return init_value

    def delete_initial_value(self, component: str, variable: str):
        """Deletes the initial value. Returns True if successful."""
        init_value = self.get_initial_value_by_variable(
            component=component,
            variable=variable
        )
        init_value = self.initial_values.pop(self.initial_values.index(init_value))
        if self.system_structure.delete_initial_value(component_name=component, variable=variable):
            return True

        self.initial_values.append(init_value)
        raise TypeError('The initial value could not be added.')

    def get_component_by_name(self, name) -> Component:
        """Returns a Component instnace from its attributes"""
        try:
            return next(component for component in self.components if component.name == name)
        except StopIteration:
            raise TypeError(f'No component is found with the given name: {name}')

    def get_initial_value_by_variable(self, component: str, variable: str) -> InitialValues:
        """Returns an InitialValues instance from its attributes"""
        try:
            return next(
                init_value for init_value in self.initial_values
                if init_value.component == component and init_value.variable == variable
            )
        except StopIteration:
            raise TypeError(f'No initial value is found with the given variable: {variable}')

    def add_function(self, function_name: str, function_type: FunctionType, **kwargs) \
            -> Union[OspLinearTransformationFunction, OspSumFunction, OspVectorSumFunction]:
        """Add a function

        'factor', 'offset' arguments are required for FunctionType.LinearTransformation
        'inputCount' is required for FunctionType.Sum
        'inputCount', 'dimension' are required for FunctionType.VectorSumFunction

        Args:
            function_name: Name of the function
            function_type: Either of FunctionType.LinearTransformation, FunctionType.Sum or
                FunctionType.VectorSum
            factor (float): factor for linear transformation f(x) = factor * x + offset
            offset (float): offset for linear transformation f(x) = factor * x + offset
            inputCount (int): number of inputs for sum or vector sum
            dimension (int): Dimension of a vector for vector sum

        Returns:
            OspLinearTransformationFunction, OspSumFunction, OspVectorSumFunction

        Exceptions:
            TypeError if correct arguments are not given for a function type
        """
        if function_type == FunctionType.LinearTransformation:
            factor = kwargs.get('factor', None)
            if factor is None:
                raise TypeError('"factor" argument should be provided for a linear '
                                'transformation function')
            offset = kwargs.get('offset', None)
            if offset is None:
                raise TypeError('"offset" argument should be provided for a linear '
                                'transformation function')
            self.functions.append(Function(
                name=function_name, type=function_type, factor=factor, offset=offset
            ))
            return self.system_structure.add_function(
                function_name=function_name,
                function_type=function_type,
                factor=factor,
                offset=offset
            )

        if function_type == FunctionType.Sum:
            inputCount = kwargs.get('inputCount', None)
            if inputCount is None:
                raise TypeError('"inputCount" argument should be provided for a sum function')
            self.functions.append(Function(
                name=function_name, type=function_type, inputCount=inputCount
            ))
            return self.system_structure.add_function(
                function_name=function_name, function_type=function_type, inputCount=inputCount
            )

        if function_type == FunctionType.VectorSum:
            inputCount = kwargs.get('inputCount', None)
            if inputCount is None:
                raise TypeError('"inputCount" argument should be provided for a sum function')
            dimension = kwargs.get('dimension', None)
            if dimension is None:
                raise TypeError('"dimension" argument should be provided for a sum function')
            self.functions.append(Function(
                name=function_name, type=function_type, inputCount=inputCount, dimension=dimension
            ))
            return self.system_structure.add_function(
                function_name=function_name,
                function_type=function_type,
                inputCount=inputCount,
                dimension=dimension
            )

    def add_logging_variable(
            self, component_name: str,
            variable_name: str,
            decimation_factor: int = 1
    ):
        """Add a variable to log during a simulation

        Args:
            component_name: Name of the simulator
            variable_name: Name of the variable
            decimation_factor: Sampling rate of the
                simulation results. For example, decimationFactor=1 means the
                results of every simulation step of the simulator are logged.
                And decimationFactor=10 means every 10th of the simulation
                results are logged.
        """
        # Check if the component name is found in the system
        if component_name not in self.get_component_names():
            raise TypeError('No component is found with the name. '
                            f'It should be either of {self.get_component_names()}')
        # Check if the variable is found in the model
        comp = self.get_component_by_name(component_name)
        if variable_name not in [
                *(comp.fmu.get_input_names()),
                *(comp.fmu.get_output_names()),
                *(comp.fmu.get_parameter_names()),
                *(comp.fmu.get_other_variable_names())
        ]:
            raise TypeError('No variable or parameter is found with the name.')
        if self.logging_config is None:
            self.logging_config = OspLoggingConfiguration()
        try:
            if self.logging_config.simulators is None:
                self.logging_config.simulators = []
            logging_for_component: OspSimulatorForLogging = next(
                logging_component for logging_component in self.logging_config.simulators
                if logging_component.name == component_name
            )
            logging_for_component.add_variable(variable_name)
        except StopIteration:
            self.logging_config.simulators.append(OspSimulatorForLogging(
                name=component_name,
                decimation_factor=decimation_factor
            ))
            logging_for_component = next(
                logging_component for logging_component in self.logging_config.simulators
                if logging_component.name == component_name
            )
            logging_for_component.add_variable(variable_name)
        return True

    def set_decimation_factor(self, component_name: str, decimation_factor: int) -> bool:
        """Set decimal factor for a component logging"""
        return self.logging_config.set_decimation_factor(component_name, decimation_factor)

    def set_scenario(self, name: str, end: float, description: str = None):
        """Sets a scenario"""
        self.scenario = OSPScenario(name=name, end=end, description=description)

    def set_scenario_from_json(self, source: str):
        """Sets a scenario from the json

        Args:
            source: json string or path to the file
        """
        if os.path.isfile(source):
            with open(source, 'rt') as file:
                source = file.read()
        self.scenario = OSPScenario(name='', end=0)
        self.scenario.from_json(source)

    def add_event(self, time: float, component: str, variable: str, action: int, value: float):
        """Add an event

        Args:
            time: Time when the event is triggered
            component: Name of the component for the event to apply
            variable: Name of the variable for the event to apply
            action: Type of action. Recommended to use OSPEvent.OVERRIDE,
                OSPEvent.BIAS, OSPEvent.RESET
            value: Value for the change
        """
        if not isinstance(self.scenario, OSPScenario):
            raise TypeError('No scenario has been set up. Use set_scenario or '
                            'se_scenario_from_json to set up a scenario')
        if component not in self.get_component_names():
            raise TypeError(f'No component is found with the name {component}')
        fmu = self.get_component_by_name(component).fmu
        if variable not in [*(fmu.get_input_names()), *(fmu.get_parameter_names())]:
            raise TypeError(f'No input or parameter is found with the name {variable}')
        return self.scenario.add_event(OSPEvent(
            time=time,
            model=component,
            variable=variable,
            action=action,
            value=value
        ))

    def update_event(
            self,
            time: float,
            component: str,
            variable: str,
            action: int = None,
            value: float = None
    ):
        """Update an event

        One should provide time, model(component name) and variable to find the event to update.
        One can provide either action or value or both.
        """
        if not isinstance(self.scenario, OSPScenario):
            raise TypeError('No scenario has been set up. Use set_scenario or '
                            'se_scenario_from_json to set up a scenario')
        return self.scenario.update_event(
            time=time, component=component, variable=variable, action=action, value=value
        )

    def delete_events(self, time: float = None, component: str = None, variable: str = None):
        """Delete events

         If no argument is provided, it deletes all events. Givent the arguments, events
         that match the argument values are found and deleted.
         """
        if not isinstance(self.scenario, OSPScenario):
            raise TypeError('No scenario has been set up. Use set_scenario or '
                            'se_scenario_from_json to set up a scenario')
        return self.scenario.delete_events(time=time, component=component, variable=variable)

    def set_base_step_size(self, step_size: float) -> float:
        """Sets a base step size for master algorithm in co-simulation.

        Returns the step size set.
        """
        self.system_structure.BaseStepSize = float(step_size)
        return float(step_size)
