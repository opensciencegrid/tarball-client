#!/usr/bin/env python
import glob
import re
import os
import shutil
import subprocess
import sys
import tempfile
import types


def verify_stage1(stage_dir):
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


def install_packages(stage_dir, packages):
    """Install packages into a stage1 dir"""
    if type(packages) is types.StringType:
        packages = [packages]

    # Make /var/tmp and /var inside the chroot -- that will stop most of the
    # packages' %post scripts from failing.
    real_stage_dir = os.path.realpath(stage_dir)
    for newdir in ["tmp", "var/tmp"]:
        real_newdir = os.path.join(real_stage_dir, newdir)
        if not os.path.isdir(real_newdir):
            os.makedirs(real_newdir)

    cmd = ["yum", "install", "-y", "--installroot", real_stage_dir] + packages

    # Don't use return code to check for error.  Yum is going to fail due to
    # scriptlets failing (which we can't really do anything about), but not
    # going to fail due to not finding packages (which we want to find out).
    # So do our own error checking instead.
    subprocess.call(cmd)

    # Check that the packages got installed
    for pkg in packages:
        err = subprocess.call(["rpm", "--root", real_stage_dir, "-q", pkg])
        if err:
            print "%r not installed after yum install" % pkg
            return False

    return True


def patch_installed_packages(stage_dir, patch_dir):
    """Apply all patches in patch_dir to the files in stage_dir

    Assumptions:
    - stage_dir exists and has packages installed into it
    - patch files are to be applied in sorted order
    - patch files are -p1
    - patch files end with .patch

    Return success or failure as a bool
    """

    if not os.path.isdir(patch_dir):
        print "Error: patch directory (%r) not found" % patch_dir
        return False

    real_patch_dir = os.path.realpath(patch_dir)
    real_stage_dir = os.path.realpath(stage_dir)

    oldwd = os.getcwd()
    try:
        os.chdir(real_stage_dir)
        for patch_file in sorted(glob.glob(os.path.join(real_patch_dir, "*.patch"))):
            print "Applying patch %r" % os.path.basename(patch_file)
            err = subprocess.call(['patch', '-p1', '--force', '--input', patch_file])
            if err:
                print "Error: patch file %r failed to apply" % patch_file
                return False

        return True
    finally:
        os.chdir(oldwd)


def copy_osg_scripts(stage_dir, scripts_dir):
    """Copy osg scripts from scripts_dir to the stage2 directory"""

    if not os.path.isdir(scripts_dir):
        print "Error: script directory (%r) not found" % scripts_dir
        return False

    scripts_dir_abs = os.path.abspath(scripts_dir)
    stage_dir_abs = os.path.abspath(stage_dir)

    try:
        for script in glob.glob(os.path.join(scripts_dir_abs, "*")):
            dest_path = os.path.join(stage_dir_abs, os.path.basename(script))
            shutil.copyfile(script, dest_path)
            os.chmod(dest_path, 0755)
    except (IOError, OSError), err:
        print "Error: unable to copy script (%r) to stage2 dir (%r): %s" % (script, stage_dir_abs, str(err))
        return False

    return True



def tar_stage_dir(stage_dir, tarball):
    """tar up the stage_dir
    Assume: valid stage2 dir
    """
    stage_dir_abs = os.path.abspath(stage_dir)
    tarball_abs = os.path.abspath(tarball)
    stage_dir_parent = os.path.dirname(stage_dir_abs)
    stage_dir_base = os.path.basename(stage_dir)

    err = subprocess.call(["tar", "-C", stage_dir_parent, "-cvzf", tarball_abs, stage_dir_base])
    if err:
        print "Error: unable to create tarball (%r) from stage2 dir (%r)" % (tarball_abs, stage_dir_abs)
        return False

    return True


def make_stage2_tarball(stage_dir, packages, tarball, patch_dirs, scripts_dir):
    print "Installing packages"
    if not install_packages(stage_dir, packages):
        return False

    if patch_dirs is not None:
        print "Patching packages"
        # TODO EC
        for patch_dir in patch_dirs:
            if not patch_installed_packages(stage_dir, patch_dir):
                return False

    print "Copying OSG scripts"
    if not copy_osg_scripts(stage_dir, scripts_dir):
        return False

    print "Creating tarball"
    if not tar_stage_dir(stage_dir, tarball):
        return False

    return True


def main(argv):
    # TODO more command-line options and checking
    stage_dir = argv[1]
    metapackage = argv[2]
    tarball = metapackage + "-nonroot.tar.gz"
    # FIXME only works if metapackage is osg-wn-client or osg-client
    patch_dirs = [os.path.join(os.path.dirname(argv[0]), "patches/wn-client")]
    if "osg-client" == metapackage:
        patch_dirs.append(os.path.join(os.path.dirname(argv[0]), "patches/full-client"))
    scripts_dir = os.path.join(os.path.dirname(argv[0]), "post-install")

    if not make_stage2_tarball(stage_dir, [metapackage], tarball, patch_dirs, scripts_dir):
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
