#!/bin/sh -xe

OS_VERSION=$1
OSG_VERSION=$2

ls -l /home

# Clean the yum cache
yum -y clean all
yum -y clean expire-cache

# First, install all the needed packages.
rpm -Uvh https://dl.fedoraproject.org/pub/epel/epel-release-latest-${OS_VERSION}.noarch.rpm

# Broken mirror?
echo "exclude=mirror.beyondhosting.net" >> /etc/yum/pluginconf.d/fastestmirror.conf

yum -y install yum-plugin-priorities yum-utils

pushd tarball-client
./make-client-tarball --osgver ${OSG_VERSION} --dver el${OS_VERSION} --basearch x86_64 --bundle osg-wn-client-${OSG_VERSION}
popd

