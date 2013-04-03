#!/usr/bin/env python
import glob
import os
import re
import shutil
import subprocess
import sys
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

    yum = yumconf.YumConfig(dver, basearch)
    try:
        statusmsg("Installing packages. Ignore POSTIN scriptlet failures.")
        yum.install(installroot=real_stage_dir, packages=packages)
    finally:
        del yum

    # Don't use return code to check for error.  Yum is going to fail due to
    # scriptlets failing (which we can't really do anything about), but not
    # going to fail due to not finding packages (which we want to find out).
    # So we just check that the packages got installed
    for pkg in packages:
        err = subprocess.call(["rpm", "--root", real_stage_dir, "-q", pkg])
        if err:
            errormsg("%r not installed after yum install" % pkg)
            return False

    return True


def _cmp_basename(left, right):
    """String comparison on file paths based on the basename of each file.

    Example, '02-foo.patch' should sort after 'el5/01-bar.patch'

    """
    return cmp(os.path.basename(left), os.path.basename(right))


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
        patch_files = glob.glob(os.path.join(real_patch_dir, "*.patch"))
        patch_files += glob.glob(os.path.join(real_patch_dir, dver, "*.patch"))
        patch_files.sort(cmp=_cmp_basename)
        for patch_file in patch_files:
            statusmsg("Applying patch %r" % os.path.basename(patch_file))
            err = subprocess.call(['patch', '-p1', '--force', '--input', patch_file])
            if err:
                errormsg("Error: patch file %r failed to apply" % patch_file)
                return False

        return True
    finally:
        os.chdir(oldwd)


def fix_osg_version(stage_dir, relnum=""):
    osg_version_path = os.path.join(os.path.abspath(stage_dir), 'etc/osg-version')
    osg_version_fh = open(osg_version_path)
    version_str = new_version_str = ""
    _relnum = ""
    if relnum:
        _relnum = "-" + relnum
    try:
        version_str = osg_version_fh.readline()
        if not version_str:
            errormsg("Could not read version string from %r" % osg_version_path)
            return False
        if not re.match(r'[0-9.]+', version_str):
            errormsg("%r does not contain version" % osg_version_path)
            return False

        new_version_str = re.sub(r'^([0-9.]+)(?!-tarball)', r'\1-tarball%s' % (_relnum), version_str)
    finally:
        osg_version_fh.close()

    osg_version_write_fh = open(osg_version_path, 'w')
    try:
        osg_version_write_fh.write(new_version_str)
    finally:
        osg_version_write_fh.close()
    return True


def fix_gsissh_config_dir(stage_dir):
    """A hack to fix gsissh, which looks for $GLOBUS_LOCATION/etc/ssh.
    The actual files are in $OSG_LOCATION/etc/gsissh, so make a symlink.
    Make it a relative symlink so we don't have to fix it in post-install.

    """
    stage_dir_abs = os.path.abspath(stage_dir)

    if not os.path.isdir(os.path.join(stage_dir_abs, 'etc/gsissh')):
        return True

    try:
        usr_etc = os.path.join(stage_dir_abs, 'usr/etc')
        if not os.path.isdir(usr_etc):
            os.makedirs(usr_etc)
        os.symlink('../../etc/gsissh', os.path.join(usr_etc, 'ssh'))
    except EnvironmentError, err:
        errormsg("Error: unable to fix gsissh config dir: %s" % str(err))
        return False

    return True


def remove_broken_cog_axis(stage_dir):
    stage_dir_abs = os.path.abspath(stage_dir)

    cog_axis_path = os.path.join(stage_dir_abs, 'usr/share/java', 'cog-axis-1.8.0.jar')
    if os.path.exists(cog_axis_path):
        os.remove(cog_axis_path)
    return True


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


def tar_stage_dir(stage_dir, tarball):
    """tar up the stage_dir
    Assume: valid stage2 dir
    """
    stage_dir_abs = os.path.abspath(stage_dir)
    tarball_abs = os.path.abspath(tarball)
    stage_dir_parent = os.path.dirname(stage_dir_abs)
    stage_dir_base = os.path.basename(stage_dir)

    excludes = ["var/log/yum.log",
                "tmp/*",
                "var/cache/yum/*",
                #"var/lib/rpm/*",
                #"var/lib/yum/*",
                "var/tmp/*"]

    cmd = ["tar", "-C", stage_dir_parent, "-czf", tarball_abs, stage_dir_base]
    cmd.extend(["--exclude=" + x for x in excludes])

    err = subprocess.call(cmd)
    if err:
        errormsg("Error: unable to create tarball (%r) from stage 2 dir (%r)" % (tarball_abs, stage_dir_abs))
        return False

    return True


def make_stage2_tarball(stage_dir, packages, tarball, patch_dirs, post_scripts_dir, dver, basearch, relnum=0):
    def _statusmsg(msg):
        statusmsg("[%r,%r]: %s" % (dver, basearch, msg))

    _statusmsg("Installing packages %r into %r" % (packages, stage_dir))
    if not install_packages(stage_dir, packages, dver, basearch):
        return False

    if patch_dirs is not None:
        if type(patch_dirs) is types.StringType:
            patch_dirs = [patch_dirs]

        _statusmsg("Patching packages using %r in %r" % (patch_dirs, stage_dir))
        for patch_dir in patch_dirs:
            if not patch_installed_packages(stage_dir, patch_dir, dver):
                return False

    _statusmsg("Fixing gsissh config dir (if needed) in %r" % (stage_dir))
    if not fix_gsissh_config_dir(stage_dir):
        return False

    _statusmsg("Fixing osg-version in %r" % (stage_dir))
    if not fix_osg_version(stage_dir, relnum):
        return False

    _statusmsg("Removing broken cog-axis jar")

    _statusmsg("Copying OSG scripts from %r to %r" % (post_scripts_dir, stage_dir))
    if not copy_osg_post_scripts(stage_dir, post_scripts_dir):
        return False

    _statusmsg("Creating tarball from %r as %r" % (stage_dir, tarball))
    if not tar_stage_dir(stage_dir, tarball):
        return False

    return True


def main(argv):
    # This main function was for initial testing, which is why it's light on
    # checking.
    stage_dir = argv[1]
    metapackage = argv[2]
    dver = argv[3]
    basearch = argv[4]
    tarball = "%s-%s-%s-nonroot.tar.gz" % (metapackage, dver, basearch)
    patch_dirs = [os.path.join(os.path.dirname(argv[0]), "patches/wn-client")]
    if "osg-client" == metapackage:
        patch_dirs.append(os.path.join(os.path.dirname(argv[0]), "patches/full-client"))
    post_scripts_dir = os.path.join(os.path.dirname(argv[0]), "post-install")

    if not make_stage2_tarball(stage_dir, ['osg-ca-scripts', metapackage], tarball, patch_dirs, post_scripts_dir, dver, basearch):
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
