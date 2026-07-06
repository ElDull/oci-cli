import oci
from oci.identity import IdentityClient
from oci.core import ComputeClient, VirtualNetworkClient
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
import json
import base64


def print_section(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def is_admin_group(group_name):
    """Check if a group name suggests admin privileges"""
    admin_keywords = ["admin", "administrator", "root", "superuser"]
    return any(keyword in group_name.lower() for keyword in admin_keywords)


def print_instance_info(signer):
    """Print detailed information about the instance from its token"""
    print_section("INSTANCE PRINCIPAL TOKEN INFORMATION")

    try:
        # Basic token information
        print("Token Metadata:")
        print(f"  Tenancy ID: {signer.tenancy_id}")

        # Try to get the security token (JWT)
        if hasattr(signer, "security_token"):
            print(
                f"\n  Security Token (truncated): {str(signer.security_token)[:100]}..."
            )

            # Try to decode JWT token (it's usually in 3 parts: header.payload.signature)
            try:
                token_parts = signer.security_token.split(".")
                if len(token_parts) >= 2:
                    # Decode header
                    print("\n  JWT Header:")
                    header_decoded = base64.urlsafe_b64decode(token_parts[0] + "==")
                    header_json = json.loads(header_decoded)
                    print(json.dumps(header_json, indent=4))

                    # Decode payload
                    print("\n  JWT Payload (Claims):")
                    payload_decoded = base64.urlsafe_b64decode(token_parts[1] + "==")
                    payload_json = json.loads(payload_decoded)
                    print(json.dumps(payload_json, indent=4))
            except Exception as e:
                print(f"\n  Could not decode JWT token: {e}")

        # Get instance metadata
        print("\n" + "-" * 80)
        print("Instance Metadata from OCI API:")
        print("-" * 80 + "\n")

        try:
            # Initialize compute client to get instance details
            compute = ComputeClient(config={}, signer=signer)

            # Get instance ID from metadata service
            import urllib.request

            metadata_url = "http://169.254.169.254/opc/v2/instance/"
            req = urllib.request.Request(metadata_url)
            req.add_header("Authorization", "Bearer Oracle")

            with urllib.request.urlopen(req, timeout=5) as response:
                metadata = json.loads(response.read().decode())

                print("Instance Metadata:")
                print(f"  Instance ID: {metadata.get('id', 'N/A')}")
                print(f"  Display Name: {metadata.get('displayName', 'N/A')}")
                print(f"  Compartment ID: {metadata.get('compartmentId', 'N/A')}")
                print(f"  Region: {metadata.get('region', 'N/A')}")
                print(
                    f"  Canonical Region: {metadata.get('canonicalRegionName', 'N/A')}"
                )
                print(
                    f"  Availability Domain: {metadata.get('availabilityDomain', 'N/A')}"
                )
                print(f"  Fault Domain: {metadata.get('faultDomain', 'N/A')}")
                print(f"  Shape: {metadata.get('shape', 'N/A')}")
                print(f"  Time Created: {metadata.get('timeCreated', 'N/A')}")

                instance_id = metadata.get("id")
                compartment_id = metadata.get("compartmentId")

                # Get more detailed instance information via API
                if instance_id:
                    try:
                        instance = compute.get_instance(instance_id=instance_id)
                        print("\nInstance Details from API:")
                        print(f"  Lifecycle State: {instance.data.lifecycle_state}")
                        print(f"  Launch Mode: {instance.data.launch_mode}")
                        print(f"  Image ID: {instance.data.image_id}")

                        if instance.data.metadata:
                            print(f"\n  Custom Metadata:")
                            for key, value in instance.data.metadata.items():
                                print(f"    {key}: {value}")

                        if instance.data.freeform_tags:
                            print(f"\n  Freeform Tags:")
                            for key, value in instance.data.freeform_tags.items():
                                print(f"    {key}: {value}")

                        if instance.data.defined_tags:
                            print(f"\n  Defined Tags:")
                            print(json.dumps(instance.data.defined_tags, indent=4))
                    except Exception as e:
                        print(f"\n  Could not get instance details via API: {e}")

                # Get VNIC information
                if instance_id and compartment_id:
                    try:
                        vnic_attachments = compute.list_vnic_attachments(
                            compartment_id=compartment_id, instance_id=instance_id
                        )

                        if vnic_attachments.data:
                            print("\nNetwork Information:")
                            vnet = VirtualNetworkClient(config={}, signer=signer)

                            for attachment in vnic_attachments.data:
                                if attachment.lifecycle_state == "ATTACHED":
                                    vnic = vnet.get_vnic(vnic_id=attachment.vnic_id)
                                    print(
                                        f"  VNIC Display Name: {vnic.data.display_name}"
                                    )
                                    print(f"  Private IP: {vnic.data.private_ip}")
                                    print(
                                        f"  Public IP: {vnic.data.public_ip or 'None'}"
                                    )
                                    print(f"  Subnet ID: {vnic.data.subnet_id}")
                                    print(f"  MAC Address: {vnic.data.mac_address}")
                                    print(f"  Hostname: {vnic.data.hostname_label}")
                    except Exception as e:
                        print(f"\n  Could not get network information: {e}")

        except urllib.error.URLError as e:
            print(f"Could not access instance metadata service: {e}")
            print("(This is normal if not running on an OCI instance)")
        except Exception as e:
            print(f"Error retrieving instance metadata: {e}")

        # Print signer attributes
        print("\n" + "-" * 80)
        print("Signer Object Attributes:")
        print("-" * 80 + "\n")

        for attr in dir(signer):
            if not attr.startswith("_") and not callable(getattr(signer, attr)):
                try:
                    value = getattr(signer, attr)
                    if value and not isinstance(value, (type, type(None))):
                        print(f"  {attr}: {value}")
                except:
                    pass

    except Exception as e:
        print(f"ERROR getting instance information: {e}")
        import traceback

        traceback.print_exc()


def enumerate_users(identity, tenancy_id):
    """Enumerate all users in the tenancy"""
    print_section("ENUMERATING USERS")

    try:
        users_response = identity.list_users(compartment_id=tenancy_id)
        users = users_response.data

        print(f"Found {len(users)} users:\n")

        for user in users:
            print(f"User: {user.name}")
            print(f"  ID: {user.id}")
            print(f"  Email: {user.email}")
            print(f"  Lifecycle State: {user.lifecycle_state}")
            print(f"  Description: {user.description}")
            print(f"  Time Created: {user.time_created}")

            # Try to get user's group memberships
            try:
                memberships = identity.list_user_group_memberships(
                    compartment_id=tenancy_id, user_id=user.id
                )
                if memberships.data:
                    print(f"  Group Memberships:")
                    for membership in memberships.data:
                        group = identity.get_group(group_id=membership.group_id)
                        is_admin = is_admin_group(group.data.name)
                        admin_marker = " [ADMIN]" if is_admin else ""
                        print(f"    - {group.data.name}{admin_marker}")
                else:
                    print(f"  Group Memberships: None")
            except Exception as e:
                print(f"  Group Memberships: ERROR - {e}")

            print()

        return users
    except Exception as e:
        print(f"ERROR listing users: {e}")
        return []


def enumerate_groups(identity, tenancy_id):
    """Enumerate all groups in the tenancy"""
    print_section("ENUMERATING GROUPS")

    try:
        groups_response = identity.list_groups(compartment_id=tenancy_id)
        groups = groups_response.data

        print(f"Found {len(groups)} groups:\n")

        for group in groups:
            is_admin = is_admin_group(group.name)
            admin_marker = " [ADMIN]" if is_admin else ""

            print(f"Group: {group.name}{admin_marker}")
            print(f"  ID: {group.id}")
            print(f"  Description: {group.description}")
            print(f"  Lifecycle State: {group.lifecycle_state}")
            print(f"  Time Created: {group.time_created}")

            # Try to list group members
            try:
                memberships = identity.list_user_group_memberships(
                    compartment_id=tenancy_id, group_id=group.id
                )
                if memberships.data:
                    print(f"  Members ({len(memberships.data)}):")
                    for membership in memberships.data:
                        try:
                            user = identity.get_user(user_id=membership.user_id)
                            print(f"    - {user.data.name}")
                        except Exception as e:
                            print(f"    - [User ID: {membership.user_id}] (Error: {e})")
                else:
                    print(f"  Members: None")
            except Exception as e:
                print(f"  Members: ERROR - {e}")

            print()

        return groups
    except Exception as e:
        print(f"ERROR listing groups: {e}")
        return []


def test_user_privileges(identity, tenancy_id, users):
    """Test 'use' privileges on users"""
    print_section("TESTING USER PRIVILEGES")

    print("Testing ability to get detailed user information:\n")

    for user in users:
        try:
            # Try to get user details (tests inspect privileges)
            user_details = identity.get_user(user_id=user.id)

            # Check if user is in admin group
            memberships = identity.list_user_group_memberships(
                compartment_id=tenancy_id, user_id=user.id
            )
            is_admin = False
            for membership in memberships.data:
                group = identity.get_group(group_id=membership.group_id)
                if is_admin_group(group.data.name):
                    is_admin = True
                    break

            admin_status = "[ADMIN]" if is_admin else "[NON-ADMIN]"
            print(f"✓ {admin_status} Successfully accessed: {user.name}")

            # Try to list user's API keys (tests deeper privileges)
            try:
                api_keys = identity.list_api_keys(user_id=user.id)
                print(f"    - Can list API keys: {len(api_keys.data)} found")
            except Exception as e:
                print(f"    - Cannot list API keys: {type(e).__name__}")

            # Try to list user's auth tokens (tests use privileges)
            try:
                auth_tokens = identity.list_auth_tokens(user_id=user.id)
                print(f"    - Can list auth tokens: {len(auth_tokens.data)} found")
            except Exception as e:
                print(f"    - Cannot list auth tokens: {type(e).__name__}")

        except Exception as e:
            print(f"✗ Failed to access user {user.name}: {type(e).__name__} - {e}")

        print()


def test_group_privileges(identity, tenancy_id, groups):
    """Test privileges on groups"""
    print_section("TESTING GROUP PRIVILEGES")

    print("Testing ability to access group information:\n")

    for group in groups:
        is_admin = is_admin_group(group.name)
        admin_status = "[ADMIN]" if is_admin else "[NON-ADMIN]"

        try:
            # Try to get group details
            group_details = identity.get_group(group_id=group.id)
            print(f"✓ {admin_status} Successfully accessed: {group.name}")

            # Try to list members
            try:
                memberships = identity.list_user_group_memberships(
                    compartment_id=tenancy_id, group_id=group.id
                )
                print(f"    - Can list members: {len(memberships.data)} found")
            except Exception as e:
                print(f"    - Cannot list members: {type(e).__name__}")

        except Exception as e:
            print(f"✗ Failed to access group {group.name}: {type(e).__name__} - {e}")

        print()


def main():
    print_section("OCI INSTANCE PRINCIPAL ENUMERATION TEST")

    try:
        # Initialize signer and identity client
        signer = InstancePrincipalsSecurityTokenSigner()
        identity = IdentityClient(config={}, signer=signer)
        tenancy_id = signer.tenancy_id

        print(f"Tenancy ID: {tenancy_id}\n")

        # Print detailed instance information
        print_instance_info(signer)

        # Enumerate users
        users = enumerate_users(identity, tenancy_id)

        # Enumerate groups
        groups = enumerate_groups(identity, tenancy_id)

        # Test user privileges
        if users:
            test_user_privileges(identity, tenancy_id, users)

        # Test group privileges
        if groups:
            test_group_privileges(identity, tenancy_id, groups)

        print_section("ENUMERATION COMPLETE")

    except Exception as e:
        print(f"\nCRITICAL ERROR: {type(e).__name__} - {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
