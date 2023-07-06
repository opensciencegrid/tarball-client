from __future__ import print_function
import errno
import os
import subprocess
import sys


class Error(Exception): pass

def statusmsg(*args):
    if sys.stdout.isatty():
        print("\x1b[35;1m>>> ", " ".join(args), "\x1b[0m")
    else:
        print(">>> ".join(args))


def errormsg(*args):
    if sys.stdout.isatty():
        print("\x1b[31;1m*** ", " ".join(args), "\x1b[0m")
    else:
        print("*** ".join(args))


def safe_makedirs(path, mode=511):
    try:
        os.makedirs(path, mode)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def safe_symlink(src, dst):
    try:
        os.symlink(src, dst)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def to_str(strlike, encoding="latin-1", errors="backslashescape"):
    if not isinstance(strlike, str):
        if str is bytes:
            return strlike.encode(encoding, errors)
        else:
            return strlike.decode(encoding, errors)
    else:
        return strlike


def to_bytes(strlike, encoding="latin-1", errors="backslashescape"):
    if not isinstance(strlike, bytes):
        return strlike.encode(encoding, errors)
    else:
        return strlike


class MountProcFS(object):
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.proc_dir = os.path.join(root_dir, 'proc')

    def __enter__(self):
        safe_makedirs(self.proc_dir)
        subprocess.check_call(['mount', '-t', 'proc', 'proc', self.proc_dir])

    def __exit__(self, exc_type, exc_value, traceback):
        subprocess.call(['umount', self.proc_dir])


VALID_DVERS        = ["el6", "el7", "el8", "el9"]
VALID_BASEARCHES   = ["x86_64"]
DEFAULT_BASEARCH   = "x86_64"

assert DEFAULT_BASEARCH in VALID_BASEARCHES

