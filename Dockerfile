FROM python:3.10.12-slim
WORKDIR /usr/src/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mqtt2kasa/*.py mqtt2kasa/
COPY mqtt2kasa/git_info .
ENV PYTHONPATH=/usr/src/app
CMD ["python3", "mqtt2kasa/main.py", "/data/config.yaml"]
