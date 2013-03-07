#!/usr/bin/env python
import glob
import re
import os
import shutil
import subprocess
import sys
import tempfile


class Error(Exception):
    """Class for expected exceptions

    Contains 'longtext' field for printing a description of the problem

    """
    def __init__(self, message, longtext=""):
        Exception.__init__(self, message)
        self.longtext = longtext

    def __str__(self):
        str = "Error: %s" % self.message
        if self.longtext:
            str += "\n" + self.longtext


def transform_file(input_file_path, output_file_path, transform_function, extra_arg):
    input_file_fh = open(input_file_path, "r")
    try:
        output_file_fh = open(output_file_path, "w")
        try:
            for input_line in input_file_fh:
                output_line = transform_function(input_line, extra_arg)
                print >> output_file_fh, output_line
        finally:
            output_file_fh.close()
    finally:
        input_file_fh.close()


def _fix_osg_location_transform_function(input_line, osg_location):
    return re.sub(r'@@OSG_LOCATION@@', osg_location, input_line)


def fix_osg_location_in_setup(osg_location=None):
    if osg_location is None:
        osg_location = os.path.dirname(sys.argv[0])
    elif not os.path.isdir(osg_location):
        raise Error("OSG location (%r) not found" % osg_location, longtext="""\
Please check that the directory %r is where you unpacked the osg client or wn-client tarball.""" % osg_location)

    # TODO EC
    for shell in 'sh', 'csh':
        setup_file = "setup." + shell
        setup_path = os.path.join(osg_location, setup_file)

        if not os.path.exists(setup_path):
            raise Error("%r not found at %r" % (setup_file, setup_path), longtext="""\
Please check that the directory %r is where you unpacked the osg client or wn-client tarball.""" % osg_location)

        setup_temp_path = tempfile.mktemp()
        transform_file(setup_path, setup_temp_path, _fix_osg_location_transform_function, osg_location)
        # doing copy followed by remove because I DON'T want to keep the tempfile's permissions
        shutil.copyfile(setup_temp_path, setup_path)
        os.remove(setup_temp_path)




def main(argv):
    try:
        pass
    except Error, err:
        print str(err)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

