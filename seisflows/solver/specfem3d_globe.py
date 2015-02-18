
import subprocess
from glob import glob
from os.path import join

import numpy as np

import seisflows.seistools.specfem3d_globe as solvertools
from seisflows.seistools.io import savebin
from seisflows.seistools.shared import getpar, setpar

from seisflows.tools import unix
from seisflows.tools.array import loadnpy, savenpy
from seisflows.tools.code import exists
from seisflows.tools.config import loadclass, ParameterObj

PAR = ParameterObj('SeisflowsParameters')
PATH = ParameterObj('SeisflowsPaths')


class specfem3d_globe(loadclass('solver', 'base')):
    """ Python interface for SPECFEM3D_GLOBE

      See base class for method descriptions
    """

    if 0:
        # use isotropic model
        parameters = []
        parameters += ['reg1_rho']
        parameters += ['reg1_vp']
        parameters += ['reg1_vs']

    else:
        # use transversely isotropic model
        parameters = []
        parameters += ['reg1_rho']
        parameters += ['reg1_vpv']
        parameters += ['reg1_vph']
        parameters += ['reg1_vsv']
        parameters += ['reg1_vsh']
        parameters += ['reg1_eta']


    def check(self):
        """ Checks parameters and paths
        """
        super(specfem3d_globe, self).check()


    def generate_data(self, **model_kwargs):
        """ Generates data
        """
        self.generate_mesh(**model_kwargs)

        unix.cd(self.getpath)
        setpar('SIMULATION_TYPE', '1')
        setpar('SAVE_FORWARD', '.true.')
        self.mpirun('bin/xspecfem3D')

        unix.mv(self.data_wildcard, 'traces/obs')
        self.export_traces(PATH.OUTPUT, 'traces/obs')


    def generate_mesh(self, model_path=None, model_name=None, model_type='gll'):
        """ Performs meshing and database generation
        """
        assert(model_name)
        assert(model_type)

        self.initialize_solver_directories()
        unix.cd(self.getpath)

        if model_type == 'gll':
            assert (exists(model_path))
            unix.cp(glob(model_path +'/'+ '*'), self.model_databases)
            self.mpirun('bin/xmeshfem3D')
            self.export_model(PATH.OUTPUT +'/'+ model_name)

        else:
            raise NotImplementedError


    ### model input/output

    def save(self, path, model):
        """ writes SPECFEM3D_GLOBE transerverly isotropic model
        """
        unix.mkdir(path)

        for iproc in range(PAR.NPROC):
            for key in ['reg1_vpv', 'reg1_vph', 'reg1_vsv', 'reg1_vsh', 'reg1_eta']:
                if key in self.parameters:
                    savebin(model[key][iproc], path, iproc, key)
                else:
                    self.copybin(path, iproc, key)

            if 'reg1_rho' in self.parameters:
                savebin(model['reg1_rho'][iproc], path, iproc, 'reg1_rho')
            elif self.density_scaling:
                raise NotImplementedError
            else:
                self.copybin(path, iproc, 'reg1_rho')


    ### low-level solver interface

    def forward(self):
        """ Calls SPECFEM3D_GLOBE forward solver
        """
        solvertools.setpar('SIMULATION_TYPE', '1')
        solvertools.setpar('SAVE_FORWARD', '.true.')
        self.mpirun('bin/xspecfem3D')
        unix.mv(self.data_wildcard, 'traces/syn')


    def adjoint(self):
        """ Calls SPECFEM3D_GLOBE adjoint solver
        """
        solvertools.setpar('SIMULATION_TYPE', '3')
        solvertools.setpar('SAVE_FORWARD', '.false.')
        unix.rm('SEM')
        unix.ln('traces/adj', 'SEM')
        self.mpirun('bin/xspecfem3D')


    ### postprocessing utilities

    def combine(self, path=''):
        """ Sums individual source contributions. Wrapper over xsum_kernels 
            utility.
        """
        unix.cd(self.getpath)

        with open('kernel_paths', 'w') as f:
            f.writelines([join(path, dir)+'\n' for dir in unix.ls(path)])

        unix.mkdir(path +'/'+ 'sum')
        for name in self.parameters:
            _, name = name.split('_')
            self.mpirun(PATH.SPECFEM_BIN +'/'+ 'xsum_kernels '
                        + 'kernel_paths' + ' '
                        + path +'/'+ 'sum' + ' '
                        + name + '_kernel')


    def smooth(self, path='', tag='gradient', span=0.):
        """ smooths SPECFEM3D_GLOBE kernels
        """
        unix.cd(self.getpath)

        # smooth kernels
        for name in self.parameters:
            _, name = name.split('_')
            print ' smoothing', name
            self.mpirun(
                PATH.SPECFEM_BIN +'/'+ 'xsmooth_sem '
                + str(span) + ' '
                + str(span) + ' '
                + name + ' '
                + path +'/'+ tag + '/ '
                + self.model_databases + '/ ')

        # remove old kernels
        src = path +'/'+ tag
        dst = path +'/'+ tag + '_nosmooth'
        unix.mkdir(dst)
        for name in self.parameters:
            unix.mv(glob(src+'/*'+name+'.bin'), dst)
        unix.rename('_smooth', '', glob(src+'/*'))
        print ''


    ### utility functions

    @property
    def data_wildcard(self):
        return glob('OUTPUT_FILES/*.sem.ascii')

    @property
    def model_databases(self):
        return join(self.getpath, 'OUTPUT_FILES/DATABASES_MPI')

    @property
    def source_prefix(self):
        return 'CMTSOLUTION'


