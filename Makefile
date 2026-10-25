.PHONY: all install nopyc clean test check validate-release

SHELL := /usr/bin/env bash
PYTHON_BIN ?= python
PROJECT_VENV ?= venv
HA_TEST_HARNESS ?=

all: check test

venv:
	$(PYTHON_BIN) -m pip install virtualenv --user
	$(PYTHON_BIN) -m virtualenv $(PROJECT_VENV)

install: venv
	@( \
		source $(PROJECT_VENV)/bin/activate; \
		python -m pip install .; \
	)

nopyc:
	find . -name '*.pyc' | xargs rm -f || true
	find . -name __pycache__ | xargs rm -rf || true

clean: nopyc
	rm -rf build dist *.egg-info $(PROJECT_VENV)

test: install
	@( \
		source $(PROJECT_VENV)/bin/activate; \
		python -m pip install ".[dev]"; \
		if [[ "$(HA_TEST_HARNESS)" != "" ]]; then python -m pip install "pytest-homeassistant-custom-component==$(HA_TEST_HARNESS)" "pycares<5"; fi; \
		coverage run -m pytest -v && coverage report && coverage xml && coverage html; \
	)

check: install
	@( \
		source $(PROJECT_VENV)/bin/activate; \
		python -m pip install ".[dev]"; \
		mypy custom_components/hearth && flake8; \
	)

validate-release:
	@if [[ "${VERSION}" == "" ]]; then echo "VERSION is not set" & exit 1 ; fi

	@if [[ $$(grep "\"version\": \"${VERSION}\"" custom_components/hearth/manifest.json) == "" ]] ; then echo "Version not bumped in custom_components/hearth/manifest.json" & exit 1 ; fi

	@if [ -f SECURITY.md ]; then \
		MAJOR_MINOR=$$(echo "${VERSION}" | cut -d. -f1-2); \
		if [[ $$(grep "| $${MAJOR_MINOR}\.x" SECURITY.md) == "" ]] ; then echo "SECURITY.md missing supported-versions entry for $${MAJOR_MINOR}.x" & exit 1 ; fi; \
	fi
