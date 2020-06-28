from __future__ import absolute_import
import glob
import os
import shutil
import subprocess
import tempfile
import types
try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser

from common import VALID_BASEARCHES, VALID_DVERS, Error, to_str, to_bytes

# Edit repos/osg-3.?.repo.in to define which packages to use from
# testing/minefield (via the 'includepkgs' lines) and whether to use
# testing/minefield at all (via the 'enabled' lines)

class YumInstallError(Error):
    def __init__(self, packages, rootdir, err):
        super(self.__class__, self).__init__("Could not install %r into %r (yum process returned %d)" % (packages, rootdir, err))
class YumDownloaderError(Error):
    def __init__(self, packages, rootdir, err, resolve=False):
        super(self.__class__, self).__init__("Could not download %r into %r (resolve=%s) (yumdownloader process returned %d)" % (packages, rootdir, resolve, err))

class YumInstaller(object):
    def __init__(self, templatefile, dver, basearch, extra_repos=None):
        if not dver in VALID_DVERS:
            raise ValueError('Invalid dver, should be in {0}'.format(VALID_DVERS))
        if not basearch in VALID_BASEARCHES:
            raise ValueError('Invalid basearch, should be in {0}'.format(VALID_BASEARCHES))

        self.dver = dver
        self.basearch = basearch
        self.templatefile = templatefile

        self.config = ConfigParser.RawConfigParser()
        self._set_main()
        self._add_repos()

        self.repo_args = self._get_repo_args()

        if extra_repos:
            self.repo_args.extend(["--enablerepo=" + x for x in extra_repos])

        if int(dver[2:]) >= 8:
            self.repo_args.append("--setopt=install_weak_deps=False")

    def __enter__(self):
        self.conf_file = tempfile.NamedTemporaryFile(suffix='.conf')
        self._write_config(self.conf_file.file)
        return self


    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.conf_file.close()
        except (AttributeError, NameError):
            pass


    def _get_repo_args(self):
        # To avoid OS repos getting mixed in, we have to do --disablerepo=* first.
        # This means 'enabled' lines in the configs we make would not get used,
        # so we have to --enablerepo them ourselves.
        repo_args = ['--disablerepo=*']
        for sec in self.config.sections():
            if self.config.has_option(sec, 'enabled') and self.config.getboolean(sec, 'enabled'):
                repo_args.append('--enablerepo=' + sec)
        return repo_args


    def _set_main(self):
        self.config.read(['/etc/yum.conf'])
        self.config.remove_option('main', 'distroverpkg')
        self.config.set('main', 'plugins', '1')


    def _add_repos(self):
        self.repotemplate = ConfigParser.SafeConfigParser({'dver': self.dver, 'basearch': self.basearch})

        with open(self.templatefile, 'r') as templatefp:
            self.repotemplate.readfp(templatefp)

        for sec in self.repotemplate.sections():
            if not self.config.has_section(sec):
                self.config.add_section(sec)
            for key, value in self.repotemplate.items(sec):
                # don't want the arguments copied to every section
                if key == 'basearch' or key == 'dver': continue
                self.config.set(sec, key, value)


    def _write_config(self, dest_file):
        self.config.write(dest_file)
        dest_file.flush()


    def yum_clean(self):
        args = ["-c", self.conf_file.name, "--enablerepo=*"]
        with open(os.devnull, 'wb') as fnull:
            subprocess.call(["yum", "clean", "all"] + args, stdout=fnull)



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
        output = to_str(proc.communicate()[0])
        retcode = proc.returncode

        if not retcode:
            return output
        else:
            raise subprocess.CalledProcessError("repoquery failed")


    def install(self, installroot, packages):
        if not installroot:
            raise ValueError("'installroot' empty")
        if not packages:
            raise ValueError("'packages' empty")
        if type(packages) in (str, bytes):
            packages = [packages]

        cmd = ["yum", "install",
               "-y",
               "--installroot", installroot,
               "-c", self.conf_file.name,
               "-d1",
               "--enableplugin=priorities",
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
        if type(packages) in (str, bytes):
            packages = [packages]

        rpm_dir = tempfile.mkdtemp(suffix='.force-install')
        try:
            cmd = ["yumdownloader",
                   "--destdir", rpm_dir,
                   "--installroot", installroot,
                   "-c", self.conf_file.name,
                   "-d1",
                   "--enableplugin=priorities",
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
