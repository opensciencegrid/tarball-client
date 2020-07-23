FROM centos:8

RUN yum install -y tar yum-utils patch && rm -rf /var/cache/yum/*

