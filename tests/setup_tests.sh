#!/bin/sh -xe

# This script starts docker and systemd (if el7)

pkg_name=tarball-client

 # Run tests in Container
if [ "$OS_VERSION" = "6" ]; then

sudo docker run --privileged --rm=true -v `pwd`:/${pkg_name}:rw ${OS_TYPE}:${OS_TYPE}${OS_VERSION} /bin/bash -c "bash -xe /${pkg_name}/tests/test_inside_docker.sh ${OS_VERSION} ${OSG_VERSION}"

elif [ "$OS_VERSION" = "7" ]; then

docker run --privileged -d -ti -e "container=docker"  -v /sys/fs/cgroup:/sys/fs/cgroup -v `pwd`:/${pkg_name}:rw  ${OS_TYPE}:${OS_TYPE}${OS_VERSION}   /usr/sbin/init
DOCKER_CONTAINER_ID=$(docker ps | grep ${OS_TYPE} | awk '{print $1}')
docker logs $DOCKER_CONTAINER_ID
docker exec -ti $DOCKER_CONTAINER_ID /bin/bash -c "bash -xe /${pkg_name}/tests/test_inside_docker.sh ${OS_VERSION} ${OSG_VERSION};
  echo -ne \"------\nEND HTCONDOR-CE TESTS\n------\nSystemD Units:\n------\n\"; 
  systemctl --no-pager --all --full status;
  echo -ne \"------\nJournalD Logs:\n------\n\" ;
  journalctl --catalog --all --full --no-pager;"
docker ps -a
docker stop $DOCKER_CONTAINER_ID
docker rm -v $DOCKER_CONTAINER_ID

fi



