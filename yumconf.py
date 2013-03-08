#!/usr/bin/env python
import glob
import re
import os
import shutil
import subprocess
import sys
import types
import ConfigParser


def write_yum_config(dest_file, dver, basearch):
    close_dest_fileobj_at_end = False
    if type(dest_file) is types.StringType:
        dest_fileobj = open(dest_file, 'w')
        close_dest_fileobj_at_end = True
    elif type(dest_file) is types.IntType:
        dest_fileobj = os.fdopen(dest_file, 'w')
    elif type(dest_file) is types.FileType:
        dest_fileobj = dest_file
    else:
        raise TypeError('dest_file')

    assert(type(dest_fileobj) is types.FileType)

    try:
        config = ConfigParser.RawConfigParser()
        config.read(['/etc/yum.conf'])
        config.remove_option('main', 'distroverpkg')

        if not dver in ['el5', 'el6']:
            raise ValueError('Invalid dver, should be el5 or el6')
        if not basearch in ['i386', 'x86_64']:
            raise ValueError('Invalid basearch, should be i386 or x86_64')

        sec = 'osg-release-build'
        config.add_section(sec)
        config.set(sec, 'name', '%s-osg-release-build latest (%s)' % (dver, basearch))
        config.set(sec, 'baseurl', 'http://koji-hub.batlab.org/mnt/koji/repos/%s-osg-release-build/latest/%s/' % (dver, basearch))
        config.set(sec, 'failovermethod', 'priority')
        config.set(sec, 'priority', '98')
        config.set(sec, 'enabled', '1')
        config.set(sec, 'gpgcheck', '0')

        config.write(dest_fileobj)
        dest_fileobj.flush()
    finally:
        if close_dest_fileobj_at_end:
            dest_fileobj.close()


def main(argv):


    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

