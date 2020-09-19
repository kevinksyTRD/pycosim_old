import json
import os
import random
import string

from pyOSPParser.model_description import OspModelDescription, OspVariableGroupsType, \
    OspLinearMechanicalPortType, OspForceType, OspLinearVelocityType, OspVariableType

from pycosim.simulation import FMU

PATH_TO_FMU = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fmus', 'chassis.fmu')
PATH_TO_FMU_DIR = os.path.dirname(PATH_TO_FMU)


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
    assert endpoints.get('variable_group') == \
           fmu.osp_model_description.to_dict().get('VariableGroups')

    # Test running a single FMU simulation
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


def test_add_variable_group():
    fmu = FMU(PATH_TO_FMU)
    fmu.osp_model_description = OspModelDescription(
        VariableGroups=OspVariableGroupsType()
    )
    var_group = OspLinearMechanicalPortType(
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
    fmu.add_variable_group(var_group)
    assert len(fmu.get_variable_groups()) == 1

    var_group_deleted = fmu.delete_variable_groups(var_group.name)
    assert var_group.to_dict_xml() == var_group_deleted.to_dict_xml()
    assert fmu.osp_model_description.VariableGroups.LinearMechanicalPort is None
    assert len(fmu.get_variable_groups()) == 0


