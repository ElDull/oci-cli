# coding: utf-8
# Copyright (c) 2016, 2026, Oracle and/or its affiliates. All rights reserved.
# This fork adds a whoami command to show proof of caller identity (instance principal, user, etc.).

from __future__ import print_function

import base64
import json
import re

import click
from oci.identity import IdentityClient
from oci.core import ComputeClient

from oci_cli.cli_root import cli
from oci_cli import cli_util

# Token-based signers use this prefix (see oci.auth.signers.security_token_signer)
SECURITY_TOKEN_PREFIX = "ST$"

# OCID pattern: ocid1.<resource type>.oc1.[realm].[region].[unique]
_OCID_PATTERN = re.compile(r"^ocid1\.([a-z0-9_-]+)\.oc1\.")


def _decode_jwt_payload(token_str):
    """Decode JWT payload (middle part). Returns dict or None."""
    try:
        parts = token_str.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None


def _is_ocid(s):
    """Return True if s looks like an OCI OCID."""
    if not s or not isinstance(s, str):
        return False
    return s.startswith("ocid1.") and ".oc1." in s


def _ocid_resource_type(ocid):
    """Extract resource type from OCID string, e.g. 'tenancy', 'compartment', 'user', 'instance'."""
    m = _OCID_PATTERN.match(ocid.strip())
    if m:
        return m.group(1).lower()
    return None


def _collect_ocids_from_payload(payload, signer):
    """Collect unique OCID strings from token payload and signer."""
    seen = set()
    ocids = []

    def add(v):
        if _is_ocid(v) and v not in seen:
            seen.add(v)
            ocids.append(v)

    if payload:
        for v in payload.values():
            if isinstance(v, str):
                add(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        add(item)
    if getattr(signer, "tenancy_id", None):
        add(signer.tenancy_id)
    return ocids


def _resolve_ocid_to_name(identity_client, compute_client, ocid, region):
    """Resolve a single OCID to a display name via API. Returns (resource_type, name) or (None, None)."""
    rtype = _ocid_resource_type(ocid)
    if not rtype:
        return None, None
    try:
        if rtype == "tenancy":
            r = identity_client.get_tenancy(tenancy_id=ocid)
            return "tenancy", r.data.name
        if rtype == "compartment":
            r = identity_client.get_compartment(compartment_id=ocid)
            return "compartment", r.data.name
        if rtype == "user":
            r = identity_client.get_user(user_id=ocid)
            return "user", r.data.name
        if rtype == "instance" and compute_client and region:
            r = compute_client.get_instance(instance_id=ocid)
            return "instance", getattr(r.data, "display_name", None) or r.data.id
    except Exception:
        return rtype, None
    return rtype, None


def _resolve_ocids(client_config, signer, ocids):
    """Resolve a list of OCIDs to names. Returns list of (ocid, resource_type, name)."""
    if not ocids:
        return []
    region = client_config.get("region")
    if not region:
        region = getattr(signer, "region", None)
    if not region:
        return [(ocid, _ocid_resource_type(ocid), None) for ocid in ocids]
    try:
        identity = IdentityClient(config=client_config, signer=signer)
        compute = ComputeClient(config=client_config, signer=signer) if client_config.get("region") else None
    except Exception:
        return [(ocid, _ocid_resource_type(ocid), None) for ocid in ocids]
    results = []
    for ocid in ocids:
        rtype, name = _resolve_ocid_to_name(identity, compute, ocid, region)
        results.append((ocid, rtype or _ocid_resource_type(ocid), name))
    return results


@cli.command("whoami", help="""Show the identity of the current caller (proof of who is making API requests).

For instance principal / instance_principal_from_files: prints the session token claims (tenancy, principal type, resource identifiers) so you can verify you are using the instance identity.

For API key auth: prints the user OCID and tenancy from config, and optionally fetches the user name from IAM.
""")
@click.pass_context
@cli_util.help_option_group
def whoami(ctx):
    config_and_signer = cli_util.create_config_and_signer_based_on_click_context(ctx)
    client_config = config_and_signer.config
    signer = config_and_signer.signer

    if signer is None:
        click.echo("ERROR: No signer could be created. Check your config and --auth.", err=True)
        raise SystemExit(1)

    # Token-based auth (instance principal, resource principal, session token, etc.)
    api_key = getattr(signer, "api_key", None)
    if api_key and isinstance(api_key, str) and api_key.startswith(SECURITY_TOKEN_PREFIX):
        token_str = api_key[len(SECURITY_TOKEN_PREFIX):]
        payload = _decode_jwt_payload(token_str)
        if payload:
            click.echo("Auth type: token (instance principal, resource principal, or session token)")
            click.echo("")
            click.echo("Session token claims (proof of caller identity):")
            # Show all claims so you can verify the principal; OCI uses various keys by principal type
            for key in sorted(payload.keys()):
                val = payload[key]
                click.echo("  {}: {}".format(key, val))
            # If we have tenancy_id / region on the signer (our instance_principal_from_files sets these)
            if hasattr(signer, "tenancy_id") and signer.tenancy_id:
                click.echo("")
                click.echo("Tenancy (from signer): {}".format(signer.tenancy_id))
            if hasattr(signer, "region") and signer.region:
                click.echo("Region (from signer):  {}".format(signer.region))
            # Resolve OCIDs to names via API
            ocids = _collect_ocids_from_payload(payload, signer)
            if ocids:
                resolved = _resolve_ocids(client_config, signer, ocids)
                if any(r[2] for r in resolved):
                    click.echo("")
                    click.echo("Resolved names (from API):")
                    for ocid, rtype, name in resolved:
                        if name:
                            click.echo("  {} ({}): {}".format(ocid, rtype, name))
                        else:
                            click.echo("  {} ({}): (no permission or not found)".format(ocid, rtype))
            click.echo("")
            click.echo("These claims are issued by OCI for this identity; using them proves you are that caller.")
            return
        click.echo("Auth type: token (could not decode JWT payload)")
        if hasattr(signer, "tenancy_id") and signer.tenancy_id:
            click.echo("Tenancy: {}".format(signer.tenancy_id))
        if hasattr(signer, "region") and signer.region:
            click.echo("Region:  {}".format(signer.region))
        return

    # API key auth
    user_ocid = client_config.get("user")
    tenancy_ocid = client_config.get("tenancy")
    if user_ocid or tenancy_ocid:
        click.echo("Auth type: API key (user)")
        click.echo("User OCID:    {}".format(user_ocid or "(not set)"))
        click.echo("Tenancy OCID: {}".format(tenancy_ocid or "(not set)"))
        if user_ocid or tenancy_ocid:
            try:
                identity = IdentityClient(config=client_config, signer=signer)
                if user_ocid:
                    try:
                        user = identity.get_user(user_id=user_ocid)
                        click.echo("User name:    {}".format(user.data.name))
                    except Exception as e:
                        click.echo("User name:    (could not fetch: {})".format(e))
                if tenancy_ocid:
                    try:
                        tenancy = identity.get_tenancy(tenancy_id=tenancy_ocid)
                        click.echo("Tenancy name: {}".format(tenancy.data.name))
                    except Exception as e:
                        click.echo("Tenancy name: (could not fetch: {})".format(e))
            except Exception as e:
                click.echo("(could not create Identity client: {})".format(e))
        return

    click.echo("Auth type: unknown (no user/tenancy in config and no token claims decoded)")
