#!/usr/bin/env python3
"""
Replicate OCI instance-principal request signing using local certificate and key files.

This uses the same flow as InstancePrincipalsSecurityTokenSigner but reads the leaf
certificate, private key, and optional intermediate certificate from the filesystem
instead of the instance metadata service. Useful for testing or running outside an
OCI instance when you have copied the instance identity cert/key (e.g. from
/etc/oci/ or from the metadata API).

Usage:
  # Minimum: leaf cert, key, and region (tenancy is read from the cert)
  python oci_signer_from_local_files.py \\
    --cert /path/to/cert.pem \\
    --key /path/to/key.pem \\
    --region us-phoenix-1

  # With optional intermediate cert (recommended if your tenancy uses it)
  python oci_signer_from_local_files.py \\
    --cert /path/to/identity/cert.pem \\
    --key /path/to/identity/key.pem \\
    --intermediate /path/to/identity/intermediate.pem \\
    --region us-phoenix-1

  # Run the enumeration script using this signer (example)
  python oci_signer_from_local_files.py -c cert.pem -k key.pem -r us-phoenix-1 --run-enumeration
"""

import argparse
import os
import sys

import oci.regions
from oci.auth import auth_utils
from oci.auth.certificate_retriever import FileBasedCertificateRetriever
from oci.auth.federation_client import X509FederationClient
from oci.auth.session_key_supplier import SessionKeySupplier
from oci.auth.signers.security_token_signer import (
    X509FederationClientBasedSecurityTokenSigner,
)


def create_signer_from_files(
    certificate_path,
    private_key_path,
    region,
    intermediate_certificate_path=None,
    passphrase=None,
    federation_cert_bundle_verify=None,
):
    """
    Build an OCI request signer that uses the same token-based flow as instance
    principals, but with cert/key read from local files.

    :param str certificate_path: Path to the leaf certificate PEM (e.g. identity/cert.pem).
    :param str private_key_path: Path to the leaf private key PEM (e.g. identity/key.pem).
    :param str region: OCI region identifier (e.g. us-phoenix-1, eu-frankfurt-1).
    :param str intermediate_certificate_path: Optional path to intermediate cert PEM.
    :param str passphrase: Optional passphrase for the private key.
    :param federation_cert_bundle_verify: Optional path to CA bundle or False to disable TLS verify.
    :return: A signer compatible with OCI clients (e.g. IdentityClient(config={}, signer=signer)).
             The signer also has a .tenancy_id attribute for compatibility with code that expects
             InstancePrincipalsSecurityTokenSigner.
    """
    certificate_path = os.path.expanduser(certificate_path)
    private_key_path = os.path.expanduser(private_key_path)
    if not os.path.isfile(certificate_path):
        raise FileNotFoundError(f"Certificate file not found: {certificate_path}")
    if not os.path.isfile(private_key_path):
        raise FileNotFoundError(f"Private key file not found: {private_key_path}")

    # Leaf cert + key from files (same as instance metadata identity/cert.pem + identity/key.pem)
    leaf_retriever = FileBasedCertificateRetriever(
        certificate_file_path=certificate_path,
        private_key_pem_file_path=private_key_path,
        passphrase=passphrase,
    )

    # Tenancy is encoded in the leaf cert (opc-tenant:ocid1.tenancy.oc1.....)
    tenancy_id = auth_utils.get_tenancy_id_from_certificate(
        leaf_retriever.get_certificate_as_certificate()
    )

    # Optional intermediate (same as instance metadata identity/intermediate.pem)
    intermediate_retrievers = []
    if intermediate_certificate_path:
        intermediate_certificate_path = os.path.expanduser(
            intermediate_certificate_path
        )
        if os.path.isfile(intermediate_certificate_path):
            intermediate_retrievers = [
                FileBasedCertificateRetriever(
                    certificate_file_path=intermediate_certificate_path,
                )
            ]
        else:
            raise FileNotFoundError(
                f"Intermediate certificate file not found: {intermediate_certificate_path}"
            )

    # Session key pair used when requesting the token; its private key signs requests made with the token
    session_key_supplier = SessionKeySupplier()

    # Auth service federation endpoint for X.509 token exchange (same URL shape as instance principal)
    federation_endpoint = "{}/v1/x509".format(oci.regions.endpoint_for("auth", region))

    federation_client = X509FederationClient(
        federation_endpoint=federation_endpoint,
        tenancy_id=tenancy_id,
        session_key_supplier=session_key_supplier,
        leaf_certificate_retriever=leaf_retriever,
        intermediate_certificate_retrievers=intermediate_retrievers,
        cert_bundle_verify=federation_cert_bundle_verify,
    )

    signer = X509FederationClientBasedSecurityTokenSigner(
        federation_client=federation_client
    )

    # So that code written for InstancePrincipalsSecurityTokenSigner can use signer.tenancy_id
    signer.tenancy_id = tenancy_id
    signer.region = region

    return signer


def main():
    parser = argparse.ArgumentParser(
        description="Create OCI request signer from local cert/key files (instance-principal style).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-c",
        "--cert",
        required=True,
        metavar="PATH",
        help="Path to leaf certificate PEM (e.g. identity/cert.pem).",
    )
    parser.add_argument(
        "-k",
        "--key",
        required=True,
        metavar="PATH",
        help="Path to leaf private key PEM (e.g. identity/key.pem).",
    )
    parser.add_argument(
        "-r",
        "--region",
        required=True,
        metavar="REGION",
        help="OCI region (e.g. us-phoenix-1, eu-frankfurt-1).",
    )
    parser.add_argument(
        "-i",
        "--intermediate",
        default=None,
        metavar="PATH",
        help="Optional path to intermediate certificate PEM.",
    )
    parser.add_argument(
        "--passphrase",
        default=None,
        help="Optional passphrase for the private key.",
    )
    parser.add_argument(
        "--run-enumeration",
        action="store_true",
        help="After creating the signer, run the enumeration script logic (list users/groups, test privileges).",
    )
    parser.add_argument(
        "--verify",
        default=None,
        metavar="PATH",
        help="Path to CA bundle for federation endpoint TLS verify, or 'false' to disable.",
    )
    args = parser.parse_args()

    verify = args.verify
    if verify is not None and verify.lower() == "false":
        verify = False

    try:
        signer = create_signer_from_files(
            certificate_path=args.cert,
            private_key_path=args.key,
            region=args.region,
            intermediate_certificate_path=args.intermediate,
            passphrase=args.passphrase,
            federation_cert_bundle_verify=verify,
        )
    except Exception as e:
        print(f"Failed to create signer: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Tenancy ID: {signer.tenancy_id}")
    print(f"Region:     {signer.region}")
    print("Signer created successfully (instance-principal style from local files).")

    if args.run_enumeration:
        try:
            from oci.identity import IdentityClient

            identity = IdentityClient(config={}, signer=signer)
            tenancy_id = signer.tenancy_id

            print("\n--- Listing users ---")
            users = identity.list_users(compartment_id=tenancy_id)
            for u in users.data:
                print(f"  {u.name} ({u.id})")

            print("\n--- Listing groups ---")
            groups = identity.list_groups(compartment_id=tenancy_id)
            for g in groups.data:
                print(f"  {g.name} ({g.id})")

            print("\nEnumeration completed successfully.")
        except Exception as e:
            print(f"Enumeration failed: {e}", file=sys.stderr)
            sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
