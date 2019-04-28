#!/usr/bin/python2
# -*- coding: utf-8 -*-
"""Update a tarball-based worker node client installation from a hosted CE.
Requires Python 2.7

"""

from __future__ import print_function
from six.moves import shlex_quote
from six.moves import urllib
import argparse
import contextlib
import glob
import logging
import os
import shutil
import subprocess
import sys
import tempfile


devnull = open(os.devnull, "w+")
log = logging.getLogger(__name__)


class Error(Exception): pass


# adapted from osgbuild/fetch_sources; thanks Carl
def download_to_file(uri, outfile):
    try:
        handle = urllib.request.urlopen(uri)
    except urllib.error.URLError as err:
        raise Error("Unable to download %s: %s" % (uri, err))

    try:
        with open(outfile, 'wb') as desthandle:
            chunksize = 64 * 1024
            chunk = handle.read(chunksize)
            while chunk:
                desthandle.write(chunk)
                chunk = handle.read(chunksize)
    except EnvironmentError as err:
        raise Error("Unable to save downloaded file to %s: %s" % (outfile, err))


def cas_exist(cert_dir):
    """Return True if we already have CAs in cert_dir (and do not need to run
    osg-ca-manage setupCA)

    """
    cas = glob.glob(os.path.join(cert_dir, '*.0'))
    if cas:
        return True
    else:
        return False


def setup_cas(wn_client, osgrun, cert_dir):
    "Run osg-ca-manage setupCA"

    # Unfortunately, if we specify a location to osg-ca-manage setupCA, it
    # always wants to create a symlink from
    # $OSG_LOCATION/etc/grid-security/certificates to that location.  Since we
    # do not want to mess up the tarball install we're using, we must first
    # save the symlink that's already there, then run osg-ca-manage, then
    # restore it.
    certs_link = os.path.join(wn_client, 'etc/grid-security/certificates')
    certs_link_save = certs_link + '.save'

    # Note that in a proper tarball install, certs_link should already exist
    # but handle its nonexistence gracefully too.
    # Note the need to use 'lexists' since 'exists' returns False if the path
    # is a broken symlink.
    if os.path.lexists(certs_link):
        if os.path.lexists(certs_link_save):
            os.unlink(certs_link_save)
        os.rename(certs_link, certs_link_save)

    # osg-ca-manage always puts the certs into a subdirectory called 'certificates'
    # under the location specified here. So specify the parent of cert_dir as --location.
    command = [osgrun, 'osg-ca-manage']
    command += ['setupCA']
    command += ['--location', os.path.dirname(cert_dir)]
    command += ['--url', 'osg']
    try:
        subprocess.check_call(command)
    finally:
        if os.path.lexists(certs_link_save):
            if os.path.lexists(certs_link):
                os.unlink(certs_link)
            os.rename(certs_link_save, certs_link)


def update_cas(osgrun, cert_dir):
    subprocess.check_call([osgrun, 'osg-ca-manage', '--cert-dir', cert_dir, 'refreshCA'])


def update_crls(osgrun, cert_dir):
    "Run fetch-crl and return a list of non-fatal issues it finds"
    command = [osgrun, 'fetch-crl']
    command += ['--infodir', cert_dir]
    command += ['--out', cert_dir]
    command += ['--quiet']
    command += ['--agingtolerance', '24'] # 24 hours
    command += ['--parallelism', '5']

    output = None
    try:
        output = subprocess.check_output(command, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as err:
        if output and ("CRL verification failed" in output or "Download error" in output):
            # These errors aren't actually fatal; we'll send a less alarming
            # notification about them.
            log.info(output)
        else:
            raise


def rsync_upload(srcdir, destuser, desthost, destdir, ssh_key=None):
    # type: (str, str, str, str, str) -> None
    """Use rsync to upload the contents of a directory to a remote host,
    minimizing the time the remote dir spends in an inconsistent state.
    Requires rsync and ssh shell access on the remote host to do the swapping.

    The parent directories must already exist.
    """
    ssh = ["ssh", "-l", destuser]
    if ssh_key:
        ssh.extend(["-i", ssh_key])
    olddir = "%s~old~" % destdir
    newdir = "%s~new~" % destdir
    srcdir = srcdir.rstrip("/") + "/"  # exactly 1 trailing slash

    if subprocess.check_output(ssh +
            [desthost, "[[ -e %s ]] || echo missing" % shlex_quote(destdir)]).rstrip() == "missing":
        log.info("rsyncing entire WN client to %s:%s", desthost, destdir)
        # If remote dir is missing then just upload and return
        try:
            subprocess.check_call(["rsync", "-e", " ".join(ssh),
                                   "-qa",
                                   srcdir,
                                   "%s:%s" % (desthost, destdir)])
            return
        except EnvironmentError as e:
            raise Error("Error rsyncing to remote host %s:%s: %s" % (desthost, destdir, e))

    # Otherwise, upload to newdir
    try:
        log.info("rsyncing WN client changes to %s:%s", desthost, newdir)
        subprocess.check_call(["rsync", "-e", " ".join(ssh),
                               "-qa",
                               "--link-dest", destdir,
                               "--delete-before",
                               srcdir,
                               "%s:%s" % (desthost, newdir)])
    except EnvironmentError as e:
        raise Error("Error rsyncing to remote host: %s:%s: %s" % (desthost, newdir, e))

    # then rename destdir to olddir and newdir to destdir
    try:
        log.info("Moving %s to %s", newdir, destdir)
        subprocess.check_call(ssh +
            [desthost,
             "rm -rf {0} && "
             "mv {1} {0} && "
             "mv {2} {1}".format(
                shlex_quote(olddir), shlex_quote(destdir), shlex_quote(newdir))])
    except EnvironmentError as e:
        raise Error("Error renaming remote directories: %s" % e)


@contextlib.contextmanager
def working_dir(*args, **kwargs):
    """Resource manager for creating a temporary directory, cd'ing into it,
    and deleting it after completion.

    """
    wd = tempfile.mkdtemp(*args, **kwargs)
    olddir = os.getcwd()
    os.chdir(wd)
    yield wd
    os.chdir(olddir)
    shutil.rmtree(wd)


# Because paths are embedded into the WN-client installation, two copies
# of the client are used: the "deploy" client, which will be rsynced to the
# worker node, and the "fetch" client, which will be used to download CAs
# and CRLs.  The "fetch" client will put the CAs and CRLs into the certificate
# dir of the "deploy" client.

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-url",
                        default="https://repo.opensciencegrid.org/tarball-install/3.4/osg-wn-client-latest.el7.x86_64.tar.gz",
                        help="The URL for the WN tarball file. Default: %(default)s")
    parser.add_argument("--remote-user", default="bosco",
                        help="The remote user to use for rsync and ssh. Default: %(default)s")
    parser.add_argument("--remote-dir", default="/home/bosco/osg-wn-client",
                        help="The remote directory the client will be placed in. Default: %(default)s")
    parser.add_argument("--ssh-key", help="The SSH key to use to log in with. No default.")
    parser.add_argument("remote_host", help="The host to upload the wn client to.")
    args = parser.parse_args()

    # check if rsync is installed and working
    try:
        subprocess.check_call(["rsync", "--version"], stdout=devnull)
    except EnvironmentError as e:
        log.error("Error invoking rsync: %s", e)
        return 1

    with working_dir() as wd:
        try:
            log.info("Downloading WN tarball")
            download_to_file(args.upstream_url, "osg-wn-client.tar.gz")

            os.mkdir("deploy")
            subprocess.check_call(["tar", "-C", "deploy", "-xzf", "osg-wn-client.tar.gz"])
            deploy_client_dir = os.path.join(wd, "deploy/osg-wn-client")
            cert_dir = os.path.join(deploy_client_dir, "etc/grid-security/certificates")

            os.mkdir("fetch")
            subprocess.check_call(["tar", "-C", "fetch", "-xzf", "osg-wn-client.tar.gz"])
            fetch_client_dir = os.path.join(wd, "fetch/osg-wn-client")

            log.info("Setting up tarball dirs")
            subprocess.check_call([os.path.join(deploy_client_dir, "osg/osg-post-install"),
                                   "-f", args.remote_dir])
            subprocess.check_call([os.path.join(fetch_client_dir, "osg/osg-post-install")])
            osgrun = os.path.join(fetch_client_dir, "osgrun")

            log.info("Fetching CAs")
            setup_cas(fetch_client_dir, osgrun, cert_dir)
            log.info("Fetching CRLs")
            update_crls(osgrun, cert_dir)

            log.info("Uploading")
            rsync_upload(deploy_client_dir, args.remote_user, args.remote_host, args.remote_dir, args.ssh_key)
        except Error as e:
            log.error(e)
            return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(format="*** %(message)s", level=logging.INFO)
    sys.exit(main())
