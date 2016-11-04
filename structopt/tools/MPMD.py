import logging, os
import subprocess
import math
import time
from collections import defaultdict

import structopt
from structopt.tools.parallel import root, single_core, parallel, parse_MPMD_cores_per_structure


@root
def fitness(population, parameters):
    """Perform the FEMSIM fitness calculation on an entire population.

    Args:
        population (Population): the population to evaluate
    """
    from mpi4py import MPI

    to_fit = [individual for individual in population if not individual._fitted]

    if to_fit:
        spawn_args = [individual.fitnesses.FEMSIM.get_spawn_args(individual) for individual in to_fit]
        MPMD(to_fit, spawn_args)

        # Collect the results for each chisq and return them
        logger = logging.getLogger('output')
        for i, individual in enumerate(to_fit):
            while True:
                vk = individual.fitnesses.FEMSIM.get_vk_data()
                if len(vk) != 0:
                    break
            individual.FEMSIM = individual.fitnesses.FEMSIM.chi2(vk)
            logger.info('Individual {0} for FEMSIM evaluation had chisq {1}'.format(i, individual.FEMSIM))

    return [individual.FEMSIM for individual in population]


@root(broadcast=False)
def MPMD(self, to_run, spawn_args):
    """This is a function to run MPMD, with an example for FEMSIM above.
    I'm not confident we should use it yet, but only because I haven't tested it.
    I'm relatively confident it will work.
    """
    ncores = parameters.ncores
    cores_per_individual = ncores // len(to_run)
    # Round cores_per_individual down to nearest power of 2
    if cores_per_individual == 0:
        # We have more individuals than cores, so each fitness scheme needs to be run multiple times
        cores_per_individual = 1

    pow(2.0, math.floor(math.log2(cores_per_individual)))
    minmax = parse_MPMD_cores_per_structure(parameters.MPMD)
    assert minmax['max'] >= minmax['min'] > 0
    if cores_per_individual < minmax['min']:
        cores_per_individual = minmax['min']
    elif cores_per_individual > minmax['max']:
        cores_per_individual = minmax['max']

    # Setup each individual and get the inputs for each individual that need to be passed into the spawn
    multiple_spawn_args = defaultdict(list)
    for individual in to_run:
        for arg_name, arg in spawn_args.items():
            multiple_spawn_args[arg_name].append(arg)

    # Make sure each key in `multiple_spawn_args` has the same number of elements and set `count` to that value
    count = -1
    for key, value in multiple_spawn_args.items():
        if count != -1:
            assert len(value) == count
        count = len(value)

    # Create MPI.Info objects from the kwargs dicts in multiple_spawn_args['info'] for each rank
    infos = [MPI.Info.Create() for _ in multiple_spawn_args['info']]
    for i, info in enumerate(infos):
        for key, value in multiple_spawn_args['info'][i].items():
            info.Set(key, value)

    # Run the multiple spawn
    individuals_per_iteration = ncores // cores_per_individual
    individuals_per_iteration = min(individuals_per_iteration, len(to_run))
    num_iterations = math.ceil(len(to_run) / individuals_per_iteration)
    for i in range(num_iterations):
        j = i * individuals_per_iteration
        print("Spawning {} processes, each with {} cores".format(individuals_per_iteration, cores_per_individual))
        intercomm = MPI.COMM_SELF.Spawn_multiple(command=multiple_spawn_args['command'][j:j+individuals_per_iteration],
                                     args=multiple_spawn_args['args'][j:j+individuals_per_iteration],
                                     maxprocs=[cores_per_individual]*individuals_per_iteration,
                                     info=infos[j:j+individuals_per_iteration]
                                     )
        # Disconnect the child processes
        intercomm.Disconnect()

