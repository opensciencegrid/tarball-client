FROM almalinux:8

RUN dnf install -y zlib tar yum-utils patch && dnf clean all

