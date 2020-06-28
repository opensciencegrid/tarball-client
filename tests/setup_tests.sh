#!/bin/sh -xe

# This script starts docker and systemd (if el7)

pkg_name=tarball-client

 # Run tests in Container
if [ "$OS_VERSION" = "6" ]; then

sudo docker run --privileged --rm=true -v `pwd`:/${pkg_name}:rw ${OS_TYPE}:${OS_TYPE}${OS_VERSION} /bin/bash -c "bash -xe /${pkg_name}/tests/test_inside_docker.sh ${OS_VERSION} ${OSG_VERSION}"

elif [ "$OS_VERSION" -gt 6 ]; then

docker run --privileged -d -ti -e "container=docker"  -v /sys/fs/cgroup:/sys/fs/cgroup -v `pwd`:/${pkg_name}:rw  ${OS_TYPE}:${OS_TYPE}${OS_VERSION}   /usr/sbin/init
DOCKER_CONTAINER_ID=$(docker ps | grep ${OS_TYPE} | awk '{print $1}')
docker logs $DOCKER_CONTAINER_ID
docker exec -ti $DOCKER_CONTAINER_ID /bin/bash -xec "bash -xe /${pkg_name}/tests/test_inside_docker.sh ${OS_VERSION} ${OSG_VERSION}"
docker ps -a
docker stop $DOCKER_CONTAINER_ID
docker rm -v $DOCKER_CONTAINER_ID

fi



