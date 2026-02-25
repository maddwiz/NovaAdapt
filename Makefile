PYTHONPATH := core:shared

.PHONY: test test-py test-go build-bridge smoke run-local

test: test-py test-go

test-py:
	PYTHONPATH=$(PYTHONPATH) python3 -m unittest discover -s tests -p 'test_*.py' -v

test-go:
	cd bridge && go test ./...

build-bridge:
	./installer/build_bridge_go.sh

smoke:
	./scripts/smoke_bridge.sh

run-local:
	./installer/run_local_operator_stack.sh
