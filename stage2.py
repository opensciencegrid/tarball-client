#!/usr/bin/env python
import glob
import re
import os
import shutil
import subprocess
import sys
import tempfile
import types


import yumconf

from common import statusmsg, errormsg


def install_packages(stage_dir, packages, dver, basearch):
    """Install packages into a stage1 dir"""
    if type(packages) is types.StringType:
        packages = [packages]

    # Make /var/tmp and /var inside the chroot -- that will stop some of the
    # packages' %post scripts from failing.
    real_stage_dir = os.path.realpath(stage_dir)
    for newdir in ["tmp", "var/tmp"]:
        real_newdir = os.path.join(real_stage_dir, newdir)
        if not os.path.isdir(real_newdir):
            os.makedirs(real_newdir)

    conf_file = tempfile.NamedTemporaryFile(suffix='.conf')
    yumconf.write_yum_config(conf_file.file, dver, basearch)
    try:
        cmd = ["yum", "install", "-y", "--installroot", real_stage_dir, "-c", conf_file.name, "--disablerepo=*", "--enablerepo=osg-release-build", "--nogpgcheck"] + packages

        # Don't use return code to check for error.  Yum is going to fail due to
        # scriptlets failing (which we can't really do anything about), but not
        # going to fail due to not finding packages (which we want to find out).
        # So do our own error checking instead.
        subprocess.call(cmd)
    finally:
        conf_file.close()

    # Check that the packages got installed
    for pkg in packages:
        err = subprocess.call(["rpm", "--root", real_stage_dir, "-q", pkg])
        if err:
            errormsg("%r not installed after yum install" % pkg)
            return False

    return True


def patch_installed_packages(stage_dir, patch_dir, dver):
    """Apply all patches in patch_dir to the files in stage_dir

    Assumptions:
    - stage_dir exists and has packages installed into it
    - patch files are to be applied in sorted order
    - patch files are -p1
    - patch files end with .patch

    Return success or failure as a bool
    """

    if not os.path.isdir(patch_dir):
        errormsg("Error: patch directory (%r) not found" % patch_dir)
        return False

    real_patch_dir = os.path.realpath(patch_dir)
    real_stage_dir = os.path.realpath(stage_dir)

    oldwd = os.getcwd()
    try:
        os.chdir(real_stage_dir)
        patch_files = sorted(glob.glob(os.path.join(real_patch_dir, "*.patch")))
        patch_files += sorted(glob.glob(os.path.join(real_patch_dir, dver, "*.patch")))
        for patch_file in patch_files:
            statusmsg("Applying patch %r" % os.path.basename(patch_file))
            err = subprocess.call(['patch', '-p1', '--force', '--input', patch_file])
            if err:
                errormsg("Error: patch file %r failed to apply" % patch_file)
                return False

        return True
    finally:
        os.chdir(oldwd)


def copy_osg_post_scripts(stage_dir, post_scripts_dir):
    """Copy osg scripts from post_scripts_dir to the stage2 directory"""

    if not os.path.isdir(post_scripts_dir):
        errormsg("Error: script directory (%r) not found" % post_scripts_dir)
        return False

    post_scripts_dir_abs = os.path.abspath(post_scripts_dir)
    stage_dir_abs = os.path.abspath(stage_dir)
    dest_dir = os.path.join(stage_dir_abs, "osg")
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)

    try:
        for script in glob.glob(os.path.join(post_scripts_dir_abs, "*")):
            dest_path = os.path.join(dest_dir, os.path.basename(script))
            shutil.copyfile(script, dest_path)
            os.chmod(dest_path, 0755)
    except (IOError, OSError), err:
        errormsg("Error: unable to copy script (%r) to (%r): %s" % (script, dest_dir, str(err)))
        return False

    return True


def clean_stage_dir(stage_dir):
    try:
        os.remove(os.path.join(stage_dir, 'var/log/yum.log'))
        shutil.rmtree(os.path.join(stage_dir, 'tmp'))
        shutil.rmtree(os.path.join(stage_dir, 'var/cache/yum'))
        shutil.rmtree(os.path.join(stage_dir, 'var/lib/rpm'))
        shutil.rmtree(os.path.join(stage_dir, 'var/lib/yum'))
        shutil.rmtree(os.path.join(stage_dir, 'var/tmp'))
        os.makedirs(os.path.join(stage_dir, 'tmp'), 04755)
        os.makedirs(os.path.join(stage_dir, 'var/tmp'), 04755)
    except (IOError, OSError):
        pass

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
        errormsg("Error: unable to create tarball (%r) from stage2 dir (%r)" % (tarball_abs, stage_dir_abs))
        return False

    return True


def make_stage2_tarball(stage_dir, packages, tarball, patch_dirs, post_scripts_dir, dver, basearch):
    statusmsg("Installing packages")
    if not install_packages(stage_dir, packages, dver, basearch):
        return False

    if patch_dirs is not None:
        if type(patch_dirs) is types.StringType:
            patch_dirs = [patch_dirs]

        statusmsg("Patching packages")
        for patch_dir in patch_dirs:
            if not patch_installed_packages(stage_dir, patch_dir, dver):
                return False

    statusmsg("Copying OSG scripts")
    if not copy_osg_post_scripts(stage_dir, post_scripts_dir):
        return False

    statusmsg("Cleaning stage 2 dir")
    if not clean_stage_dir(stage_dir):
        return False

    statusmsg("Creating tarball")
    if not tar_stage_dir(stage_dir, tarball):
        return False

    return True


def main(argv):
    # TODO more command-line options and checking
    stage_dir = argv[1]
    metapackage = argv[2]
    dver = argv[3]
    basearch = argv[4]
    tarball = "%s-%s-%s-nonroot.tar.gz" % (metapackage, dver, basearch)
    # FIXME only works if metapackage is osg-wn-client or osg-client
    patch_dirs = [os.path.join(os.path.dirname(argv[0]), "patches/wn-client")]
    if "osg-client" == metapackage:
        patch_dirs.append(os.path.join(os.path.dirname(argv[0]), "patches/full-client"))
    post_scripts_dir = os.path.join(os.path.dirname(argv[0]), "post-install")

    if not make_stage2_tarball(stage_dir, ['osg-ca-scripts', metapackage], tarball, patch_dirs, post_scripts_dir, dver, basearch):
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
