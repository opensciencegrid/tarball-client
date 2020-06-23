"""
Make a "stage 1" directory for the non-root client.

This directory contains an RPM database with entries for the prerequisites of
the non-root client that are *not* going to ship with the final non-root
tarball. This is software that the user is expected to have on their machine
already, such as 'bash'.

The database is needed for installing the software we will put in the final
tarballs, but will not be included in the tarballs.
"""

import glob
import grp
import os
from os.path import join as opj
import pipes
import shlex
import shutil
import stat
import subprocess
import sys


import yumconf
import common
from common import statusmsg, errormsg, safe_makedirs, Error

# Character devices to put in /dev in the chroot.  Fields are:
# name, major, minor, group, perms
DEVICES = [('core', 1, 6, 'root', 0o600),
           ('mem',  1, 1, 'kmem', 0o640),
           ('null', 1, 3, 'root', 0o666),
           ('port', 1, 4, 'kmem', 0o640),
           ('zero', 1, 5, 'root', 0o666),
           ('urandom', 1, 9, 'root', 0o666)]

def make_stage1_root_dir(stage1_root):
    """Make or empty a directory to be used for building the stage1.
    Prompt the user before removing anything (if the dir already exists).

    """
    if stage1_root == "/":
        raise Error("You may not use '/' as the output directory")
    try:
        if os.path.isdir(stage1_root):
            print "Stage 1 directory (%r) already exists. Reuse it? Note that the contents will be emptied! " % stage1_root
            user_choice = raw_input("[y/n] ? ").strip().lower()
            if not user_choice.startswith('y'):
                raise Error("Not overwriting %r. Remove it or pass a different directory" % stage1_root)
            shutil.rmtree(stage1_root)
        os.makedirs(stage1_root)
    except OSError as err:
        raise Error("Could not create stage 1 root dir %s: %s" % (stage1_root, str(err)))


def init_stage1_rpmdb(stage1_root):
    """Create an rpmdb"""
    err = subprocess.call(["rpm", "--initdb", "--root", stage1_root])
    if err:
        raise Error("Could not initialize rpmdb into %r (rpm process returned %d)" % (stage1_root, err))


def init_stage1_devices(stage1_root):
    """Make /dev file system in the chroot"""
    devdir = os.path.join(stage1_root, 'dev')
    os.makedirs(devdir)
    for name, major, minor, group, perms in DEVICES:
        path = opj(devdir, name)
        try:
            os.mknod(path, perms | stat.S_IFCHR, os.makedev(major, minor))
            os.chown(path, -1, grp.getgrnam(group).gr_gid)
        except EnvironmentError as err:
            raise Error("Could not create /dev/%s in the chroot: %s" % (name, str(err)))


def get_stage1_packages(pkglist_file):
    with open(pkglist_file, 'r') as filehandle:
        return filter(None, shlex.split(filehandle.read(), comments=True))


def _install_stage1_packages(yum, dver, stage1_root, stage1_packages):
    def yuminstall(packages):
        yum.install(installroot=stage1_root, packages=packages)
    def yumforceinstall(packages, **kwargs):
        yum.force_install(installroot=stage1_root, packages=packages, **kwargs)

    yum.yum_clean()
    yumforceinstall(['filesystem'])
    yumforceinstall(['bash', 'grep', 'info', 'findutils', 'libacl', 'libattr'], noscripts=True, resolve=True)
    yumforceinstall(['coreutils'], noscripts=True)
    if dver == 'el6':
        yumforceinstall(['coreutils-libs', 'pam', 'ncurses', 'gmp'], resolve=True)
    if dver in ['el6', 'el7']:
        yuminstall(['yum-plugin-priorities'])
    subprocess.call(['touch', opj(stage1_root, 'etc/fstab')])
    yuminstall(stage1_packages)


def install_stage1_packages(stage1_root, repofile, dver, basearch, pkglist_file):
    stage1_packages = get_stage1_packages(pkglist_file)
    with common.MountProcFS(stage1_root):
        with yumconf.YumInstaller(repofile, dver, basearch) as yum:
            _install_stage1_packages(yum, dver, stage1_root, stage1_packages)


def make_stage1_filelist(stage_dir):
    oldwd = os.getcwd()
    try:
        os.chdir(stage_dir)
        os.system('find . -not -type d > stage1_filelist')
    finally:
        os.chdir(oldwd)


def make_stage1_rpmlist(stage_dir, stage1_root):
    oldwd = os.getcwd()
    try:
        os.chdir(stage_dir)
        os.system('rpm -qa --root=' + pipes.quote(stage1_root) + ' > stage1_rpmlist')
    finally:
        os.chdir(oldwd)


def make_stage1_dir(stage_dir, repofile, dver, basearch, pkglist_file):
    def _statusmsg(msg):
        statusmsg("[%r,%r]: %s" % (dver, basearch, msg))

    _statusmsg("Using %r for stage 1 directory" % stage_dir)
    stage1_root = os.path.realpath(stage_dir)
    try:
        _statusmsg("Making stage 1 root directory")
        make_stage1_root_dir(stage1_root)

        _statusmsg("Initializing stage 1 rpm db")
        init_stage1_rpmdb(stage1_root)

        _statusmsg("Initializing /dev in root dir")
        init_stage1_devices(stage1_root)

        _statusmsg("Installing stage 1 packages from " + pkglist_file)
        install_stage1_packages(stage1_root, repofile, dver, basearch, pkglist_file)

        _statusmsg("Making file list")
        make_stage1_filelist(stage_dir)

        _statusmsg("Making rpm list")
        make_stage1_rpmlist(stage_dir, stage1_root)

        return True
    except Error as err:
        errormsg(str(err))
        return False
