# OCI CLI fork - install so 'oci' is on your PATH
#
# Quick:  make install          # install into current Python (oci goes to that Python's bin)
# Isolated: make venv && . venv/bin/activate   # then 'oci' is on PATH while venv is active
# Wheel:  make wheel           # build dist/oci_cli-*.whl to install elsewhere

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
WHEEL_DIR = dist

.PHONY: install install-user wheel venv clean help

help:
	@echo "OCI CLI fork - get 'oci' on your PATH"
	@echo ""
	@echo "  make install      - Install into current Python (editable). 'oci' will be in that Python's bin/ or Scripts/"
	@echo "  make install-user - Install for current user; 'oci' usually in ~/.local/bin (add to PATH if needed)"
	@echo "  make venv        - Create ./venv and install CLI there; run:  . venv/bin/activate  then use: oci"
	@echo "  make wheel       - Build wheel to dist/; then: pip install dist/oci_cli-*.whl"
	@echo "  make clean       - Remove build artifacts and venv"
	@echo ""
	@echo "After install, ensure the install directory is on your PATH (e.g. ~/.local/bin for install-user)."

# Editable install into current environment
install:
	$(PIP) install -e .

# Install for current user (binary typically in ~/.local/bin)
install-user:
	$(PIP) install --user -e .

# Build a wheel you can install anywhere: pip install dist/oci_cli-*.whl
wheel:
	$(PIP) install wheel
	$(PIP) wheel . --wheel-dir $(WHEEL_DIR) --no-deps
	@echo "Built: $(WHEEL_DIR)/oci_cli-*.whl"
	@echo "Install with: pip install $(WHEEL_DIR)/oci_cli-*.whl"

# Create a dedicated venv with oci installed (activate it to get oci on PATH)
venv:
	$(PYTHON) -m venv venv
	./venv/bin/pip install -e .
	@echo ""
	@echo "Activate the venv to use 'oci':"
	@echo "  . venv/bin/activate    # Linux/macOS"
	@echo "  venv\\\\Scripts\\\\activate  # Windows"
	@echo "Then run: oci --version"

clean:
	rm -rf build/
	rm -rf src/*.egg-info
	rm -rf *.egg-info
	rm -rf $(WHEEL_DIR)/
	rm -rf venv/
