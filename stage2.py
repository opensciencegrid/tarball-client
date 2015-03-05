from __future__ import print_function
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types


import envsetup
import yumconf

import common
from common import statusmsg, errormsg, safe_makedirs, safe_symlink, Error


def install_packages(stage_dir_abs, packages, osgver, dver, basearch, prerelease=False):
    """Install packages into a stage1 dir"""
    if type(packages) is types.StringType:
        packages = [packages]

    with common.MountProcFS(stage_dir_abs):
        with yumconf.YumInstaller(osgver, dver, basearch, prerelease=prerelease) as yum:
            yum.install(installroot=stage_dir_abs, packages=packages)

    # Check that the packages got installed
    for pkg in packages:
        err = subprocess.call(["rpm", "--root", stage_dir_abs, "-q", pkg])
        if err:
            raise Error("%r not installed after yum install" % pkg)


def _cmp_basename(left, right):
    """String comparison on file paths based on the basename of each file.

    Example, '02-foo.patch' should sort after 'el5/01-bar.patch'

    """
    return cmp(os.path.basename(left), os.path.basename(right))


def patch_installed_packages(stage_dir_abs, patch_dir, dver, osgver):
    """Apply all patches in patch_dir to the files in stage_dir_abs

    Assumptions:
    - stage_dir_abs exists and has packages installed into it
    - patch files are to be applied in sorted order (by filename; directory
      name does not matter)
    - patch files are -p1
    - patch files end with .patch

    Return success or failure as a bool
    """

    if not os.path.isdir(patch_dir):
        raise Error("patch directory (%r) not found" % patch_dir)

    patch_dir_abs = os.path.abspath(patch_dir)

    subdirs = ["common", os.path.join("common", dver), osgver, os.path.join(osgver, dver)]

    oldwd = os.getcwd()
    try:
        os.chdir(stage_dir_abs)
        patch_files = []
        for subdir in subdirs:
            patch_files += glob.glob(os.path.join(patch_dir_abs, subdir, "*.patch"))
        patch_files.sort(cmp=_cmp_basename)
        for patch_file in patch_files:
            statusmsg("Applying patch %r" % os.path.basename(patch_file))
            err = subprocess.call(['patch', '-p1', '--force', '--input', patch_file])
            if err:
                raise Error("patch file %r failed to apply" % patch_file)
    finally:
        os.chdir(oldwd)


def fix_osg_version(stage_dir_abs, relnum=""):
    osg_version_path = os.path.join(stage_dir_abs, 'etc/osg-version')
    version_str = new_version_str = ""
    _relnum = ""
    if relnum:
        _relnum = "-" + str(relnum)

    with open(osg_version_path) as osg_version_fh:
        version_str = osg_version_fh.readline()
        if not version_str:
            raise Error("Could not read version string from %r" % osg_version_path)
        if not re.match(r'[0-9.]+', version_str):
            raise Error("%r does not contain version" % osg_version_path)

        if 'tarball' in version_str:
            new_version_str = version_str
        else:
            new_version_str = re.sub(r'^([0-9.]+)(?!-tarball)', r'\1-tarball%s' % (_relnum), version_str)

    with open(osg_version_path, 'w') as osg_version_write_fh:
        osg_version_write_fh.write(new_version_str)


def fix_gsissh_config_dir(stage_dir_abs):
    """A hack to fix gsissh, which looks for $GLOBUS_LOCATION/etc/ssh.
    The actual files are in $OSG_LOCATION/etc/gsissh, so make a symlink.
    Make it a relative symlink so we don't have to fix it in post-install.

    """
    if not os.path.isdir(os.path.join(stage_dir_abs, 'etc/gsissh')):
        return

    try:
        usr_etc = os.path.join(stage_dir_abs, 'usr/etc')
        safe_makedirs(usr_etc)
        os.symlink('../../etc/gsissh', os.path.join(usr_etc, 'ssh'))
    except EnvironmentError as err:
        raise Error("unable to fix gsissh config dir: %s" % str(err))


def copy_osg_post_scripts(stage_dir_abs, post_scripts_dir, dver, basearch):
    """Copy osg scripts from post_scripts_dir to the stage2 directory"""

    if not os.path.isdir(post_scripts_dir):
        raise Error("script directory (%r) not found" % post_scripts_dir)

    post_scripts_dir_abs = os.path.abspath(post_scripts_dir)
    dest_dir = os.path.join(stage_dir_abs, "osg")
    safe_makedirs(dest_dir)

    for script_name in 'osg-post-install', 'osgrun.in':
        script_path = os.path.join(post_scripts_dir_abs, script_name)
        dest_path = os.path.join(dest_dir, script_name)
        try:
            shutil.copyfile(script_path, dest_path)
            os.chmod(dest_path, 0755)
        except EnvironmentError as err:
            raise Error("unable to copy script (%r) to (%r): %s" % (script_path, dest_dir, str(err)))

    try:
        envsetup.write_setup_in_files(dest_dir, dver, basearch)
    except EnvironmentError as err:
        raise Error("unable to create environment script templates (setup.csh.in, setup.sh.in): %s" % str(err))


def _write_exclude_list(stage1_filelist_path, exclude_list_path, prepend_dir, extra_excludes=None):
    assert stage1_filelist_path != exclude_list_path
    with open(stage1_filelist_path, 'r') as in_fh:
        with open(exclude_list_path, 'w') as out_fh:
            for line in in_fh:
                out_fh.write(os.path.join(prepend_dir, line.lstrip('./')))
    if extra_excludes:
        with open(exclude_list_path, 'a') as out_fh:
            for excl in extra_excludes:
                out_fh.write(os.path.join(prepend_dir, excl) + '\n')


def tar_stage_dir(stage_dir_abs, tarball):
    """tar up the stage_dir
    Assume: valid stage2 dir
    """
    tarball_abs = os.path.abspath(tarball)
    stage_dir_parent = os.path.dirname(stage_dir_abs)
    stage_dir_base = os.path.basename(stage_dir_abs)

    excludes = ["var/log/yum.log",
                "tmp/*",
                "var/cache/yum/*",
                "var/lib/rpm/*",
                "var/lib/yum/*",
                "var/tmp/*",
                "dev/*",
                "proc/*",
                "etc/rc.d/rc?.d",
                "etc/alternatives",
                "var/lib/alternatives",
                "usr/bin/[[]",
                "usr/share/man/man1/[[].1.gz",
                "bin/dbus*",
                "lib/libcap*",
                "lib/dbus*",
                "lib/security/pam*.so",
                "lib64/libcap*",
                "lib64/dbus*",
                "lib64/security/pam*.so",
                "usr/bin/gnome*"]

    cmd = ["tar", "-C", stage_dir_parent, "-czf", tarball_abs, stage_dir_base]

    stage1_filelist = os.path.join(stage_dir_abs, 'stage1_filelist')
    if os.path.isfile(stage1_filelist):
        exclude_list = os.path.join(stage_dir_parent, 'exclude_list')
        _write_exclude_list(stage1_filelist, exclude_list, stage_dir_base, excludes)
        cmd.append('--exclude-from=%s' % exclude_list)

    err = subprocess.call(cmd)
    if err:
        raise Error("unable to create tarball (%r) from stage 2 dir (%r)" % (tarball_abs, stage_dir_abs))


def fix_broken_cog_axis_symlink(stage_dir_abs):
    """cog-axis-1.8.0.jar points to cog-jglobus-axis.jar, but is an absolute
    symlink; replace it with a relative one.

    """
    cog_axis_path = os.path.join(stage_dir_abs, 'usr/share/java', 'cog-axis-1.8.0.jar')
    # using lexists because os.path.exists returns False for a broken symlink
    # -- which is what we're expecting
    if os.path.lexists(cog_axis_path):
        os.remove(cog_axis_path)
        os.symlink("cog-jglobus-axis.jar", cog_axis_path)


def create_fetch_crl_symlinks(stage_dir_abs, dver):
    """fetch-crl3 on el5 is called fetch-crl on el6. Make symlinks (both ways)
    to reduce confusion.

    """
    if 'el5' == dver:
        safe_symlink('fetch-crl3.conf', os.path.join(stage_dir_abs, 'etc/fetch-crl.conf'))
        safe_symlink('fetch-crl3', os.path.join(stage_dir_abs, 'usr/sbin/fetch-crl'))
        safe_symlink('fetch-crl3.8.gz', os.path.join(stage_dir_abs, 'usr/share/man/man8/fetch-crl.8.gz'))
    elif 'el6' == dver:
        safe_symlink('fetch-crl.conf', os.path.join(stage_dir_abs, 'etc/fetch-crl3.conf'))
        safe_symlink('fetch-crl', os.path.join(stage_dir_abs, 'usr/sbin/fetch-crl3'))
        safe_symlink('fetch-crl.8.gz', os.path.join(stage_dir_abs, 'usr/share/man/man8/fetch-crl3.8.gz'))


def fix_alternatives_symlinks(stage_dir_abs):
    for root, dirs, files in os.walk(os.path.join(stage_dir_abs, 'usr')):
        for afile in files:
            afilepath = os.path.join(root, afile)
            if not os.path.islink(afilepath):
                continue
            linkpath = os.readlink(afilepath)
            if not linkpath.startswith('/etc/alternatives'):
                continue
            stage_linkpath = os.path.join(stage_dir_abs, linkpath.lstrip('/'))
            if not os.path.islink(stage_linkpath):
                print("broken symlink to alternatives? {0} -> {1}".format(afilepath, stage_linkpath))
                continue
            alternatives_linkpath = os.readlink(stage_linkpath)
            stage_alternatives_linkpath = os.path.join(stage_dir_abs, alternatives_linkpath.lstrip('/'))
            if not os.path.exists(stage_alternatives_linkpath):
                print("broken symlink from alternatives? {0} -> {1}".format(stage_linkpath, stage_alternatives_linkpath))
                continue
            new_linkpath = os.path.relpath(stage_alternatives_linkpath, start=os.path.dirname(afilepath))
            os.unlink(afilepath)
            os.symlink(new_linkpath, afilepath)


def fix_permissions(stage_dir_abs):
    return subprocess.call(['chmod', '-R', 'u+rwX', stage_dir_abs])


def remove_empty_dirs_from_tarball(tarball, topdir):
    tarball_abs = os.path.abspath(tarball)
    tarball_base = os.path.basename(tarball)
    extract_dir = tempfile.mkdtemp()
    oldcwd = os.getcwd()
    try:
        os.chdir(extract_dir)
        subprocess.check_call(['tar', '-xzf', tarball_abs])
        subprocess.call(['find', topdir, '-type', 'd', '-empty', '-delete'])
        # hack to preserve these directories
        safe_makedirs(os.path.join(topdir, 'var/lib/osg-ca-certs'))
        safe_makedirs(os.path.join(topdir, 'etc/fetch-crl.d'))
        subprocess.check_call(['tar', '-czf', tarball_base, topdir])
        shutil.copy(tarball_base, tarball_abs)
    finally:
        os.chdir(oldcwd)
        shutil.rmtree(extract_dir)


def make_stage2_tarball(stage_dir, packages, tarball, patch_dirs, post_scripts_dir, osgver, dver, basearch, relnum=0, prerelease=False):
    def _statusmsg(msg):
        statusmsg("[%r,%r]: %s" % (dver, basearch, msg))

    _statusmsg("Making stage2 tarball in %r" % stage_dir)

    stage_dir_abs = os.path.abspath(stage_dir)
    try:
        _statusmsg("Installing packages %r" % packages)
        install_packages(stage_dir_abs, packages, osgver, dver, basearch, prerelease=prerelease)

        if patch_dirs is not None:
            if type(patch_dirs) is types.StringType:
                patch_dirs = [patch_dirs]

            _statusmsg("Patching packages using %r" % patch_dirs)
            for patch_dir in patch_dirs:
                patch_installed_packages(stage_dir_abs=stage_dir_abs, patch_dir=patch_dir, dver=dver, osgver=osgver)

        _statusmsg("Fixing gsissh config dir (if needed)")
        fix_gsissh_config_dir(stage_dir_abs)

        _statusmsg("Fixing osg-version")
        fix_osg_version(stage_dir_abs, relnum)

        _statusmsg("Fixing broken cog-axis jar symlink")
        fix_broken_cog_axis_symlink(stage_dir_abs)

        _statusmsg("Fixing broken /etc/alternatives symlinks")
        fix_alternatives_symlinks(stage_dir_abs)

        _statusmsg("Creating fetch-crl symlinks")
        create_fetch_crl_symlinks(stage_dir_abs, dver)

        _statusmsg("Copying OSG scripts from %r" % post_scripts_dir)
        copy_osg_post_scripts(stage_dir_abs, post_scripts_dir, dver, basearch)

        _statusmsg("Fixing permissions")
        fix_permissions(stage_dir_abs)

        _statusmsg("Creating tarball %r" % tarball)
        tar_stage_dir(stage_dir_abs, tarball)

        _statusmsg("Removing empty dirs from tarball")
        remove_empty_dirs_from_tarball(tarball, os.path.basename(stage_dir))

        return True
    except Error as err:
        errormsg(str(err))
