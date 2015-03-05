import errno
import os
import subprocess
import sys


class Error(Exception): pass

def statusmsg(*args):
    if sys.stdout.isatty():
        print "\x1b[35;1m>>> ", " ".join(args), "\x1b[0m"
    else:
        print ">>> ".join(args)


def errormsg(*args):
    if sys.stdout.isatty():
        print "\x1b[31;1m*** ", " ".join(args), "\x1b[0m"
    else:
        print "*** ".join(args)


def safe_makedirs(path, mode=511):
    try:
        os.makedirs(path, mode)
    except OSError as e:
        if e.errno == errno.EEXIST:
            pass


def safe_symlink(src, dst):
    try:
        os.symlink(src, dst)
    except OSError as e:
        if e.errno == errno.EEXIST:
            pass


class MountProcFS(object):
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.proc_dir = os.path.join(root_dir, 'proc')

    def __enter__(self):
        safe_makedirs(self.proc_dir)
        subprocess.check_call(['mount', '-t', 'proc', 'proc', self.proc_dir])

    def __exit__(self, exc_type, exc_value, traceback):
        subprocess.call(['umount', self.proc_dir])


VALID_METAPACKAGES = ["osg-wn-client", "osg-client"]
VALID_DVERS        = ["el5", "el6"]
VALID_BASEARCHES   = ["i386", "x86_64"]

