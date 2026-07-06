#!/usr/bin/env python3
"""
Pull instance identity certificate and key from an OCI compute instance via SSH.

Fetches cert.pem, key.pem, and (if present) intermediate.pem from the instance
metadata service and saves them locally for use with --auth instance_principal_from_files
or with oci_signer_from_local_files.py.

Usage:
  python pull_instance_identity.py -i ~/.ssh/mykey.pem --ip 129.146.0.1
  python pull_instance_identity.py -i key.pem --ip 10.0.0.5 --user opc --output-dir ./instance_identity
"""

import argparse
import os
import subprocess
import sys

# Default metadata base URL (can be overridden on the instance with OCI_METADATA_BASE_URL)
METADATA_BASE = "http://169.254.169.254/opc/v2"
REGION_PATH = "instance/region"
IDENTITY_PATHS = ("identity/cert.pem", "identity/key.pem", "identity/intermediate.pem")


def normalize_region(region_raw):
    """Convert short region key (e.g. phx) to long form (e.g. us-phoenix-1) if possible."""
    if not region_raw or not isinstance(region_raw, str):
        return None
    region_raw = region_raw.strip().lower()
    if not region_raw:
        return None
    try:
        import oci.regions
        if region_raw in getattr(oci.regions, "REGIONS_SHORT_NAMES", {}):
            return oci.regions.REGIONS_SHORT_NAMES[region_raw]
    except ImportError:
        pass
    return region_raw


def run_ssh_command(ssh_key_path, ip, user, remote_cmd, capture_output=True):
    """Run a command on the instance via SSH. Returns (success, stdout_bytes, stderr_bytes)."""
    key_path = os.path.expanduser(ssh_key_path)
    cmd = [
        "ssh",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        "{}@{}".format(user, ip),
        remote_cmd,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            timeout=30,
        )
        return result.returncode == 0, result.stdout or b"", result.stderr or b""
    except subprocess.TimeoutExpired:
        return False, b"", b"SSH command timed out"
    except FileNotFoundError:
        return False, b"", b"ssh command not found (OpenSSH client required)"
    except Exception as e:
        return False, b"", str(e).encode("utf-8")


def fetch_remote_file(ssh_key_path, ip, user, path_suffix):
    """Fetch one file from instance metadata. Returns (success, content_bytes)."""
    url = "{}/{}".format(METADATA_BASE, path_suffix)
    # Single-quote the URL so the shell on the instance doesn't expand anything
    remote_cmd = "curl -s -H 'Authorization: Bearer Oracle' '{}'".format(url)
    ok, stdout, stderr = run_ssh_command(ssh_key_path, ip, user, remote_cmd)
    if not ok:
        return False, None
    if not stdout.strip():
        return False, None
    return True, stdout


def fetch_region_from_instance(ssh_key_path, ip, user):
    """Fetch region from instance metadata and return normalized region string, or None on failure."""
    ok, content = fetch_remote_file(ssh_key_path, ip, user, REGION_PATH)
    if not ok or not content:
        return None
    try:
        region_raw = content.decode("utf-8")
    except Exception:
        return None
    return normalize_region(region_raw)


def main():
    parser = argparse.ArgumentParser(
        description="Pull instance identity cert/key from an OCI instance via SSH for local auth.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-i",
        "--key",
        required=True,
        metavar="PATH",
        help="Path to the SSH private key for the instance.",
    )
    parser.add_argument(
        "--ip",
        required=True,
        metavar="ADDRESS",
        help="Instance IP address (public or private).",
    )
    parser.add_argument(
        "-u",
        "--user",
        default="opc",
        metavar="USER",
        help="SSH username (default: opc).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        metavar="DIR",
        help="Directory to write cert.pem, key.pem, intermediate.pem (default: current directory).",
    )
    parser.add_argument(
        "--profile-name",
        default="instance_from_files",
        metavar="NAME",
        help="Profile name for the printed OCI config snippet (default: instance_from_files).",
    )
    parser.add_argument(
        "--region",
        default=None,
        metavar="REGION",
        help="Region in the config snippet. If omitted, region is fetched from the instance metadata.",
    )
    args = parser.parse_args()

    key_path = os.path.expanduser(args.key)
    if not os.path.isfile(key_path):
        print("ERROR: SSH key file not found: {}".format(key_path), file=sys.stderr)
        sys.exit(1)
    # Ensure key has safe permissions if we can
    try:
        mode = os.stat(key_path).st_mode
        if mode & 0o077:
            print("WARNING: SSH key has loose permissions. Consider: chmod 600 {}".format(key_path), file=sys.stderr)
    except OSError:
        pass

    output_dir = os.path.expanduser(args.output_dir)
    os.makedirs(output_dir, mode=0o700, exist_ok=True)

    out_cert = os.path.join(output_dir, "cert.pem")
    out_key = os.path.join(output_dir, "key.pem")
    out_intermediate = os.path.join(output_dir, "intermediate.pem")

    # Fetch cert (required)
    print("Fetching identity/cert.pem ...", end=" ", flush=True)
    ok, content = fetch_remote_file(args.key, args.ip, args.user, IDENTITY_PATHS[0])
    if not ok or not content:
        print("FAILED")
        print("  Ensure the instance is reachable and the SSH key is correct.", file=sys.stderr)
        sys.exit(1)
    with open(out_cert, "wb") as f:
        f.write(content)
    print("saved to {}".format(out_cert))

    # Fetch key (required)
    print("Fetching identity/key.pem ...", end=" ", flush=True)
    ok, content = fetch_remote_file(args.key, args.ip, args.user, IDENTITY_PATHS[1])
    if not ok or not content:
        print("FAILED")
        print("  Could not read private key from instance.", file=sys.stderr)
        sys.exit(1)
    with open(out_key, "wb") as f:
        f.write(content)
    os.chmod(out_key, 0o600)
    print("saved to {}".format(out_key))

    # Fetch intermediate (optional)
    print("Fetching identity/intermediate.pem ...", end=" ", flush=True)
    ok, content = fetch_remote_file(args.key, args.ip, args.user, IDENTITY_PATHS[2])
    if ok and content and content.strip():
        with open(out_intermediate, "wb") as f:
            f.write(content)
        print("saved to {}".format(out_intermediate))
    else:
        print("not present (optional)")

    # Fetch region from instance metadata (same source the SDK uses on the instance)
    region = args.region
    if region is None:
        print("Fetching instance/region ...", end=" ", flush=True)
        region = fetch_region_from_instance(args.key, args.ip, args.user)
        if region:
            print("{}".format(region))
        else:
            print("could not determine (optional: set --region)")

    # Print config snippet
    print()
    print("Add this to ~/.oci/config (or set OCI_CLI_CONFIG_FILE) to use with --auth instance_principal_from_files:")
    print()
    print("[{}]".format(args.profile_name))
    print("instance_certificate_file={}".format(os.path.abspath(out_cert)))
    print("instance_key_file={}".format(os.path.abspath(out_key)))
    if os.path.isfile(out_intermediate) and os.path.getsize(out_intermediate) > 0:
        print("intermediate_certificate_file={}".format(os.path.abspath(out_intermediate)))
    if region:
        print("region={}".format(region))
    else:
        print("region=<set your region, e.g. us-phoenix-1>")
    print()
    print("Then run:")
    print("  oci iam user list --auth instance_principal_from_files --profile {}".format(args.profile_name))
    print()


if __name__ == "__main__":
    main()
