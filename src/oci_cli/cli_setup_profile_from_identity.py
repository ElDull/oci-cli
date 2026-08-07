# coding: utf-8
# Copyright (c) 2016, 2026, Oracle and/or its affiliates. All rights reserved.
# Fork addition: create an instance_principal_from_files profile from cert+key files.

from __future__ import print_function

import configparser
import os
import sys

import click
from oci.auth import auth_utils
from oci.auth.certificate_retriever import FileBasedCertificateRetriever

from oci_cli import cli_util
from oci_cli.cli_setup import setup_group, DEFAULT_DIRECTORY

DEFAULT_CONFIG_LOCATION = os.path.join(DEFAULT_DIRECTORY, 'config')
DEFAULT_PROFILE_NAME = 'instance_from_files'


@setup_group.command(
    'create-profile-from-identity',
    help="""Create an OCI config profile from instance identity certificate and key files.

Reads an instance identity certificate (cert.pem) and private key (key.pem),
extracts the tenancy OCID from the certificate, and writes a ready-to-use
profile for --auth instance_principal_from_files to the OCI config file.

\b
Example (individual files):
  oci setup create-profile-from-identity \\
    --cert ./cert.pem --key ./key.pem --set-region us-phoenix-1

\b
Example (directory, e.g. pull_instance_identity.py's --output-dir):
  oci setup create-profile-from-identity \\
    --identity-dir ./instance_identity --set-region us-phoenix-1

The certificate and key must be the instance identity PEMs from an OCI compute
instance (e.g. fetched via pull_instance_identity.py or from the instance
metadata service at identity/cert.pem and identity/key.pem). Pass either
--identity-dir (a directory containing cert.pem, key.pem, and optionally
intermediate.pem) or --cert/--key/--intermediate individually, not both.
""")
@cli_util.option('--cert', default=None, type=click.Path(exists=True, dir_okay=False),
                 help='Path to the instance identity certificate (cert.pem). '
                      'Mutually exclusive with --identity-dir.')
@cli_util.option('--key', default=None, type=click.Path(exists=True, dir_okay=False),
                 help='Path to the instance identity private key (key.pem). '
                      'Mutually exclusive with --identity-dir.')
@cli_util.option('--intermediate', default=None, type=click.Path(exists=True, dir_okay=False),
                 help='Path to the intermediate certificate (intermediate.pem). Optional. '
                      'Mutually exclusive with --identity-dir.')
@cli_util.option('--identity-dir', default=None, type=click.Path(exists=True, file_okay=False),
                 help='Directory containing cert.pem, key.pem, and (optionally) intermediate.pem '
                      '-- the layout pull_instance_identity.py writes. '
                      'Mutually exclusive with --cert/--key/--intermediate.')
@cli_util.option('--set-region', 'profile_region', required=True,
                 help='OCI region for the profile (e.g. us-phoenix-1).')
@cli_util.option('--profile-name', default=DEFAULT_PROFILE_NAME, show_default=True,
                 help='Name for the new config profile.')
@cli_util.option('--config-file', default=DEFAULT_CONFIG_LOCATION, show_default=True,
                 type=click.Path(dir_okay=False),
                 help='Path to the OCI config file to write to.')
@cli_util.option('--force', is_flag=True, default=False,
                 help='Overwrite existing profile if it already exists.')
@cli_util.help_option
def create_profile_from_identity(cert, key, intermediate, identity_dir, profile_region, profile_name, config_file, force):
    region = profile_region

    if identity_dir and (cert or key or intermediate):
        click.echo(
            "ERROR: --identity-dir cannot be combined with --cert/--key/--intermediate. "
            "Use one or the other.",
            err=True,
        )
        sys.exit(1)

    if identity_dir:
        identity_dir = os.path.abspath(os.path.expanduser(identity_dir))
        cert = os.path.join(identity_dir, 'cert.pem')
        key = os.path.join(identity_dir, 'key.pem')
        found = os.listdir(identity_dir)
        missing = [name for name, path in (('cert.pem', cert), ('key.pem', key)) if not os.path.isfile(path)]
        if missing:
            click.echo(
                "ERROR: {} not found in {}. Found: {}".format(
                    ' and '.join(missing), identity_dir, ', '.join(sorted(found)) or '(empty)'
                ),
                err=True,
            )
            sys.exit(1)
        candidate_intermediate = os.path.join(identity_dir, 'intermediate.pem')
        if os.path.isfile(candidate_intermediate):
            intermediate = candidate_intermediate
    elif not (cert and key):
        click.echo(
            "ERROR: either --identity-dir, or both --cert and --key, must be provided.",
            err=True,
        )
        sys.exit(1)

    cert_path = os.path.abspath(os.path.expanduser(cert))
    key_path = os.path.abspath(os.path.expanduser(key))
    config_file = os.path.expanduser(config_file)

    try:
        retriever = FileBasedCertificateRetriever(
            certificate_file_path=cert_path,
            private_key_pem_file_path=key_path,
        )
        tenancy_id = auth_utils.get_tenancy_id_from_certificate(
            retriever.get_certificate_as_certificate()
        )
    except Exception as e:
        click.echo(
            "ERROR: Could not load certificate/key or extract tenancy: {}\n"
            "Ensure the files are instance identity PEMs from an OCI compute instance.".format(e),
            err=True,
        )
        sys.exit(1)

    click.echo("Extracted tenancy OCID: {}".format(tenancy_id))

    intermediate_path = None
    if intermediate:
        intermediate_path = os.path.abspath(os.path.expanduser(intermediate))

    if os.path.exists(config_file):
        parser = configparser.ConfigParser(default_section="")
        try:
            parser.read(config_file)
        except configparser.Error:
            pass
        if parser.has_section(profile_name):
            if not force:
                click.echo(
                    "ERROR: Profile [{}] already exists in {}. "
                    "Use --force to overwrite.".format(profile_name, config_file),
                    err=True,
                )
                sys.exit(1)
            parser.remove_section(profile_name)
            with open(config_file, 'w') as f:
                parser.write(f)

    config_dir = os.path.dirname(config_file)
    if config_dir and not os.path.exists(config_dir):
        os.makedirs(config_dir, mode=0o700)

    existing = os.path.exists(config_file)
    with open(config_file, 'a') as f:
        if existing:
            f.write('\n')
        f.write('[{}]\n'.format(profile_name))
        f.write('instance_certificate_file={}\n'.format(cert_path))
        f.write('instance_key_file={}\n'.format(key_path))
        f.write('region={}\n'.format(region))
        if intermediate_path:
            f.write('intermediate_certificate_file={}\n'.format(intermediate_path))

    cli_util.apply_user_only_access_permissions(config_file)

    click.echo("Profile [{}] written to {}".format(profile_name, config_file))
    click.echo("")
    click.echo("Test it with:")
    click.echo("  oci whoami --auth instance_principal_from_files --profile {}".format(profile_name))
