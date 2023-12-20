#!/bin/bash -xe

OS_VERSION=$1
OSG_VERSION=$2

ls -l /home

# Clean the yum cache
yum -y clean all

# First, install all the needed packages.
rpm -U https://dl.fedoraproject.org/pub/epel/epel-release-latest-${OS_VERSION}.noarch.rpm

# Broken mirror?
echo "exclude=mirror.beyondhosting.net" >> /etc/yum/pluginconf.d/fastestmirror.conf

yum -y install /bin/mount patch python3 yum-utils
if [[ $OS_VERSION -lt 8 ]]; then
    yum -y install yum-plugin-priorities
fi

pushd tarball-client
args=(--version ${OSG_VERSION} --dver el${OS_VERSION} --basearch x86_64)
./make-client-tarball "${args[@]}"
popd

