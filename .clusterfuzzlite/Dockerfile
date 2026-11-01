# ClusterFuzzLite build image for the Atheris fuzzers in fuzz/ (.github/workflows/cflite.yml). Pinned by digest;
# Dependabot (docker, /.clusterfuzzlite) proposes updates.
FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:21f6fab17ace4dc76e1c56de91ee95d3d03da021df94b41056ba036f6c6f55e9
COPY . $SRC/netdryrun
WORKDIR $SRC/netdryrun
COPY .clusterfuzzlite/build.sh $SRC/
