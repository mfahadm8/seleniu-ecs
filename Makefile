LOCAL_VENV_NAME=.venv
PYTHON=python3
STACK?=NetworkStack

STAGE?= dev
ifeq ($(STAGE), prod)
	REGION=af-south-1
else
	REGION=us-east-1
endif

setup-codebuild:
	aws cloudformation deploy --template-file ./cloudformation/codebuild/docker_build.yml --stack-name CodebuildDockerPushStack --region $(REGION) --capabilities CAPABILITY_NAMED_IAM

s3-pipeline:
	aws cloudformation deploy --template-file ./cloudformation\s3\buckets.yaml --stack-name S3Buckets-$(STAGE) --region $(REGION) --capabilities CAPABILITY_NAMED_IAM

.PHONY: all test lint synth diff deploy

local-venv:
	$(PYTHON) -m venv .venv

install-dependencies:
	pip install -r requirements.txt

lint:
	flake8 $(shell git ls-files '*.py')

test:
	pytest

synth:
	@cdk synth -c stage=$(STAGE) --output=cdk.out/$(STAGE) $(STACK)-$(STAGE)

deploy:
	@cdk deploy --app=cdk.out/$(STAGE) $(STACK)-$(STAGE)

diff:
	@cdk diff -c stage=$(STAGE) $(STACK)-$(STAGE)

destroy:
	@cdk destroy -c stage=$(STAGE) $(STACK)-$(STAGE)

bootstrapp-cdk-toolkit:
	@cdk bootstrap aws://$(shell cat config/$(STAGE).yaml | yq -r '.awsAccount')/$(shell cat config/$(STAGE).yaml | yq -r '.aws_region') -c stage=$(STAGE)