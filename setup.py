from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='pyCoSim',
    version='0.1.1',
    description='Python library running co-simulation using cosim-cli from Open Simulation Platform',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/kevinTRD/pycosim",
    author='Kevin Koosup Yum',
    author_email='kevinkoosup.yum@sintef.no',
    license="Apache License 2.0",
    classifiers=[
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
    ],
    packages=['pycosim'],
    install_requires=[
      'pyyaml',
      'pyOSPParser',
      'pandas',
      'numpy',
      'xmlschema'
    ],
    include_package_data=True,
    zip_safe=False
)
