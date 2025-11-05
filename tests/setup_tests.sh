#!/bin/sh -xe

pkg_name=tarball-client
image=
case "${OS_TYPE}${OS_VERSION}" in
    almalinux8) image=almalinux:8 ;;
    almalinux9) image=almalinux:9 ;;
    almalinux10) image=almalinux:10 ;;
    *) echo >&2 "${OS_TYPE}${OS_VERSION} not supported"; exit 1 ;;
esac

 # Run tests in Container
docker run --privileged --rm -v `pwd`:/${pkg_name}:rw "$image" /bin/bash -c "bash -xe /${pkg_name}/tests/test_inside_docker.sh ${OS_VERSION} ${OSG_VERSION}"
