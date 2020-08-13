FROM centos:8

RUN yum install -y zlib tar yum-utils patch && rm -rf /var/cache/yum/*

