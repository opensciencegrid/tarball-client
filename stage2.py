#!/usr/bin/env python
import glob
import re
import os
import shutil
import subprocess
import sys

def verify_stage1(stage1_dir):
    """Verify the stage1_dir is usable as a base to install the rest of the
    software into.

    """
    if not os.path.isdir(stage1_dir):
        print "Error: stage 1 directory (%r) missing" % stage1_dir
        return False

    rpmdb_dir = os.path.join(stage1_dir, "var/lib/rpm")
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
            err = subprocess.call(["rpm", "-q", "--root", os.path.realpath(stage1_dir), pkg], stdout=fnull)
            if err:
                print "Error: package entry for %r not in rpmdb" % pkg
                return False
    finally:
        fnull.close()

    if len(glob.glob(os.path.join(stage1_dir, "*"))) > 1:
        print "Error: unexpected files or directories found under stage 1 directory (%r)" % stage1_dir
        return False

    return True



def main(argv):
    # EXECUTION BEGINS HERE
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
