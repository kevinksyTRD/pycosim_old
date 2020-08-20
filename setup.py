from setuptools import setup

setup(
    name='pyCoSim',
    version='0.1.0',
    description='Python library running co-simulation using cosim-cli from Open Simulation Platform',
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
      'pyOSPParse',
      'pandas',
      'numpy',
      'xmlschema'
    ],
    include_package_data=True,
    zip_safe=False
)
