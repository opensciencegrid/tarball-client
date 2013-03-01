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


# The list of packages to "install" into the stage 1 dir.
# TODO Add to it until all dependencies we're not going to provide
# are in the list.
STAGE1_PACKAGES = [
    '@core',
    'info', # needed for "/sbin/install-info", used in wget's %post script
    'perl',
    'wget',
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

def main(argv):
    """Fake an installation into the target directory by essentially
    doing the install and then removing all but the rpmdb from the
    directory.

    """
    if len(argv) < 2:
        print "Usage: %s <output_directory>" % argv[0]
        return 2
    
    if os.getuid() != 0:
        print "You need to be root to run this script"
        return 1
    
    stage1_root = os.path.realpath(argv[1])
    if stage1_root == "/":
        print "You may not use '/' as the output directory"
        return 1
    try:
        if os.path.isdir(stage1_root):
            print "Stage 1 directory (%r) already exists. Reuse it? Note that the contents will be emptied! " % stage1_root
            user_choice = raw_input("[y/n] ? ").strip().lower()
            if not user_choice.startswith('y'):
                print "Remove %r or pass a different directory" % stage1_root
                return 1
            shutil.rmtree(stage1_root)
        os.makedirs(stage1_root)
    except OSError, err:
        print "Error creating stage 1 root dir %s: %s" % (stage1_root, str(err))
        return 1
    
    try:
        checked_call(["rpm", "--initdb", "--root", stage1_root],
                     "Initialize RPM database")
        checked_call(["yum", "install", "--installroot", stage1_root, "-y"] + STAGE1_PACKAGES,
                     "Install stage 1 packages")
    except CalledProcessError, err:
        print str(err)
        return 1
    
    rpmdb_dir = os.path.join(stage1_root, "var/lib/rpm")
    try:
        tempdir = tempfile.mkdtemp()
        rpmdb_save = os.path.join(tempdir, "rpm")
        try:
            print "Saving rpmdb"
            shutil.copytree(rpmdb_dir, rpmdb_save)
        except OSError, err:
            print "Error saving rpmdb: %s" % str(err)
            return 1
    
        try:
            print "Removing files from stage 1"
            shutil.rmtree(stage1_root)
            print "Restoring rpmdb"
            os.makedirs(os.path.dirname(rpmdb_dir))
            shutil.move(rpmdb_save, rpmdb_dir)
        except OSError, err:
            print "Error restoring rpmdb: %s" % str(err)
            return 1

    finally:
        shutil.rmtree(tempdir, ignore_errors=True)

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

