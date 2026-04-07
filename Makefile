.PHONY: test test-kaven

test:
	pytest -q

test-kaven:
	pytest -q tests/test_kaven_dedup.py tests/test_kaven_log_replay_integration.py
