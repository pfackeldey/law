# -*- coding: utf-8 -*-

"""
High-level extension layer for Luigi analysis workflows.
"""


__author__     = "Marcel Rieger"
__email__      = "python-law@googlegroups.com"
__copyright__  = "Copyright 2016, Marcel Rieger"
__credits__    = ["Marcel Rieger"]
__contact__    = "https://github.com/riga/law"
__license__    = "MIT"
__status__     = "Development"
__version__    = "0.0.3"

__all__ = ["Task", "WrapperTask", "SandboxTask", "LocalWorkflow",
           "LocalFileSystem, LocalFileTarget, LocalDirectoryTarget",
           "DropboxFileSystem", "DropboxFileTarget", "DropboxDirectoryTarget",
           "DCacheFileSystem", "DCacheFileTarget", "DCacheDirectoryTarget",
           "TargetCollection", "SiblingTargetCollection",
           "NO_STR", "NO_INT", "NO_FLOAT", "TaskInstanceParameter", "CSVParameter"]


# patches
from law.patches import patch_all
patch_all()


# provisioning imports
import law.util
from law.parameter import NO_STR, NO_INT, NO_FLOAT, TaskInstanceParameter, CSVParameter
from law.target.local import LocalFileSystem, LocalFileTarget, LocalDirectoryTarget
from law.target.dropbox import DropboxFileSystem, DropboxFileTarget, DropboxDirectoryTarget
from law.target.dcache import DCacheFileSystem, DCacheFileTarget, DCacheDirectoryTarget
from law.target.collection import TargetCollection, SiblingTargetCollection
import law.decorator
from law.task.base import Task, WrapperTask
from law.sandbox.base import SandboxTask
import law.sandbox.docker
from law.workflow.local import LocalWorkflow


# register exit function
import atexit

def exit():
    pass

atexit.register(exit)
