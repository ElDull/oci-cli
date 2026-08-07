# Instance Principal from Local Files

This fork adds an authentication method **`instance_principal_from_files`** that uses the same X.509 token exchange as instance principal, but reads the instance identity certificate and private key from **local files** instead of the instance metadata service.

Use this when you have copied the instance identity cert/key from an OCI compute instance (e.g. for testing or running the CLI from your laptop with instance principal privileges).

## Config profile

Create a profile in `~/.oci/config` (or the file set by `OCI_CLI_CONFIG_FILE`):

```ini
[instance_from_files]
instance_certificate_file=/path/to/identity/cert.pem
instance_key_file=/path/to/identity/key.pem
region=us-phoenix-1
# optional, if your tenancy uses an intermediate cert:
# intermediate_certificate_file=/path/to/identity/intermediate.pem
# optional, if the private key has a passphrase:
# pass_phrase=your_passphrase
```

Paths are expanded (e.g. `~` works). The certificate and key must be the **instance identity** PEMs (same as exposed at the instance metadata endpoints `identity/cert.pem` and `identity/key.pem`).

### Or: generate it automatically

Instead of writing the profile by hand, `oci setup create-profile-from-identity` extracts the tenancy OCID from the cert and writes the profile for you:

```bash
# Individual files:
oci setup create-profile-from-identity --cert ./cert.pem --key ./key.pem --set-region us-phoenix-1

# Or a whole directory (e.g. pull_instance_identity.py's --output-dir), auto-discovering
# cert.pem / key.pem / intermediate.pem inside it:
oci setup create-profile-from-identity --identity-dir ./identity --set-region us-phoenix-1
```

`--identity-dir` and `--cert`/`--key`/`--intermediate` are mutually exclusive. With `--identity-dir`, `cert.pem` and `key.pem` are required inside the directory; `intermediate.pem` is picked up automatically if present. Use `--profile-name` / `--config-file` / `--force` to control where it's written.

## Usage

Use the `--auth` option and the profile that contains the above keys:

```bash
oci iam user list --auth instance_principal_from_files --profile instance_from_files
```

Or set the auth and profile via environment variables:

```bash
export OCI_CLI_AUTH=instance_principal_from_files
export OCI_CLI_PROFILE=instance_from_files
oci iam user list
```

You can override paths with environment variables:

- `OCI_CLI_INSTANCE_CERTIFICATE_FILE` – path to leaf certificate
- `OCI_CLI_INSTANCE_KEY_FILE` – path to private key
- `OCI_CLI_INSTANCE_INTERMEDIATE_CERTIFICATE_FILE` – path to intermediate cert (optional)

Command-line `--region` overrides the profile region when present.

### Proof of identity (whoami)

To confirm you are using the instance identity (and not a user API key), run:

```bash
oci whoami --auth instance_principal_from_files --profile instance_from_files
```

This decodes the session token issued by OCI for your cert/key and prints its claims (e.g. tenancy, principal type, resource identifiers). Those claims are the proof that the CLI is authenticating as the instance principal tied to the certificate you provided.

## How it works

1. The CLI loads the profile and reads `instance_certificate_file`, `instance_key_file`, and `region` (and optionally `intermediate_certificate_file`).
2. It builds an OCI signer using the same flow as `InstancePrincipalsSecurityTokenSigner`:  
   leaf cert + key → tenancy from cert → session key → request token from Auth Service `/v1/x509` → sign requests with that token.
3. All subsequent API calls use this signer, so you get the same permissions as the dynamic group (and policies) attached to the instance whose identity you copied.

## Getting the cert and key from an instance

### Option 1: Automated pull via SSH

From the same repo (or scripts directory), use `pull_instance_identity.py` to fetch the identity files from a running instance via SSH:

```bash
python pull_instance_identity.py -i /path/to/instance_ssh_private_key --ip <instance_ip> [--user opc] [--output-dir ./identity] [--region us-phoenix-1]
```

This writes `cert.pem`, `key.pem`, and (if present) `intermediate.pem` into the output directory and prints a ready-to-paste config profile. Requires SSH access to the instance (e.g. opc + instance SSH key).

### Option 2: Manual (run on the instance)

On a Linux OCI compute instance, the metadata service provides the identity cert and key. Example (run on the instance):

```bash
# Optional: use a custom metadata base URL
# export OCI_METADATA_BASE_URL=http://169.254.169.254/opc/v2

curl -s -H "Authorization: Bearer Oracle" http://169.254.169.254/opc/v2/identity/cert.pem -o cert.pem
curl -s -H "Authorization: Bearer Oracle" http://169.254.169.254/opc/v2/identity/key.pem -o key.pem
curl -s -H "Authorization: Bearer Oracle" http://169.254.169.254/opc/v2/identity/intermediate.pem -o intermediate.pem
```

Copy `cert.pem`, `key.pem`, and (if present) `intermediate.pem` to your local machine and point your profile at them.

## Requirements

- **oci** Python SDK (same as the rest of the CLI).
- Certificate and key must be the instance identity for a compute instance that has the desired dynamic group and IAM policies.
- Region must match the tenancy/instance region (e.g. `us-phoenix-1`, `eu-frankfurt-1`).

## Security

- Protect the private key file (e.g. `chmod 600`). The CLI will warn if permissions are too open.
- Use this only in trusted environments; anyone with these files can assume the instance’s privileges until the instance is terminated or the identity is rotated.
