import glob
import os
import shutil
import subprocess
import tempfile
import types
import ConfigParser


PACKAGES_FROM_TESTING = {'3.1': [], '3.2': []}
PACKAGES_FROM_MINEFIELD = {'3.1': [], '3.2': []}


class YumConfig(object):
    # To avoid OS repos getting mixed in, we have to do --disablerepo=* first.
    # This means 'enabled' lines in the configs we make would not get used,
    # so we have to --enablerepo them ourselves.
    repo_args = ["--disablerepo=*",
                 "--enablerepo=osg-release-build"]

    def __init__(self, osgver, dver, basearch, prerelease=False):
        if not dver in ['el5', 'el6']:
            raise ValueError('Invalid dver, should be el5 or el6')
        if not basearch in ['i386', 'x86_64']:
            raise ValueError('Invalid basearch, should be i386 or x86_64')
        self.repo_args = list(YumConfig.repo_args)
        if prerelease:
            self.repo_args.append("--enablerepo=osg-prerelease-for-tarball")
        if PACKAGES_FROM_TESTING[osgver]:
            self.repo_args.append("--enablerepo=osg-testing-limited")
        if PACKAGES_FROM_MINEFIELD[osgver]:
            self.repo_args.append("--enablerepo=osg-minefield-limited")
        self.config = ConfigParser.RawConfigParser()
        self.set_main()
        self.add_repos(osgver, dver, basearch)


    def __enter__(self):
        self.conf_file = tempfile.NamedTemporaryFile(suffix='.conf')
        self.write_config(self.conf_file.file)
        return self


    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.conf_file.close()
        except (AttributeError, NameError):
            pass


    def set_main(self):
        self.config.read(['/etc/yum.conf'])
        self.config.remove_option('main', 'distroverpkg')
        self.config.set('main', 'plugins', '1')


    def add_repos(self, osgver, dver, basearch):
        sec = 'osg-release-build'
        self.config.add_section(sec)
        self.config.set(sec, 'name', 'osg-%s-%s-release-build latest (%s)' % (osgver, dver, basearch))
        self.config.set(sec, 'baseurl', 'http://koji-hub.batlab.org/mnt/koji/repos/osg-%s-%s-release-build/latest/%s/' % (osgver, dver, basearch))
        self.config.set(sec, 'failovermethod', 'priority')
        self.config.set(sec, 'priority', '98')
        self.config.set(sec, 'gpgcheck', '0')

        sec2 = 'osg-testing-limited'
        self.config.add_section(sec2)
        self.config.set(sec2, 'name', 'osg-%s-%s-testing latest (%s) (limited)' % (osgver, dver, basearch))
        self.config.set(sec2, 'baseurl', 'http://repo.grid.iu.edu/osg/%s/%s/testing/%s' % (osgver, dver, basearch))
        self.config.set(sec2, 'failovermethod', 'priority')
        self.config.set(sec2, 'priority', '96')
        self.config.set(sec2, 'gpgcheck', '0')
        if PACKAGES_FROM_TESTING[osgver]:
            self.config.set(sec2, 'includepkgs', " ".join(PACKAGES_FROM_TESTING[osgver]))

        sec3 = 'osg-minefield-limited'
        self.config.add_section(sec3)
        self.config.set(sec3, 'name', 'osg-%s-%s-development latest (%s) (limited)' % (osgver, dver, basearch))
        self.config.set(sec3, 'baseurl', 'http://koji-hub.batlab.org/mnt/koji/repos/osg-%s-%s-development/latest/%s/' % (osgver, dver, basearch))
        self.config.set(sec3, 'failovermethod', 'priority')
        self.config.set(sec3, 'priority', '95')
        self.config.set(sec3, 'gpgcheck', '0')
        if PACKAGES_FROM_MINEFIELD[osgver]:
            self.config.set(sec3, 'includepkgs', " ".join(PACKAGES_FROM_MINEFIELD[osgver]))

        # osg-prerelease-for-tarball needs to have better priority than
        # osg-release-build to properly handle the edge case where
        # osg-release-build has a package of higher version than osg-prerelease
        # This popped up during the switch to 3.2, when the osg-release repos
        # for 3.2 were empty so osg-release-build was filled with EPEL packages
        # instead -- some of which were higher version than what was in
        # prerelease.
        sec4 = 'osg-prerelease-for-tarball'
        self.config.add_section(sec4)
        self.config.set(sec4, 'name', 'osg-%s-%s-prerelease (%s)' % (osgver, dver, basearch))
        self.config.set(sec4, 'baseurl', 'http://koji-hub.batlab.org/mnt/koji/repos/osg-%s-%s-prerelease/latest/%s/' % (osgver, dver, basearch))
        self.config.set(sec4, 'failovermethod', 'priority')
        self.config.set(sec4, 'priority', '97')
        self.config.set(sec4, 'gpgcheck', '0')


    def write_config(self, dest_file):
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
                "(must be a path, a file descriptor, or a file object)")

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
        if len(args) == 1 and type(args[0]) is list or type(args[0]) is tuple:
            args = args[0]
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
        return subprocess.call(cmd, env=env)


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
            # FIXME Better EC and exceptions
            err = subprocess.call(cmd)
            if err:
                return err
            rpms = glob.glob(os.path.join(rpm_dir, "*.rpm"))
            cmd2 = ["rpm",
                    "--install",
                    "--verbose",
                    "--force",
                    "--nodeps",
                    "--root", installroot]
            if noscripts:
                cmd2.append('--noscripts')
            cmd2 += rpms
            env = os.environ.copy()
            env.update({'LANG': 'C', 'LC_ALL': 'C'})
            return subprocess.call(cmd2, env=env)
        finally:
            shutil.rmtree(rpm_dir, ignore_errors=True)
