test:
	python3 -m pytest -q

test-maven:
	python3 -m pytest -q tests/test_maven_dedup.py tests/test_maven_log_replay_integration.py
