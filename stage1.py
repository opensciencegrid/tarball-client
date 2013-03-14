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

# The list of packages to "install" into the stage 1 dir.
# TODO Add to it until all dependencies we're not going to provide
# are in the list.
STAGE1_PACKAGES = [
    '@core',
    'info', # needed for "/sbin/install-info", used in wget's %post script
    'rpm',  # you would THINK this would be in @core, but in some places it isn't
    'perl',
    'wget',
    'yum',  # see rpm
    'zip',
]


class CalledProcessError(Exception):
    pass


def checked_call(command, description=""):
    err = subprocess.call(command)
    if err:
        if description:
            errormsg(description + " failed")
        raise CalledProcessError("Exit code %d from %r" % (err, command))


def check_running_as_root():
    if os.getuid() != 0:
        errormsg("Error: You need to be root to run this script")
        return False
    return True


def make_stage1_root_dir(stage_dir):
    stage1_root = os.path.realpath(stage_dir)
    if stage1_root == "/":
        errormsg("Error: You may not use '/' as the output directory")
        return False
    try:
        if os.path.isdir(stage1_root):
            print "Stage 1 directory (%r) already exists. Reuse it? Note that the contents will be emptied! " % stage1_root
            user_choice = raw_input("[y/n] ? ").strip().lower()
            if not user_choice.startswith('y'):
                errormsg("Error: Not overwriting %r. Remove it or pass a different directory" % stage1_root)
                return False
            shutil.rmtree(stage1_root)
        os.makedirs(stage1_root)
    except OSError, err:
        errormsg("Error creating stage 1 root dir %s: %s" % (stage1_root, str(err)))
        return False
    return True


def init_stage1_rpmdb(stage_dir, dver, basearch):
    stage1_root = os.path.realpath(stage_dir)
    err = subprocess.call(["rpm", "--initdb", "--root", stage1_root])
    if err:
        errormsg("Error initializing rpmdb into %r (rpm process returned %d)" % (stage1_root, err))
        return False

    yum = yumconf.YumConfig(dver, basearch)
    err2 = yum.install(installroot=stage1_root, packages=STAGE1_PACKAGES)
    if err2:
        errormsg("Error installing %r packages into %r (yum process returned %d)" % (STAGE1_PACKAGES, stage1_root, err2))
        return False

    return True


def clean_files_from_stage1(stage_dir):
    stage1_root = os.path.realpath(stage_dir)

    rpmdb_dir = os.path.join(stage1_root, "var/lib/rpm")
    try:
        tempdir = tempfile.mkdtemp()
        rpmdb_save = os.path.join(tempdir, "rpm")
        try:
            statusmsg("Saving rpmdb")
            shutil.copytree(rpmdb_dir, rpmdb_save)
        except OSError, err:
            errormsg("Error saving rpmdb: %s" % str(err))
            return False

        try:
            statusmsg("Removing files from stage 1")
            shutil.rmtree(stage1_root)
            statusmsg("Restoring rpmdb")
            os.makedirs(os.path.dirname(rpmdb_dir))
            shutil.move(rpmdb_save, rpmdb_dir)
        except OSError, err:
            errormsg("Error restoring rpmdb: %s" % str(err))
            return False

    finally:
        statusmsg("Cleaning up temporary files")
        shutil.rmtree(tempdir, ignore_errors=True)

    return True


def verify_stage1_dir(stage_dir):
    """Verify the stage_dir is usable as a base to install the rest of the
    software into.

    """
    if not os.path.isdir(stage_dir):
        errormsg("Error: stage 1 directory (%r) missing" % stage_dir)
        return False

    rpmdb_dir = os.path.join(stage_dir, "var/lib/rpm")
    if not os.path.isdir(rpmdb_dir):
        errormsg("Error: rpm database directory (%r) missing" % rpmdb_dir)
        return False

    # Not an exhaustive verification (there are more files than these)
    if not (glob.glob(os.path.join(rpmdb_dir, "__db.*")) or    # el5-style rpmdb
            glob.glob(os.path.join(rpmdb_dir, "Packages"))):   # el6-style rpmdb (partial)
        errormsg("Error: rpm database files (__db.* or Packages) missing from %r" % rpmdb_dir)
        return False

    # Checking every package fake-installed is overkill for this; do spot check instead
    fnull = open(os.devnull, "w")
    try:
        for pkg in ['bash', 'coreutils', 'filesystem', 'rpm']:
            err = subprocess.call(["rpm", "-q", "--root", os.path.realpath(stage_dir), pkg], stdout=fnull)
            if err:
                errormsg("Error: package entry for %r not in rpmdb" % pkg)
                return False
    finally:
        fnull.close()

    if len(glob.glob(os.path.join(stage_dir, "*"))) > 1:
        errormsg("Error: unexpected files or directories found under stage 1 directory (%r)" % stage_dir)
        return False

    return True


def make_stage1_dir(stage_dir, dver, basearch):
    """Fake an installation into the target directory by essentially
    doing the install and then removing all but the rpmdb from the
    directory.

    """
    statusmsg("Checking privileges")
    if not check_running_as_root():
        return False

    statusmsg("Making stage1 root directory")
    if not make_stage1_root_dir(stage_dir):
        return False

    statusmsg("Initializing stage1 rpm db")
    if not init_stage1_rpmdb(stage_dir, dver, basearch):
        return False

    statusmsg("Cleaning files from stage1")
    if not clean_files_from_stage1(stage_dir):
        return False

    statusmsg("Verifying")
    if not verify_stage1_dir(stage_dir):
        return False

    return True


def main(argv):
    if len(argv) != 4:
        print "Usage: %s <output_directory> <el5|el6> <i386|x86_64>" % os.path.basename(argv[0])
        return 2

    if not make_stage1_dir(*argv[1:4]):
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

