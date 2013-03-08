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
import re
import os
import shutil
import subprocess
import sys
import tempfile


import yumconf

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
            print description + " failed"
        raise CalledProcessError("Exit code %d from %r" % (err, command))


def check_running_as_root():
    if os.getuid() != 0:
        print "Error: You need to be root to run this script"
        return False
    return True


def make_stage1_root_dir(stage_dir):
    stage1_root = os.path.realpath(stage_dir)
    if stage1_root == "/":
        print "Error: You may not use '/' as the output directory"
        return False
    try:
        if os.path.isdir(stage1_root):
            print "Stage 1 directory (%r) already exists. Reuse it? Note that the contents will be emptied! " % stage1_root
            user_choice = raw_input("[y/n] ? ").strip().lower()
            if not user_choice.startswith('y'):
                print "Error: Not overwriting %r. Remove it or pass a different directory" % stage1_root
                return False
            shutil.rmtree(stage1_root)
        os.makedirs(stage1_root)
    except OSError, err:
        print "Error creating stage 1 root dir %s: %s" % (stage1_root, str(err))
        return False
    return True


def init_stage1_rpmdb(stage_dir, dver, basearch):
    stage1_root = os.path.realpath(stage_dir)
    conf_file = tempfile.NamedTemporaryFile(suffix='.conf')
    yumconf.write_yum_config(conf_file.file, dver, basearch)

    try:
        try:
            checked_call(["rpm", "--initdb", "--root", stage1_root],
                         "Initialize RPM database")
            checked_call(["yum", "install", "--disablerepo=*", "--installroot", stage1_root, "-c", conf_file.name, "--nogpgcheck", "--enablerepo=osg-release-build", "-y"] + STAGE1_PACKAGES,
                         "Install stage 1 packages")
        except CalledProcessError, err:
            print "Error: " + str(err)
            return False
        return True
    finally:
        conf_file.close()


def clean_files_from_stage1(stage_dir):
    stage1_root = os.path.realpath(stage_dir)

    rpmdb_dir = os.path.join(stage1_root, "var/lib/rpm")
    try:
        tempdir = tempfile.mkdtemp()
        rpmdb_save = os.path.join(tempdir, "rpm")
        try:
            print "Saving rpmdb"
            shutil.copytree(rpmdb_dir, rpmdb_save)
        except OSError, err:
            print "Error saving rpmdb: %s" % str(err)
            return False

        try:
            print "Removing files from stage 1"
            shutil.rmtree(stage1_root)
            print "Restoring rpmdb"
            os.makedirs(os.path.dirname(rpmdb_dir))
            shutil.move(rpmdb_save, rpmdb_dir)
        except OSError, err:
            print "Error restoring rpmdb: %s" % str(err)
            return False

    finally:
        print "Cleaning up temporary files"
        shutil.rmtree(tempdir, ignore_errors=True)

    return True


def verify_stage1_dir(stage_dir):
    """Verify the stage_dir is usable as a base to install the rest of the
    software into.

    """
    if not os.path.isdir(stage_dir):
        print "Error: stage 1 directory (%r) missing" % stage_dir
        return False

    rpmdb_dir = os.path.join(stage_dir, "var/lib/rpm")
    if not os.path.isdir(rpmdb_dir):
        print "Error: rpm database directory (%r) missing" % rpmdb_dir
        return False

    if not glob.glob(os.path.join(rpmdb_dir, "__db.*")):
        print "Error: rpm database files (__db.*) missing from %r" % rpmdb_dir
        return False

    # Checking every package fake-installed is overkill for this; do spot check instead
    fnull = open(os.devnull, "w")
    try:
        for pkg in ['bash', 'coreutils', 'filesystem', 'rpm']:
            err = subprocess.call(["rpm", "-q", "--root", os.path.realpath(stage_dir), pkg], stdout=fnull)
            if err:
                print "Error: package entry for %r not in rpmdb" % pkg
                return False
    finally:
        fnull.close()

    if len(glob.glob(os.path.join(stage_dir, "*"))) > 1:
        print "Error: unexpected files or directories found under stage 1 directory (%r)" % stage_dir
        return False

    return True


def make_stage1_dir(stage_dir, dver, basearch):
    """Fake an installation into the target directory by essentially
    doing the install and then removing all but the rpmdb from the
    directory.

    """
    print "Checking privileges"
    if not check_running_as_root():
        return False

    print "Making stage1 root directory"
    if not make_stage1_root_dir(stage_dir):
        return False

    print "Initializing stage1 rpm db"
    if not init_stage1_rpmdb(stage_dir, dver, basearch):
        return False

    print "Cleaning files from stage1"
    if not clean_files_from_stage1(stage_dir):
        return False

    print "Verifying"
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

