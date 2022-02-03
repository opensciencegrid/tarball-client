FROM quay.io/centos/centos:stream8

RUN yum install -y zlib tar yum-utils patch && rm -rf /var/cache/yum/*

