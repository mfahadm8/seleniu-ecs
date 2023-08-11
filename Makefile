LOCAL_VENV_NAME=.venv
PYTHON=python3
STACK?=NetworkStack

STAGE?= dev
ifeq ($(STAGE), prod)
	REGION=us-east-1
else
	REGION=eu-west-3
endif

install-nvm:
	curl https://raw.githubusercontent.com/creationix/nvm/master/install.sh | bash
	source .bashrc
	exec bash --login

init:
	nvm install 16
	nvm use 16
	npm install -g aws-cdk
	make local-venv
	source .venv/bin/activate
	make install-dependencies

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
	make synth
	@cdk deploy --app=cdk.out/$(STAGE) Selenium-$(STACK)-$(STAGE)

diff:
	@cdk diff -c stage=$(STAGE) Selenium-$(STACK)-$(STAGE)

destroy:
	@cdk destroy -c stage=$(STAGE) Selenium-$(STACK)-$(STAGE)

bootstrapp-cdk-toolkit:
	@cdk bootstrap aws://964915130125/$(REGION) -c stage=$(STAGE)