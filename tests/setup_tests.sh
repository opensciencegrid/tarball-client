#!/bin/sh -xe

pkg_name=tarball-client
image=
case "${OS_TYPE}${OS_VERSION}" in
    centos7) image=centos:centos7 ;;
    centos8) image=quay.io/centos/centos:stream8 ;;
    *) echo >&2 "${OS_TYPE}${OS_VERSION} not supported"; exit 1 ;;
esac

 # Run tests in Container
docker run --privileged --rm -v `pwd`:/${pkg_name}:rw "$image" /bin/bash -c "bash -xe /${pkg_name}/tests/test_inside_docker.sh ${OS_VERSION} ${OSG_VERSION}"
