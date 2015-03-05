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
import os
from os.path import join as opj
import shutil
import subprocess
import sys


import yumconf
import common
from common import statusmsg, errormsg, safe_makedirs

# The list of packages to "install" into the stage 1 dir.  Some of these are
# not always present. For example, EL5 doesn't have java-1.5.0-gcj, and EL6
# doesn't have java-1.4.2-gcj-compat. That's OK to ignore.

STAGE1_PACKAGES = [
    'e2fsprogs',
    'java-1.4.2-gcj-compat',
    'java-1.5.0-gcj',
    'java-1.6.0-openjdk',
    'java-1.7.0-openjdk',
    'java-1.7.0-openjdk-devel',
    'kernel',
    'info',
    'openldap-clients',
    'perl',
    'rpm',
    'wget',
    'yum',
    'zip',
    # X libraries
    'libXau',
    'libXdmcp',
    'libX11',
    'libXext',
    'libXfixes',
    'libXi',
    'libXtst',
    'libXft',
    'libXrender',
    'libXrandr',
    'libXcursor',
    'libXinerama',
]


class Error(Exception): pass
class YumInstallError(Error):
    def __init__(self, packages, rootdir, err):
        super(self.__class__, self).__init__("Could not install %r into %r (yum process returned %d)" % (packages, rootdir, err))


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
    except OSError, err:
        raise Error("Could not create stage 1 root dir %s: %s" % (stage1_root, str(err)))


def init_stage1_rpmdb(stage1_root):
    """Create an rpmdb"""
    err = subprocess.call(["rpm", "--initdb", "--root", stage1_root])
    if err:
        raise Error("Could not initialize rpmdb into %r (rpm process returned %d)" % (stage1_root, err))


def init_stage1_devices(stage1_root):
    """Make /dev file system in the chroot"""
    devdir = os.path.join(stage1_root, 'dev')
    for device in ['mem', 'null', 'port', 'zero', 'core']:
        err = subprocess.call(['MAKEDEV', '-d', devdir, '-D', devdir, '-v', device])
    if err:
        raise Error("Could not run MAKEDEV into %r (process returned %d)" % (stage1_root, err))


def _install_stage1_packages(yum, dver, stage1_root):
    def yuminstall(packages):
        err = yum.install(installroot=stage1_root, packages=packages)
        if err:
            raise YumInstallError(packages, stage1_root, err)
    def yumforceinstall(packages, **kwargs):
        err = yum.force_install(installroot=stage1_root, packages=packages, **kwargs)
        if err:
            raise YumInstallError(packages, stage1_root, err)

    yum.yum_clean()
    yumforceinstall(['filesystem'])
    yumforceinstall(['bash', 'grep', 'info', 'findutils', 'libacl', 'libattr'], noscripts=True, resolve=True)
    yumforceinstall(['coreutils'], noscripts=True)
    if dver == 'el6':
        yumforceinstall(['coreutils-libs', 'pam', 'ncurses', 'gmp'], resolve=True)
    yuminstall(['glibc', 'glibc-common', 'libselinux'])
    subprocess.call(['touch', opj(stage1_root, 'etc/fstab')])
    safe_makedirs(opj(stage1_root, 'etc/modprobe.d'))
    subprocess.call(['touch', opj(stage1_root, 'etc/modprobe.d/dummy.conf')])
    yuminstall(STAGE1_PACKAGES)


def install_stage1_packages(stage1_root, osgver, dver, basearch):
    with common.MountProcFS(stage1_root):
        with yumconf.YumConfig(osgver, dver, basearch) as yum:
            _install_stage1_packages(yum, dver, stage1_root)


def make_stage1_filelist(stage_dir):
    oldwd = os.getcwd()
    try:
        os.chdir(stage_dir)
        os.system('find . -not -type d > stage1_filelist')
    finally:
        os.chdir(oldwd)


def make_stage1_dir(stage_dir, osgver, dver, basearch):
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

        _statusmsg("Installing stage 1 packages")
        install_stage1_packages(stage1_root, osgver, dver, basearch)

        _statusmsg("Making file list")
        make_stage1_filelist(stage_dir)

        return True
    except Error, err:
        errormsg(str(err))
        return False
