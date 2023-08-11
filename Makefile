LOCAL_VENV_NAME=.venv
PYTHON=python3
STACK?=NetworkStack

STAGE?= dev
ifeq ($(STAGE), prod)
	REGION=us-east-1
else
	REGION=eu-west-3
endif

local-venv:
	$(PYTHON) -m venv .venv

install-dependencies:
	pip install -r requirements.txt

lint:
	flake8 $(shell git ls-files '*.py')

test:
	pytest

synth:
	@cdk synth -c stage=$(STAGE) --output=cdk.out/$(STAGE) Selenium-$(STACK)-$(STAGE)

deploy:
	@cdk deploy --app=cdk.out/$(STAGE) Selenium-$(STACK)-$(STAGE)

diff:
	@cdk diff -c stage=$(STAGE) Selenium-$(STACK)-$(STAGE)

destroy:
	@cdk destroy -c stage=$(STAGE) Selenium-$(STACK)-$(STAGE)

bootstrapp-cdk-toolkit:
	@cdk bootstrap aws://964915130125/$(REGION) -c stage=$(STAGE)