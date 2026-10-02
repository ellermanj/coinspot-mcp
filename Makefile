# SAM Python makefile build for src-layout + uv-managed deps.
# Artifact target directory is provided by SAM as $(ARTIFACTS_DIR).

.PHONY: build-CoinspotMcpFunction

build-CoinspotMcpFunction:
	uv export --no-dev --frozen --no-emit-project -o "$(ARTIFACTS_DIR)/requirements.txt"
	uv pip install --python-platform x86_64-manylinux2014 --target "$(ARTIFACTS_DIR)" -r "$(ARTIFACTS_DIR)/requirements.txt"
	cp -R src/coinspot_mcp "$(ARTIFACTS_DIR)/coinspot_mcp"
	# Drop caches from the deployment package.
	find "$(ARTIFACTS_DIR)" -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -f "$(ARTIFACTS_DIR)/requirements.txt"
