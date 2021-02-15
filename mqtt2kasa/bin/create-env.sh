#!/bin/bash
set -o errexit
set -o xtrace

cd "$(dirname $0)"
BIN_DIR="${PWD}"
PROG_DIR="${BIN_DIR%/*}"
TOP_DIR="${PROG_DIR%/*}"

pushd ${TOP_DIR}
if [ ! -e ./env ]; then
    #virtualenv --system-site-packages env
    python3 -m venv --copies env
fi
source ./env/bin/activate
#pip install --upgrade pip setuptools
pip install --ignore-installed -r ./requirements.txt
deactivate

popd
exit 0
