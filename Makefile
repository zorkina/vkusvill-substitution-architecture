.PHONY: render check

render:
	bash scripts/render.sh

check:
	python3 scripts/check.py
