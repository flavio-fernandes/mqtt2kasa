FROM python:3.9

RUN apt-get update && apt-get install -y dnsutils

WORKDIR /usr/src/app

COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

COPY . .

CMD ["./startup.sh"]
