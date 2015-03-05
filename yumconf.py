import glob
import os
import shutil
import subprocess
import tempfile
import types
import ConfigParser

from common import VALID_BASEARCHES, VALID_DVERS, Error

PACKAGES_FROM_TESTING = {'3.1': [], '3.2': []}
PACKAGES_FROM_MINEFIELD = {'3.1': [], '3.2': []}


class YumInstallError(Error):
    def __init__(self, packages, rootdir, err):
        super(self.__class__, self).__init__("Could not install %r into %r (yum process returned %d)" % (packages, rootdir, err))
class YumDownloaderError(Error):
    def __init__(self, packages, rootdir, err, resolve=False):
        super(self.__class__, self).__init__("Could not download %r into %r (resolve=%s) (yumdownloader process returned %d)" % (packages, rootdir, resolve, err))

class YumInstaller(object):
    # To avoid OS repos getting mixed in, we have to do --disablerepo=* first.
    # This means 'enabled' lines in the configs we make would not get used,
    # so we have to --enablerepo them ourselves.
    repo_args = ["--disablerepo=*",
                 "--enablerepo=osg-release-build"]

    def __init__(self, osgver, dver, basearch, prerelease=False):
        if not dver in VALID_DVERS:
            raise ValueError('Invalid dver, should be in {0}'.format(VALID_DVERS))
        if not basearch in VALID_BASEARCHES:
            raise ValueError('Invalid basearch, should be in {0}'.format(VALID_BASEARCHES))

        self.repo_args = list(YumInstaller.repo_args)

        self.packages_from_testing = None
        self.packages_from_minefield = None

        if prerelease:
            self.repo_args.append("--enablerepo=osg-prerelease-for-tarball")
        if PACKAGES_FROM_TESTING[osgver]:
            self.repo_args.append("--enablerepo=osg-testing-limited")
            self.packages_from_testing = PACKAGES_FROM_TESTING[osgver]
        if PACKAGES_FROM_MINEFIELD[osgver]:
            self.repo_args.append("--enablerepo=osg-minefield-limited")
            self.packages_from_minefield = PACKAGES_FROM_MINEFIELD[osgver]

        self.osgver = osgver
        self.dver = dver
        self.basearch = basearch

        self.config = ConfigParser.RawConfigParser()
        self._set_main()
        self._add_repos()


    def __enter__(self):
        self.conf_file = tempfile.NamedTemporaryFile(suffix='.conf')
        self._write_config(self.conf_file.file)
        return self


    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.conf_file.close()
        except (AttributeError, NameError):
            pass


    def _set_main(self):
        self.config.read(['/etc/yum.conf'])
        self.config.remove_option('main', 'distroverpkg')
        self.config.set('main', 'plugins', '1')


    def _add_repo(self, name, osglevel, priority, includes=None):
        kojitag = 'osg-{self.osgver}-{self.dver}-{osglevel}'.format(**locals())
        self.config.add_section(name)
        section = dict(
            name='{kojitag} ({self.basearch})',
            baseurl='http://koji-hub.batlab.org/mnt/koji/repos/{kojitag}/latest/{self.basearch}/',
            failovermethod='priority',
            gpgcheck='0',
            priority=str(priority))

        for key, value in section.iteritems():
            self.config.set(name, key, value.format(**locals()))

        if includes:
            self.config.set(name, 'includepkgs', ' '.join(includes))


    def _add_repos(self):
        # prerelease needs to have better priority than release-build to
        # properly handle the edge case where release-build has a package of
        # higher version than prerelease This popped up during the switch to
        # 3.2, when the release repos for 3.2 were empty so release-build was
        # filled with EPEL packages instead -- some of which were higher
        # version than what was in prerelease.
        self._add_repo('osg-release-build', 'release-build', 98)
        self._add_repo('osg-testing-limited', 'testing', 98, self.packages_from_testing)
        self._add_repo('osg-minefield-limited', 'development', 98, self.packages_from_minefield)
        self._add_repo('osg-prerelease-for-tarball', 'prerelease', 97)



    def _write_config(self, dest_file):
        close_dest_fileobj_at_end = False
        if type(dest_file) is types.StringType:
            dest_fileobj = open(dest_file, 'w')
            close_dest_fileobj_at_end = True
        elif type(dest_file) is types.IntType:
            dest_fileobj = os.fdopen(dest_file, 'w')
        elif type(dest_file) is types.FileType:
            dest_fileobj = dest_file
        else:
            raise TypeError("dest_file is not something that can be used as a file"
                " (must be a path, a file descriptor, or a file object)")

        self.config.write(dest_fileobj)
        dest_fileobj.flush()
        if close_dest_fileobj_at_end:
            dest_fileobj.close()


    def yum_clean(self):
        args = ["-c", self.conf_file.name, "--enablerepo=*"]
        with open(os.devnull, 'w') as fnull:
            subprocess.call(["yum", "clean", "all"] + args, stdout=fnull)
            subprocess.call(["yum", "clean", "expire-cache"] + args, stdout=fnull)



    def repoquery(self, *args):
        # Correct someone passing a list of strings instead of just the strings
        if type(args[0]) is list or type(args[0]) is tuple:
            args = list(args[0])
        cmd = ["repoquery",
               "-c", self.conf_file.name,
               "--plugins"] + \
               self.repo_args
        cmd += args
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        output = proc.communicate()[0]
        retcode = proc.returncode

        if not retcode:
            return output
        else:
            raise subprocess.CalledProcessError("repoquery failed")


    def query_osg_version(self):
        query = self.repoquery("osg-version", "--queryformat=%{VERSION}").rstrip()
        return query


    def install(self, installroot, packages):
        if not installroot:
            raise ValueError("'installroot' empty")
        if not packages:
            raise ValueError("'packages' empty")
        if type(packages) is types.StringType:
            packages = [packages]

        cmd = ["yum", "install",
               "-y",
               "--installroot", installroot,
               "-c", self.conf_file.name,
               "-d1",
               "--nogpgcheck"] + \
              self.repo_args
        cmd += packages
        env = os.environ.copy()
        env.update({'LANG': 'C', 'LC_ALL': 'C'})
        err = subprocess.call(cmd, env=env)
        if err:
            raise YumInstallError(packages, installroot, err)


    def force_install(self, installroot, packages, resolve=False, noscripts=False):
        if not installroot:
            raise ValueError("'installroot' empty")
        if not packages:
            raise ValueError("'packages' empty")
        if type(packages) is types.StringType:
            packages = [packages]

        rpm_dir = tempfile.mkdtemp(suffix='.force-install')
        try:
            cmd = ["yumdownloader",
                   "--destdir", rpm_dir,
                   "--installroot", installroot,
                   "-c", self.conf_file.name,
                   "-d1",
                   "--nogpgcheck"] + \
                  self.repo_args
            if resolve:
                cmd.append('--resolve')
            cmd += packages
            err = subprocess.call(cmd)
            if err:
                raise YumDownloaderError(packages, installroot, err, resolve)
            rpms = glob.glob(os.path.join(rpm_dir, "*.rpm"))
            cmd = ["rpm",
                   "--install",
                   "--verbose",
                   "--force",
                   "--nodeps",
                   "--root", installroot]
            if noscripts:
                cmd.append('--noscripts')
            cmd += rpms
            env = os.environ.copy()
            env.update({'LANG': 'C', 'LC_ALL': 'C'})
            err = subprocess.call(cmd, env=env)
            if err:
                raise YumInstallError(packages, installroot, err)
        finally:
            shutil.rmtree(rpm_dir, ignore_errors=True)
