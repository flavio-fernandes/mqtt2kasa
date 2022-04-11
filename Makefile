PROJECT=$(shell basename $(shell pwd))
TAG=ghcr.io/johnjones4/${PROJECT}

info:
	echo ${PROJECT}

ci:
	docker build -t ${TAG} .
	docker push ${TAG}:latest
	docker image rm ${TAG}:latest
