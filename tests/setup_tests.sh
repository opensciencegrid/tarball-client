#!/bin/sh -xe

pkg_name=tarball-client

 # Run tests in Container
if [ "$OS_VERSION" = "6" ]; then
    sudo docker run --privileged --rm -v `pwd`:/${pkg_name}:rw ${OS_TYPE}:${OS_TYPE}${OS_VERSION} /bin/bash -c "bash -xe /${pkg_name}/tests/test_inside_docker.sh ${OS_VERSION} ${OSG_VERSION}"
else
    docker run --privileged --rm -v `pwd`:/${pkg_name}:rw ${OS_TYPE}:${OS_TYPE}${OS_VERSION} /bin/bash -c "bash -xe /${pkg_name}/tests/test_inside_docker.sh ${OS_VERSION} ${OSG_VERSION}"
fi
