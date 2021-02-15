#!/bin/bash

set -o errexit
#set -x

cd "$(dirname $0)"
BIN_DIR="${PWD}"
PROG_DIR="${BIN_DIR%/*}"
TOP_DIR="${PROG_DIR%/*}"

cd ${TOP_DIR}/env
source ./bin/activate
export PYTHONPATH=${PYTHONPATH:-$TOP_DIR}
cd ${PROG_DIR} && ./main.py $@

exit 0
