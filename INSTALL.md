# Installing the OCI CLI fork (with `oci` on your PATH)

This fork adds the `instance_principal_from_files` auth method. Install it so the `oci` command is available on your PATH.

**If your system reports “externally-managed-environment”** when you run `pip install`, use a virtualenv (Option 3), `pipx` (Option 5), or `make venv` instead.

## Option 1: Install into your current Python (recommended)

From this directory (`oci-cli-fork/`):

```bash
pip install -e .
# or, if you use make:
make install
```

Then ensure the directory where `pip` installs scripts is on your PATH. Find it with:

```bash
python -c "import sys; print(sys.prefix + '/bin' if sys.prefix != sys.base_prefix else '')"
# or on Windows: ...\Scripts
```

If you use a virtualenv, activate it first; then `oci` will be in that venv’s `bin/` (or `Scripts/`).

## Option 2: Install for your user only (~/.local/bin)

```bash
pip install --user -e .
# or:
make install-user
```

The `oci` script is usually created under `~/.local/bin`. Add that to your PATH if it isn’t already (e.g. in `~/.bashrc` or `~/.zshrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Option 3: Isolated environment (venv)

Create a dedicated virtualenv and install the CLI there. When the venv is activated, `oci` is on your PATH:

```bash
make venv
. venv/bin/activate   # Linux/macOS
# venv\Scripts\activate  # Windows
oci --version
```

To use this `oci` from anywhere without activating, add the venv’s bin directory to your PATH:

```bash
export PATH="/path/to/oci-cli-fork/venv/bin:$PATH"
```

## Option 4: Build a wheel and install elsewhere

Build a wheel you can copy to another machine or environment:

```bash
make wheel
# Installs dist/oci_cli-<version>-py3-none-any.whl
pip install dist/oci_cli-*.whl
```

Or from another directory:

```bash
pip install /path/to/oci-cli-fork/dist/oci_cli-*.whl
```

## Option 5: pipx (isolated app on PATH)

If you use [pipx](https://pypa.github.io/pipx/), install the fork so `oci` is on your PATH without touching your global Python:

```bash
pipx install -e /path/to/oci-cli-fork
# or from inside the fork directory:
pipx install -e .
```

To upgrade later: `pipx reinstall oci-cli` (or re-run `pipx install -e .`).

## Verify

```bash
oci --version
oci iam user list --auth instance_principal_from_files --profile your_profile --help
```

## Dependencies

Install will pull in the CLI’s dependencies (see `setup.py`), including `oci` (SDK), `click`, `cryptography`, etc. Use a virtualenv if you want to avoid affecting your global Python.
