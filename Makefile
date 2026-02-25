PYTHONPATH := core:shared

.PHONY: test test-py test-go build-bridge smoke run-local release-artifacts rotate-tokens-dry-run

test: test-py test-go

test-py:
	PYTHONPATH=$(PYTHONPATH) python3 -m unittest discover -s tests -p 'test_*.py' -v

test-go:
	cd bridge && go test ./...

build-bridge:
	./installer/build_bridge_go.sh

smoke:
	./scripts/smoke_bridge.sh
	./scripts/smoke_runtime.sh

run-local:
	./installer/run_local_operator_stack.sh

release-artifacts:
	./installer/build_release_artifacts.sh

rotate-tokens-dry-run:
	./installer/rotate_tokens.sh --dry-run
