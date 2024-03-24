FROM python:3.13-rc-bookworm

COPY . /src

RUN apt-get update && \
    apt-get install -y git curl build-essential gcc make

RUN curl https://sh.rustup.rs -sSf | bash -s -- -y

ENV PATH="/root/.cargo/bin:${PATH}"

RUN python3 -m pip install cffi
RUN python3 -m pip install --no-cache-dir git+https://github.com/sbtinstruments/aiomqtt
RUN python3 -m pip install --no-cache-dir -r /src/requirements.txt
WORKDIR /src
RUN python3 setup.py install

ENTRYPOINT ["python3", "/src/mqtt2kasa/main.py", "/src/data/config.yaml"]