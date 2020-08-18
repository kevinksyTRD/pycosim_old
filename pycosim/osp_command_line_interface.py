""" Handles FMU and runs co-simulations using cosim-cli

The module contains different functions for handling FMU or running co-simulations using cosim-cli
(https://github.com/open-simulation-platform/cosim-cli)

...
Attributes:
    PATH_TO_COSIM(str)

Functions:
    get_model_description():

Classes:
    ModelVariables(NamedTuple): Representation of model variables
"""
import datetime as dt
import io
import logging
import os
from enum import Enum
from subprocess import Popen, PIPE
from sys import platform
from typing import NamedTuple, List, Dict, Union, Tuple

import pandas
import yaml

from pyOSPParser.scenario import OSPScenario
from pyOSPParser.logging_configuration import OspLoggingConfiguration

COSIM_FILE_NAME = 'cosim' if platform.startswith("linux") else 'cosim.exe'

PATH_TO_COSIM = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'cosim', COSIM_FILE_NAME
)


class SimulationError(Exception):
    pass


class ModelVariables(NamedTuple):
    """ Representation of model variables from FMU's model description

    Attributes:
        parameters (List[Dict[str,str]], optional)
        inputs (List[Dict[str,str]], optional)
        outputs (List[Dict[str,str]], optional)
        others (List[Dict[str,str]], optional)
    """
    parameters: List[Dict[str, str]] = []
    inputs: List[Dict[str, str]] = []
    outputs: List[Dict[str, str]] = []
    others: List[Dict[str, str]] = []

    def get_parameters_names(self) -> List:
        """ Returns a list of the parameter names """
        return [variable['name'] for variable in self.parameters]

    def get_input_names(self) -> List:
        """ Returns a list of the parameter names """
        return [variable['name'] for variable in self.inputs]

    def get_output_names(self) -> List:
        """ Returns a list of the output names """
        return [variable['name'] for variable in self.outputs]

    def get_other_variable_names(self) -> List:
        """ Returns a list of the parameter names """
        return [variable['name'] for variable in self.others]


class FMUModelDescription(NamedTuple):
    """ Model description summary

    Model description summary used as a return type for get_model_description

    Attributes:
        name(str)
        uuid(str)
        model_variable (ModelVariables)
        description (str, optional)
        author (str, optional)
        version (str, optional)
    """
    name: str
    uuid: str
    model_variable: ModelVariables
    description: str = ''
    author: str = ''
    version: str = ''


class LoggingLevel(Enum):
    error = 40
    warning = 30
    info = 20
    debug = 10


def parse_model_variables(variables: List[Dict[str, str]]) -> ModelVariables:
    """Parse the variables according to its category

    Args:
        variables (List[Dict[str, str]]): The variable from cosim-cli inspect
    
    Returns:
        ModelVariables: Variables sorted into parameter, input, output, others
    """
    parameters = []
    inputs = []
    outputs = []
    others = []
    for variable in variables:
        if variable['variability'] == 'fixed' or variable['causality'] == 'parameter':
            parameters.append(variable)
        elif variable['causality'] == 'input':
            inputs.append(variable)
        elif variable['causality'] == 'output':
            outputs.append(variable)
        else:
            others.append(variable)
    return ModelVariables(
        parameters=parameters,
        inputs=inputs,
        outputs=outputs,
        others=others
    )


def get_model_description(file_path_fmu: str) -> FMUModelDescription:
    """
    Returns the model description including variables_sorted.
    the parameters, inputs, outputs and other internal variables from the model
    description file of the fmu using the cosim-cli.

    Args:
        file_path_fmu (str): Absolute file path of the FMU file.

    Returns:
        FMUModelDescription: NamedTuple that contains model description
    """
    mode = 'inspect'

    assert os.path.isfile(PATH_TO_COSIM), 'The cosim CLI is not found: %s' % PATH_TO_COSIM
    assert os.path.isfile(file_path_fmu), 'The fmu file is not found: %s' % file_path_fmu

    #: Run the cosim to get the result in yaml format
    result = ''
    error = ''
    try:
        with Popen(args=[PATH_TO_COSIM, mode, file_path_fmu], shell=True, stdout=PIPE, stderr=PIPE) as proc:
            result = proc.stdout.read()
            error = proc.stderr.read()
    except OSError as e:
        raise OSError('%s, %s, %s', (result, error, e))

    #: Parse yaml to dictionary
    result = yaml.BaseLoader(result).get_data()

    return FMUModelDescription(
        name=result['name'],
        uuid=result['uuid'],
        model_variable=parse_model_variables(result['variables']),
        description=result['description'],
        author=result['author'],
        version=result['version'],
    )


def run_cli(args):
    try:
        with Popen(args=args, shell=True, stdout=PIPE, stderr=PIPE) as proc:
            log = proc.stdout.read()
            error = proc.stderr.read()
    except OSError as e:
        raise OSError('%s, %s, %s', (log, error, e))

    # Catch errors

    return log, error.decode('utf-8')


def run_single_fmu(
        path_to_fmu: str,
        initial_values: Dict[str, Union[float, bool]] = None,
        output_file_path: str = None,
        duration: float = None,
        step_size: float = None,
) -> Tuple[pandas.DataFrame, str]:
    """Runs a single fmu simulation

    Args:
        path_to_fmu(str): file path to the target fmu
        initial_values(Dict[str, Union[float, bool]], optional): dictionary of initial values
        output_file_path(str, optional): file path for the output
        duration(float, optional): duration of simulation in seconds
        step_size(float, optional): duration
    Return:
        (tuple): tuple containing:
            result(pandas.DataFrame) simulation result
            log(str) simulation logging
    """
    delete_output = False
    if initial_values is None:
        initial_values = {}
    if output_file_path is None:
        # Delete output if the output file path is not given
        output_file_path = 'model-output.csv'
        delete_output = True
    mode = "run-single"

    assert os.path.isfile(PATH_TO_COSIM), 'The cosim CLI is not found: %s' % PATH_TO_COSIM
    assert os.path.isfile(path_to_fmu), 'The fmu file is not found: %s' % path_to_fmu

    # Create a list of initial values and set arguments for simulation
    args = [PATH_TO_COSIM, mode, path_to_fmu]
    args.extend('%s=%s' % (key, value) for key, value in initial_values.items())
    args.append('--output-file=%s' % output_file_path)
    if duration:
        args.append('-d%f' % duration)
    if step_size:
        args.append('-s%f' % step_size)

    #: Run the cosim to get the result in yaml format
    log, error = run_cli(args)

    # Parse the output
    result = pandas.read_csv(output_file_path)
    if delete_output:
        os.remove(output_file_path)

    return result, log.decode('utf-8')


def deploy_output_config(output_config: OspLoggingConfiguration, path: str):
    file_path = os.path.join(path, 'LogConfig.xml')

    xml_text = output_config.to_xml_str()

    with open(file_path, 'w+') as file:
        file.write(xml_text)


def deploy_scenario(scenario: OSPScenario, path: str):
    file_path = os.path.join(path, scenario.get_file_name())

    with open(file_path, 'w+') as file:
        file.write(scenario.to_json())

    return file_path


def clean_header(header: str):
    if '[' in header:
        return header[0:header.rindex('[')-1]
    else:
        return header


def run_cosimulation(
        path_to_system_structure: str,
        # initial_values=None,
        logging_config: OspLoggingConfiguration = None,
        output_file_path: str = None,
        scenario: OSPScenario = None,
        duration: float = None,
        logging_level: LoggingLevel = LoggingLevel.warning,
        logging_stream: bool = False
) -> Tuple[Dict[str, pandas.DataFrame], str]:
    """Runs a co-simulation

    Args:
        path_to_system_structure(str): The path to the system structure definition file/directory.
              If this is a file with .xml extension, or a directory that contains a file named
              OspSystemStructure.xml, it will be interpreted as a OSP system structure
              definition.
        logging_config(Dict[str, str], optional): dictionary of output configuration
        output_file_path(str, optional): file path for the output
        scenario(Dict[str, str], optional), dictionary of scenario
        duration(float, optional): duration of simulation in seconds
        logging_level(LoggingLevel, optional): Sets the detail/severity level of diagnostic output.
            Valid arguments are 'error', 'warning', 'info', and 'debug'. Default is 'warning'.
        logging_stream(bool, optional): logging will be returned as a string if True value is given.
            Otherwise, logging will be only displayed.
    Return:
        (tuple): tuple containing:
            result(Dict[str, pandas.DataFrame]) simulation result
            log(str) simulation logging
    """
    # Set loggers
    logger = logging.getLogger()
    if logging_stream:
        log_stream = io.StringIO()
        log_handler = logging.StreamHandler(log_stream)
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
    logger.setLevel(logging_level.value)

    # Set simulation parameters
    delete_output = False
    mode = "run"

    # Check if the cosim-cli exists and the system structure exists
    assert os.path.isfile(PATH_TO_COSIM), 'The cosim CLI is not found: %s' % PATH_TO_COSIM
    assert os.path.isdir(path_to_system_structure), \
        'The system structure directory is not found: %s' % path_to_system_structure
    path_to_osp_sys_structure = os.path.join(path_to_system_structure, 'OspSystemStructure.xml')
    assert os.path.isfile(path_to_osp_sys_structure), \
        'The system structure directory is not found: %s' % path_to_system_structure
    args = [PATH_TO_COSIM, mode, path_to_system_structure]

    if logging_config is not None:
        logger.info('Deploying the logging configuration.')
        deploy_output_config(logging_config, path_to_system_structure)
    if output_file_path is None:
        output_file_path = path_to_system_structure
        delete_output = True
    else:
        assert os.path.isdir(output_file_path), \
            "The directory for the output doesn't exist: %s." % output_file_path
        logger.info('Output csv files will be saved in the following directory: %s.' % output_file_path)
    args.append('--output-dir=%s' % output_file_path)
    if scenario is not None:
        logger.info('Deploying the scenario.')
        scenario_file_path = deploy_scenario(scenario, path_to_system_structure)
        args.append('--scenario=%s' % scenario_file_path)
    if duration:
        logger.info('Simulation will run until %f seconds.' % duration)
        args.append('--duration=%s' % duration)
    args.append('--log-level=%s' % logging_level.name)

    # Run simulation
    logger.info('Running simulation.')
    log, error = run_cli(args)
    logger.info(error)

    # construct result from csvs that are created within last 30 seconds
    output_files = [file_name for file_name in os.listdir(output_file_path) if file_name.endswith('csv')]
    ago = dt.datetime.now() - dt.timedelta(seconds=30)
    output_files = [
        file_name for file_name in output_files
        if dt.datetime.fromtimestamp(os.stat(os.path.join(output_file_path, file_name)).st_mtime) > ago
    ]
    result = {}
    for file in output_files:
        simulator_name = file
        for _ in range(3):
            simulator_name = simulator_name[:simulator_name.rfind('_')]
        result[simulator_name] = pandas.read_csv(os.path.join(output_file_path, file))
        new_column_name = list(map(clean_header, result[simulator_name].columns))
        result[simulator_name].columns = new_column_name
    if delete_output:
        for file_name in output_files:
            os.remove(os.path.join(output_file_path, file_name))

    # Get logging data
    if logging_stream:
        # noinspection PyUnboundLocalVariable
        logger.removeHandler(log_handler)
        log_handler.flush()
        # noinspection PyUnboundLocalVariable
        log_stream.flush()
        log = log_stream.getvalue()
    else:
        log = ''

    return result, log
