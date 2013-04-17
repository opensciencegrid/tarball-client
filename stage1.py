#!/usr/bin/env python
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
import shutil
import subprocess
import sys
import tempfile


import yumconf
from common import statusmsg, errormsg

# The list of packages to "install" into the stage 1 dir.  Some of these are
# not always present. For example, EL5 doesn't have java-1.5.0-gcj, and EL6
# doesn't have java-1.4.2-gcj-compat. That's OK to ignore.

STAGE1_PACKAGES = [
    '@core',
    '@base',
    'e2fsprogs',
    'java-1.4.2-gcj-compat',
    'java-1.5.0-gcj',
    'java-1.6.0-sun-compat',
    'jdk',
    'kernel',
    'info',
    'openldap-clients',
    'perl',
    'rpm',  # you would THINK this would be in @core, but in some places it isn't
    'wget',
    'yum',  # see rpm
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


class Error(Exception):
    pass

def make_stage1_root_dir(stage_dir):
    """Make or empty a directory to be used for building the stage1.
    Prompt the user before removing anything (if the dir already exists).

    """
    stage1_root = os.path.realpath(stage_dir)
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


def init_stage1_rpmdb(stage_dir, dver, basearch):
    """Create an rpmdb and fake-install STAGE1_PACKAGES into it."""
    stage1_root = os.path.realpath(stage_dir)
    err = subprocess.call(["rpm", "--initdb", "--root", stage1_root])
    if err:
        raise Error("Could not initialize rpmdb into %r (rpm process returned %d)" % (stage1_root, err))

    yum = yumconf.YumConfig(dver, basearch)
    try:
        yum.yum_clean()
        err2 = yum.fake_install(installroot=stage1_root, packages=STAGE1_PACKAGES)
        if err2:
            raise Error("Could not fake-install %r packages into %r (yum process returned %d)" % (STAGE1_PACKAGES, stage1_root, err2))
    finally:
        del yum


def verify_stage1_dir(stage_dir):
    """Verify the stage_dir is usable as a base to install the rest of the
    software into.

    """
    if not os.path.isdir(stage_dir):
        raise Error("Stage 1 directory (%r) missing" % stage_dir)

    rpmdb_dir = os.path.join(stage_dir, "var/lib/rpm")
    if not os.path.isdir(rpmdb_dir):
        raise Error("RPM database directory (%r) missing" % rpmdb_dir)

    # Not an exhaustive verification (there are more files than these)
    if not (glob.glob(os.path.join(rpmdb_dir, "__db.*")) or    # el5-style rpmdb
            glob.glob(os.path.join(rpmdb_dir, "Packages"))):   # el6-style rpmdb (partial)
        raise Error("RPM database files (__db.* or Packages) missing from %r" % rpmdb_dir)

    # Checking every package fake-installed is overkill for this; do spot check instead
    fnull = open(os.devnull, "w")
    try:
        for pkg in ['bash', 'coreutils', 'filesystem', 'rpm']:
            err = subprocess.call(["rpm", "-q", "--root", os.path.realpath(stage_dir), pkg], stdout=fnull)
            if err:
                raise Error("Package entry for %r not in rpmdb" % pkg)
    finally:
        fnull.close()

    if len(glob.glob(os.path.join(stage_dir, "*"))) > 1:
        raise Error("Unexpected files or directories found under stage 1 directory (%r)" % stage_dir)


def make_stage1_dir(stage_dir, dver, basearch):
    """Fake an installation into the target directory by essentially
    doing the install and then removing all but the rpmdb from the
    directory.

    """
    def _statusmsg(msg):
        statusmsg("[%r,%r]: %s" % (dver, basearch, msg))

    _statusmsg("Using %r for stage 1 directory" % stage_dir)
    try:
        _statusmsg("Making stage 1 root directory")
        make_stage1_root_dir(stage_dir)

        _statusmsg("Initializing stage 1 rpm db")
        init_stage1_rpmdb(stage_dir, dver, basearch)

        _statusmsg("Verifying")
        verify_stage1_dir(stage_dir)

        return True
    except Error, err:
        errormsg(str(err))
        return False


def main(argv):
    if len(argv) != 4:
        print "Usage: %s <output_directory> <el5|el6> <i386|x86_64>" % os.path.basename(argv[0])
        return 2

    if not make_stage1_dir(*argv[1:4]):
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

