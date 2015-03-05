import errno
import os
import subprocess
import sys


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


def mount_proc_in_stage_dir(stage_dir):
    procdir = os.path.join(stage_dir, 'proc')
    safe_makedirs(procdir)
    return subprocess.call(['mount' , '-t', 'proc', 'proc', procdir])


def umount_proc_in_stage_dir(stage_dir):
    procdir = os.path.join(stage_dir, 'proc')
    return subprocess.call(['umount', procdir])


VALID_METAPACKAGES = ["osg-wn-client", "osg-client"]
VALID_DVERS        = ["el5", "el6"]
VALID_BASEARCHES   = ["i386", "x86_64"]

