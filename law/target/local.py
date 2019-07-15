# coding: utf-8

"""
Local target implementations.
"""


__all__ = ["LocalFileSystem", "LocalTarget", "LocalFileTarget", "LocalDirectoryTarget"]


import os
import fnmatch
import shutil
import glob
import random
import logging
from contextlib import contextmanager

import luigi
import six

from law.target.file import (
    FileSystem, FileSystemTarget, FileSystemFileTarget, FileSystemDirectoryTarget, get_path,
    get_scheme, remove_scheme, split_transfer_kwargs,
)
from law.target.formatter import find_formatter
from law.config import Config
from law.util import is_file_exists_error


logger = logging.getLogger(__name__)


class LocalFileSystem(FileSystem):

    default_instance = None

    @classmethod
    def parse_config(cls, section, config=None):
        # reads a law config section and returns parsed file system configs
        cfg = Config.instance()

        if config is None:
            config = {}

        # helper to add a config value if it exists, extracted with a config parser method
        def add(key, func):
            if key not in config and not cfg.is_missing_or_none(section, key):
                config[key] = func(section, key)

        # permissions
        add("default_file_perm", cfg.getint)
        add("default_directory_perm", cfg.getint)

        return config

    def __init__(self, config=None, **kwargs):
        cfg = Config.instance()
        if not config:
            config = cfg.get("target", "default_local_fs")

        # config might be a section in the law config
        if isinstance(config, six.string_types) and cfg.has_section(config):
            # parse it
            kwargs = self.parse_config(config, kwargs)

        FileSystem.__init__(self, **kwargs)

    def __eq__(self, other):
        return self.__class__ == other.__class__

    def _unscheme(self, path):
        return remove_scheme(path) if get_scheme(path) == "file" else path

    def abspath(self, path):
        return os.path.abspath(self._unscheme(path))

    def stat(self, path, **kwargs):
        return os.stat(self._unscheme(path))

    def exists(self, path):
        return os.path.exists(self._unscheme(path))

    def isdir(self, path, **kwargs):
        return os.path.isdir(self._unscheme(path))

    def isfile(self, path, **kwargs):
        return os.path.isfile(self._unscheme(path))

    def chmod(self, path, perm, silent=True, **kwargs):
        if perm is not None and (not silent or self.exists(path)):
            os.chmod(self._unscheme(path), perm)

    def remove(self, path, recursive=True, silent=True, **kwargs):
        path = self._unscheme(path)
        if not silent or self.exists(path):
            if self.isdir(path):
                if recursive:
                    shutil.rmtree(path)
                else:
                    os.rmdir(path)
            else:
                os.remove(path)

    def mkdir(self, path, perm=None, recursive=True, silent=True, **kwargs):
        if self.exists(path):
            return

        if perm is None:
            perm = self.default_directory_perm

        # the mode passed to os.mkdir or os.makedirs is ignored on some systems, so the strategy
        # here is to disable the process' current umask, create the directories and use chmod again
        if perm is not None:
            orig = os.umask(0)

        try:
            args = (self._unscheme(path),)
            if perm is not None:
                args += (perm,)
            try:
                (os.makedirs if recursive else os.mkdir)(*args)
            except Exception as e:
                if not silent and not is_file_exists_error(e):
                    raise
            self.chmod(path, perm)
        finally:
            if perm is not None:
                os.umask(orig)

    def listdir(self, path, pattern=None, type=None, **kwargs):
        path = self._unscheme(path)
        elems = os.listdir(path)

        # apply pattern filter
        if pattern is not None:
            elems = fnmatch.filter(elems, pattern)

        # apply type filter
        if type == "f":
            elems = [e for e in elems if not self.isdir(os.path.join(path, e))]
        elif type == "d":
            elems = [e for e in elems if self.isdir(os.path.join(path, e))]

        return elems

    def walk(self, path, max_depth=-1, **kwargs):
        # mimic os.walk with a max_depth and yield the current depth
        search_dirs = [(self._unscheme(path), 0)]
        while search_dirs:
            (search_dir, depth) = search_dirs.pop(0)

            # check depth
            if max_depth >= 0 and depth > max_depth:
                continue

            # find dirs and files
            dirs = []
            files = []
            for elem in self.listdir(search_dir):
                if self.isdir(os.path.join(search_dir, elem)):
                    dirs.append(elem)
                else:
                    files.append(elem)

            # yield everything
            yield (search_dir, dirs, files, depth)

            # use dirs to update search dirs
            search_dirs.extend((os.path.join(search_dir, d), depth + 1) for d in dirs)

    def glob(self, pattern, cwd=None, **kwargs):
        pattern = self._unscheme(pattern)

        if cwd is not None:
            cwd = self._unscheme(cwd)
            pattern = os.path.join(cwd, pattern)

        elems = glob.glob(pattern)

        # cut the cwd if there was any
        if cwd is not None:
            elems = [os.path.relpath(e, cwd) for e in elems]

        return elems

    def _prepare_dst_dir(self, src, dst, perm=None):
        dst = self._unscheme(dst)

        # dst might be an existing directory
        if self.isdir(dst):
            # add src basename to dst
            dst = os.path.join(dst, os.path.basename(src))
        else:
            # create missing dirs
            dst_dir = self.dirname(dst)
            if dst_dir and not self.exists(dst_dir):
                self.mkdir(dst_dir, perm=perm, recursive=True)

        return dst

    def copy(self, src, dst, perm=None, dir_perm=None, **kwargs):
        src = self._unscheme(src)
        dst = self._prepare_dst_dir(src, dst, perm=dir_perm)

        # copy the file
        shutil.copy2(src, dst)

        # set permissions
        if perm is None:
            perm = self.default_file_perm
        self.chmod(dst, perm)

        return dst

    def move(self, src, dst, perm=None, dir_perm=None, **kwargs):
        src = self._unscheme(src)
        dst = self._prepare_dst_dir(src, dst, perm=dir_perm)

        # move the file
        shutil.move(src, dst)

        # set permissions
        if perm is None:
            perm = self.default_file_perm
        self.chmod(dst, perm)

        return dst

    def open(self, path, mode, **kwargs):
        return open(self._unscheme(path), mode)

    def load(self, path, formatter, *args, **kwargs):
        _, kwargs = split_transfer_kwargs(kwargs)
        path = self._unscheme(path)
        return find_formatter(formatter, path).load(path, *args, **kwargs)

    def dump(self, path, formatter, *args, **kwargs):
        _, kwargs = split_transfer_kwargs(kwargs)
        path = self._unscheme(path)
        return find_formatter(formatter, path).dump(path, *args, **kwargs)


LocalFileSystem.default_instance = LocalFileSystem()


class LocalTarget(FileSystemTarget, luigi.LocalTarget):

    fs = LocalFileSystem.default_instance

    def __init__(self, path=None, fs=LocalFileSystem.default_instance, is_tmp=False, tmp_dir=None,
            **kwargs):
        if isinstance(fs, six.string_types):
            fs = LocalFileSystem(fs)

        # handle tmp paths manually since luigi uses the env tmp dir
        if not path:
            if not is_tmp:
                raise Exception("either path or is_tmp must be set")

            # if not set, get the tmp dir from the config and ensure that it exists
            if tmp_dir:
                tmp_dir = get_path(tmp_dir)
            else:
                tmp_dir = os.path.realpath(Config.instance().get_expanded("target", "tmp_dir"))
            if not fs.exists(tmp_dir):
                perm = Config.instance().get("target", "tmp_dir_permission")
                fs.mkdir(tmp_dir, perm=perm and int(perm))

            # create a random path
            while True:
                basename = "luigi-tmp-{:09d}".format(random.randint(0, 999999999))
                path = os.path.join(tmp_dir, basename)
                if not fs.exists(path):
                    break

            # is_tmp might be a file extension
            if isinstance(is_tmp, six.string_types):
                if is_tmp[0] != ".":
                    is_tmp = "." + is_tmp
                path += is_tmp
        else:
            # ensure path is not a target and does not contain, then normalize
            path = remove_scheme(get_path(path))
            path = fs.abspath(os.path.expandvars(os.path.expanduser(path)))

        luigi.LocalTarget.__init__(self, path=path, is_tmp=is_tmp)
        FileSystemTarget.__init__(self, self.path, fs=fs, **kwargs)

    def _repr_flags(self):
        flags = FileSystemTarget._repr_flags(self)
        if self.is_tmp:
            flags.append("temporary")
        return flags


class LocalFileTarget(LocalTarget, FileSystemFileTarget):

    def copy_to_local(self, *args, **kwargs):
        return self.copy_to(*args, **kwargs)

    def copy_from_local(self, *args, **kwargs):
        return self.copy_from(*args, **kwargs)

    def move_to_local(self, *args, **kwargs):
        return self.move_to(*args, **kwargs)

    def move_from_local(self, *args, **kwargs):
        return self.move_from(*args, **kwargs)

    @contextmanager
    def localize(self, mode="r", perm=None, dir_perm=None, tmp_dir=None, **kwargs):
        """ localize(mode="r", perm=None, dir_perm=None, tmp_dir=None, is_tmp=None, **kwargs)
        """
        if mode not in ("r", "w", "a"):
            raise Exception("unknown mode '{}', use 'r', 'w' or 'a'".format(mode))

        logger.debug("localizing file target {!r} with mode '{}'".format(self, mode))

        # get additional arguments
        is_tmp = kwargs.pop("is_tmp", mode in ("w", "a"))

        if mode == "r":
            if is_tmp:
                # create a temporary target
                tmp = self.__class__(is_tmp=self.ext(n=1) or True, tmp_dir=tmp_dir)

                # always copy
                self.copy_to_local(tmp)

                # yield the copy
                try:
                    yield tmp
                finally:
                    tmp.remove()
            else:
                # simply yield
                yield self

        else:  # mode "w" or "a"
            if is_tmp:
                # create a temporary target
                tmp = self.__class__(is_tmp=self.ext(n=1) or True, tmp_dir=tmp_dir)

                # copy in append mode
                if mode == "a" and self.exists():
                    self.copy_to_local(tmp)

                # yield the copy
                try:
                    yield tmp

                    # move back again
                    if tmp.exists():
                        tmp.move_to_local(self, perm=perm, dir_perm=dir_perm)
                    else:
                        logger.warning("cannot move non-existing localized file target {!r}".format(
                            self))
                finally:
                    tmp.remove()
            else:
                # create the parent dir
                self.parent.touch(perm=dir_perm)

                # simply yield
                yield self

                if self.exists():
                    self.chmod(perm)


class LocalDirectoryTarget(LocalTarget, FileSystemDirectoryTarget):

    pass


LocalTarget.file_class = LocalFileTarget
LocalTarget.directory_class = LocalDirectoryTarget
