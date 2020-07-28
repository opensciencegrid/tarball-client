tarball-client
==============

`tarball-client` contains tools and supporting files for creating tarballs
(called "bundles") for client software, where the bundles also contain most of
the dependencies required for the software to run. The primary use for these
tools is the OSG Worker Node Client (`osg-wn-client`).


Overview
--------

Bundles are based on RPM installations of software and are dependent on a base
OS install (e.g. `libc`). This means that bundles created for EL6 are not
expected to run on EL7 hosts, or vice versa. However, bundles should contain all
their dependencies that are not expected to be on a base OS install.

Patches are used to replace hard-coded paths in config files and scripts to
depend on the environment variable `$OSG_LOCATION` instead. However, binary
executables with paths baked into them cannot be fixed, since bundles are
created from binary RPMs and no compilation is done.


Usage
-----

Bundle contents are defined in `bundles.ini`. The default bundles are the OSG
worker node clients, based on the `--osgver` flag passed on the command line.

    make-client-tarball --osgver <3.4|3.5> --all

will make the whole set of osg-wn-client (and osg-afs-client) tarballs.

    make-client-tarball --osgver <3.4|3.5> --dver <el6|el7|el8>

will make specific osg-wn-client tarballs.

You can also build a specific bundle by passing `--bundle=<bundle name>`.
In this case, don't pass `--osgver`.

Pass `--version` to set the version of the tarball, e.g. `--version 3.5.21`.
If not present, it will use the version of the `osg-version` RPM or "unknown".


### Building in a VM

**Requirements:**

Tarball builds must be done on an X86\_64 machine running an RPM/YUM-based distribution, e.g. CentOS.
EL8 tarballs must be built on an EL8 or newer distribution to handle a change in RPM format.
In addition, the following utilities must be present:

- find
- patch
- tar
- yumdownloader (from yum-utils)
- yum-plugin-priorities (EL7 hosts only)



**Instructions:**

1.  Clone this repo into `/tmp/tarball-client`.

1.  `cd /tmp/tarball-client`.

1.  Run `make-client-tarball` as above, e.g. with

        ./make-client-tarball --osgver 3.5 --version 3.5.30 --all

    The resulting tarballs will be in the current directory.



### Building in a Container

**Requirements:**

You must have Docker installed on your machine and be a member of the `docker` Unix group.
Podman is currently not supported, since the container needs to be run in privileged mode in order to create chroots.


**Instructions:**

1.  Clone this repo.

1.  Follow above instructions for `make-client-tarball` except run `docker-make-client-tarball` instead.
    For example:

        ./docker-make-client-tarball --osgver 3.5 --version 3.5.30 --all

    The resulting tarballs will be in the current directory.


Mode of Operation
-----------------

`tarball-client` works inside a chroot in two stages. In stage 1, base OS
packages are "fake-installed" into the chroot. These are the packages that are
assumed to already be on the system that the resulting bundle will be run on.
For `osg-wn-client`, the list of packages to install is in `osg-stage1.lst` but
`bundles.ini` may specify a different one.

Once the stage 1 packages are installed into the chroot,
_all of the files from the packages will be deleted_.
However, the entries in the YUM and RPM databases will remain. That means that
YUM will consider those dependencies to be satisfied when installing packages
later, even though the files are not there. This is what is meant by
"fake-install."

Multiple things happen in stage 2:

-   The packages we want to keep in the bundle are installed. The list of packages to install is defined in `bundles.ini`.
-   Patches may be applied to the files in the bundle. The directories which will be searched for patches are defined in `bundles.ini`. Patches will be applied in base filename order, _ignoring their directories_.
-   Various other fixes are applied. These fixes are hardcoded in `stage2.py`.
-   The tarballs are created.


Files
-----


### bundles.ini

The definitions for each bundle in Python SafeConfigParser format. Each bundle is in its own section.

1.  Attributes

    -   paramsets:

        Space-seperated "dver,arch" pairs that define what distro versions and
        architectures using `--all` will build for. For example, `el6,x86_64
        el7,x86_64` will build for EL6 and EL7 on X86\_64 only.

    -   patchdirs:

        The directories to apply patches from. `dver` and `basearch` are
        available for substitution, where `dver` is `el6` or `el7`, and
        `basearch` is `i386` or `x86_64`.

    -   dirname:

        The name of the top-level directory inside the tarball.

    -   tarballname:

        The name pattern for the tarball. `version`, `relnum`, `dver`, and
        `basearch` are available for substitution.

    -   packages:

        The RPM packages that should be installed in stage 2. These are passed
        to the `yum install` command; they may be groups using the `@groupname`
        syntax.

    -   repofile:

        The YUM repo definition file _templates_ that stage 1 and stage 2
        packages will be installed from. These look like files in
        `/etc/yum.repos.d` but `dver` and `basearch` are available for
        substitution within these files.

    -   versionrpm (optional):

        The RPM whose version will be used for the `version` variable in the
        tarball name. If missing, you must specify `--version` on the command
        line.

    -   stage1file:

        File containing the list of packages to install for stage 1. Again, YUM
        will consider these packages to be installed during the stage 2 install,
        but the files within them will not exist.


### envsetup.py

Module to write the template `setup.sh` and `setup.csh` files.


### make-client-tarball

The script to be executed by the user to create the tarball.


### stage1.py

Code to do the stage 1 installation.

### stage2.py

Code to do the stage 2 installation, subsequent patching and fixes, and creation of the tarball.

### yumconf.py

Defines the `YumInstaller` class which deals with setting up YUM repo definition
files and running the YUM commands to do the installations.
