# Copyright (c) 2026 Cytech Technology Pte Ltd
#
# MQTT TLS helpers shared by the Comfort bridge and ingress web UI.

"""
Certificate management for Cytech Comfort MQTT TLS.

The private Certificate Authority key is stored in the add-on's
persistent /data directory.

Certificates and keys required by MQTT clients/Mosquitto are stored
in Home Assistant's shared /ssl directory.
"""
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.x509.oid import NameOID
from pathlib import Path
import logging
from mqtt_tls import validate_certificate, validate_key_matches_cert
import os
import ipaddress
import requests

logger = logging.getLogger(__name__)


# Private persistent storage belonging to this add-on
PRIVATE_CERT_DIR = Path("/data/certificates")

# Shared Home Assistant SSL storage
SSL_CERT_DIR = Path("/ssl/cytech_comfort")


# Certificate Authority
CA_KEY = PRIVATE_CERT_DIR / "ca.key"
CA_CERT = SSL_CERT_DIR / "ca.crt"

# Mosquitto server
SERVER_KEY = SSL_CERT_DIR / "mqtt-server.key"
SERVER_CERT = SSL_CERT_DIR / "mqtt-server.crt"

# Cytech Comfort MQTT client
CLIENT_KEY = SSL_CERT_DIR / "comfort-client.key"
CLIENT_CERT = SSL_CERT_DIR / "comfort-client.crt"


def ensure_certificate_directories() -> None:
    """Create the certificate directories if they do not already exist."""

    PRIVATE_CERT_DIR.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    SSL_CERT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def certificate_set_exists() -> bool:
    """Return True if the complete Comfort MQTT certificate set exists."""

    required_files = (
        CA_KEY,
        CA_CERT,
        SERVER_KEY,
        SERVER_CERT,
        CLIENT_KEY,
        CLIENT_CERT,
    )

    return all(path.is_file() for path in required_files)


def certificate_status() -> dict[str, bool]:
    """Return the presence status of each certificate/key."""

    return {
        "ca_key": CA_KEY.is_file(),
        "ca_cert": CA_CERT.is_file(),
        "server_key": SERVER_KEY.is_file(),
        "server_cert": SERVER_CERT.is_file(),
        "client_key": CLIENT_KEY.is_file(),
        "client_cert": CLIENT_CERT.is_file(),
    }

def generate_ca() -> None:
    """
    Generate the installation-specific MQTT Certificate Authority.

    The CA private key is kept in the add-on's private /data storage.
    The public CA certificate is written to /ssl/cytech_comfort.
    """

    ensure_certificate_directories()

    if CA_KEY.exists() or CA_CERT.exists():
        raise RuntimeError(
            "CA key or certificate already exists; refusing to overwrite it"
        )

    logger.info("Generating local Cytech Comfort MQTT Certificate Authority")

    # Generate a new private RSA key for this installation.
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "Cytech Comfort MQTT Local CA",
        ),
    ])

    now = datetime.now(timezone.utc)


    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365 * 20))
        .add_extension(
            x509.BasicConstraints(
                ca=True,
                path_length=0,
            ),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(
                private_key.public_key()
            ),
            critical=False,
        )
        .sign(
            private_key=private_key,
            algorithm=hashes.SHA256(),
        )
    )

    # Write the CA private key.
    CA_KEY.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    # Restrict access to the signing key.
    CA_KEY.chmod(0o600)

    # Write the public CA certificate.
    CA_CERT.write_bytes(
        certificate.public_bytes(serialization.Encoding.PEM)
    )

    logger.info("Local MQTT Certificate Authority generated successfully")


def generate_server_certificate() -> None:
    """
    Generate the Mosquitto MQTT server certificate and private key.

    The certificate is signed by the installation-specific local CA.
    """

    ensure_certificate_directories()

    if not CA_KEY.exists() or not CA_CERT.exists():
        raise RuntimeError(
            "Local CA does not exist; generate the CA before the server certificate"
        )

    if SERVER_KEY.exists() or SERVER_CERT.exists():
        raise RuntimeError(
            "Server key or certificate already exists; refusing to overwrite it"
        )

    logger.info("Generating Mosquitto MQTT server certificate")

    ca_private_key = serialization.load_pem_private_key(
        CA_KEY.read_bytes(),
        password=None,
    )

    ca_certificate = x509.load_pem_x509_certificate(
        CA_CERT.read_bytes()
    )

    server_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,
    )

    subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "core-mosquitto",
        ),
    ])

    now = datetime.now(timezone.utc)

    ha_ipv4 = get_home_assistant_ipv4()

    logger.info(
        "Generating Mosquitto server certificate for HA IPv4 address %s",
        ha_ipv4,
    )

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_certificate.subject)
        .public_key(server_private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365 * 10))
        .add_extension(
            x509.BasicConstraints(
                ca=False,
                path_length=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH
            ]),
            critical=False,
        )

        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("core-mosquitto"),
                x509.DNSName("homeassistant.local"),
                x509.IPAddress(ha_ipv4),
            ]),
            critical=False,
        )

        .sign(
            private_key=ca_private_key,
            algorithm=hashes.SHA256(),
        )
    )

    SERVER_KEY.write_bytes(
        server_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    SERVER_KEY.chmod(0o600)

    SERVER_CERT.write_bytes(
        certificate.public_bytes(serialization.Encoding.PEM)
    )

    logger.info("Mosquitto MQTT server certificate generated successfully")


def generate_client_certificate() -> None:
    """
    Generate the Cytech Comfort MQTT client certificate and private key.

    The certificate is signed by the installation-specific local CA
    and is intended for MQTT mutual TLS client authentication.
    """

    ensure_certificate_directories()

    if not CA_KEY.exists() or not CA_CERT.exists():
        raise RuntimeError(
            "Local CA does not exist; generate the CA before the client certificate"
        )

    if CLIENT_KEY.exists() or CLIENT_CERT.exists():
        raise RuntimeError(
            "Client key or certificate already exists; refusing to overwrite it"
        )

    logger.info("Generating Cytech Comfort MQTT client certificate")

    # Load the installation-specific CA.
    ca_private_key = serialization.load_pem_private_key(
        CA_KEY.read_bytes(),
        password=None,
    )

    ca_certificate = x509.load_pem_x509_certificate(
        CA_CERT.read_bytes()
    )

    # Generate a unique private key for this Comfort installation.
    client_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,
    )

    subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "cytech-comfort",
        ),
    ])

    now = datetime.now(timezone.utc)

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_certificate.subject)
        .public_key(client_private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365 * 10))
        .add_extension(
            x509.BasicConstraints(
                ca=False,
                path_length=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH
            ]),
            critical=False,
        )
        .sign(
            private_key=ca_private_key,
            algorithm=hashes.SHA256(),
        )
    )

    CLIENT_KEY.write_bytes(
        client_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    CLIENT_KEY.chmod(0o600)

    CLIENT_CERT.write_bytes(
        certificate.public_bytes(serialization.Encoding.PEM)
    )

    logger.info(
        "Cytech Comfort MQTT client certificate generated successfully"
    )




def validate_signed_by_ca(cert_path: Path) -> None:
    """
    Verify that a certificate was signed by this installation's local CA.
    """

    if not CA_CERT.is_file():
        raise RuntimeError(
            f"CA certificate not found: {CA_CERT}"
        )

    if not cert_path.is_file():
        raise RuntimeError(
            f"Certificate not found: {cert_path}"
        )

    try:
        ca_cert = x509.load_pem_x509_certificate(
            CA_CERT.read_bytes()
        )

        cert = x509.load_pem_x509_certificate(
            cert_path.read_bytes()
        )

        # Check that the certificate identifies our CA as its issuer.
        if cert.issuer != ca_cert.subject:
            raise RuntimeError(
                f"Certificate issuer does not match local CA: {cert_path}"
            )

        # Cryptographically verify the certificate signature.
        ca_public_key = ca_cert.public_key()

        ca_public_key.verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )

    except RuntimeError:
        raise

    except Exception as exc:
        raise RuntimeError(
            f"Certificate signature verification failed: {cert_path}"
        ) from exc


def write_temporary_server_certificate(
    cert_path: Path,
    key_path: Path,
) -> None:
    """
    Generate a new Mosquitto server certificate/key pair at temporary paths.

    The existing live server certificate and key are not modified.
    """

    if not CA_KEY.is_file() or not CA_CERT.is_file():
        raise RuntimeError(
            "Local CA does not exist; cannot generate server certificate"
        )

    ca_private_key = serialization.load_pem_private_key(
        CA_KEY.read_bytes(),
        password=None,
    )

    ca_certificate = x509.load_pem_x509_certificate(
        CA_CERT.read_bytes()
    )

    server_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,
    )

    subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "core-mosquitto",
        ),
    ])

    now = datetime.now(timezone.utc)
    ha_ipv4 = get_home_assistant_ipv4()

    logger.info(
        "Generating replacement Mosquitto server certificate "
        "for HA IPv4 address %s",
        ha_ipv4,
    )

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_certificate.subject)
        .public_key(server_private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365 * 10))
        .add_extension(
            x509.BasicConstraints(
                ca=False,
                path_length=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("core-mosquitto"),
                x509.DNSName("homeassistant.local"),
                x509.IPAddress(ha_ipv4),
            ]),
            critical=False,
        )
        .sign(
            private_key=ca_private_key,
            algorithm=hashes.SHA256(),
        )
    )

    key_path.write_bytes(
        server_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)

    cert_path.write_bytes(
        certificate.public_bytes(serialization.Encoding.PEM)
    )



def renew_server_certificate() -> None:
    """
    Safely replace the Mosquitto server certificate/key while retaining
    the installation-specific CA.

    The replacement certificate is generated and validated before the
    existing live certificate/key pair is changed.

    The existing pair is backed up during installation so it can be
    restored if installation or final validation fails.
    """

    logger.warning(
        "Renewing Mosquitto server certificate for current HA network identity"
    )

    validate_certificate(CA_CERT)
    validate_key_matches_cert(CA_CERT, CA_KEY)

    if SERVER_CERT.exists() != SERVER_KEY.exists():
        raise RuntimeError(
            "Incomplete Mosquitto server certificate/key pair; "
            "automatic renewal has been stopped"
        )

    temp_cert = SSL_CERT_DIR / "mqtt-server.crt.new"
    temp_key = SSL_CERT_DIR / "mqtt-server.key.new"

    backup_cert = SSL_CERT_DIR / "mqtt-server.crt.bak"
    backup_key = SSL_CERT_DIR / "mqtt-server.key.bak"

    # Remove temporary files left by a previously interrupted attempt.
    temp_cert.unlink(missing_ok=True)
    temp_key.unlink(missing_ok=True)

    # Backup files should not normally exist when this function starts.
    # Do not overwrite them because they may contain the last known
    # working server certificate/key pair from an interrupted renewal.
    if backup_cert.exists() or backup_key.exists():
        raise RuntimeError(
            "Mosquitto server certificate backup files already exist; "
            "automatic renewal has been stopped"
        )

    backup_created = False

    try:
        # ------------------------------------------------------------
        # 1. Generate and validate the replacement pair
        # ------------------------------------------------------------

        write_temporary_server_certificate(
            temp_cert,
            temp_key,
        )

        validate_certificate(temp_cert)
        validate_key_matches_cert(temp_cert, temp_key)
        validate_signed_by_ca(temp_cert)

        cert = x509.load_pem_x509_certificate(
            temp_cert.read_bytes()
        )

        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value

        dns_names = set(
            san.get_values_for_type(x509.DNSName)
        )

        ip_addresses = set(
            san.get_values_for_type(x509.IPAddress)
        )

        required_dns_names = {
            "core-mosquitto",
            "homeassistant.local",
        }

        ha_ipv4 = get_home_assistant_ipv4()

        if not required_dns_names.issubset(dns_names):
            raise RuntimeError(
                "Replacement Mosquitto server certificate is missing "
                "required DNS SAN entries"
            )

        if ha_ipv4 not in ip_addresses:
            raise RuntimeError(
                "Replacement Mosquitto server certificate does not "
                "contain the current Home Assistant IPv4 address"
            )

        logger.info(
            "Replacement Mosquitto server certificate validated successfully"
        )

        # ------------------------------------------------------------
        # 2. Back up the currently installed pair
        # ------------------------------------------------------------

        if SERVER_CERT.exists() and SERVER_KEY.exists():
            os.replace(SERVER_CERT, backup_cert)
            os.replace(SERVER_KEY, backup_key)
            backup_created = True

            logger.info(
                "Existing Mosquitto server certificate/key backed up"
            )

        # ------------------------------------------------------------
        # 3. Install the validated replacement pair
        # ------------------------------------------------------------

        os.replace(temp_key, SERVER_KEY)
        os.replace(temp_cert, SERVER_CERT)

        SERVER_KEY.chmod(0o600)

        # ------------------------------------------------------------
        # 4. Validate the installed pair
        # ------------------------------------------------------------

        validate_certificate(SERVER_CERT)
        validate_key_matches_cert(SERVER_CERT, SERVER_KEY)
        validate_signed_by_ca(SERVER_CERT)

        if not server_certificate_matches_current_network():
            raise RuntimeError(
                "Installed Mosquitto server certificate does not match "
                "the current HA network identity"
            )

        logger.info(
            "Installed Mosquitto server certificate validated successfully"
        )

    except Exception:
        logger.exception(
            "Mosquitto server certificate renewal failed"
        )

        # ------------------------------------------------------------
        # Restore the previous working pair if we backed one up.
        # ------------------------------------------------------------

        if backup_created:
            logger.warning(
                "Restoring previous Mosquitto server certificate/key"
            )

            SERVER_CERT.unlink(missing_ok=True)
            SERVER_KEY.unlink(missing_ok=True)

            if backup_cert.exists():
                os.replace(backup_cert, SERVER_CERT)

            if backup_key.exists():
                os.replace(backup_key, SERVER_KEY)
                SERVER_KEY.chmod(0o600)

            logger.info(
                "Previous Mosquitto server certificate/key restored"
            )

        raise

    else:
        # Renewal completed successfully. The old pair is no longer
        # required.
        backup_cert.unlink(missing_ok=True)
        backup_key.unlink(missing_ok=True)

        logger.info(
            "Mosquitto server certificate renewed successfully"
        )

    finally:
        temp_cert.unlink(missing_ok=True)
        temp_key.unlink(missing_ok=True)



def server_certificate_matches_current_network() -> bool:
    """
    Return True if the Mosquitto server certificate contains the current
    Home Assistant IPv4 address and required DNS names in its SAN.
    """

    if not SERVER_CERT.is_file():
        return False

    ha_ipv4 = get_home_assistant_ipv4()

    try:
        cert = x509.load_pem_x509_certificate(
            SERVER_CERT.read_bytes()
        )

        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value

        dns_names = set(
            san.get_values_for_type(x509.DNSName)
        )

        ip_addresses = set(
            san.get_values_for_type(x509.IPAddress)
        )

    except Exception as exc:
        raise RuntimeError(
            f"Unable to examine Mosquitto server certificate SAN: {SERVER_CERT}"
        ) from exc

    required_dns_names = {
        "core-mosquitto",
        "homeassistant.local",
    }

    if not required_dns_names.issubset(dns_names):
        logger.warning(
            "Mosquitto server certificate is missing required DNS SAN entries"
        )
        return False

    if ha_ipv4 not in ip_addresses:
        logger.warning(
            "Home Assistant IPv4 address %s is not present in "
            "Mosquitto server certificate",
            ha_ipv4,
        )
        return False

    logger.info(
        "Mosquitto server certificate matches current HA network identity "
        "(IPv4=%s)",
        ha_ipv4,
    )

    return True






def validate_certificate_set() -> None:
    """
    Validate the complete Cytech Comfort MQTT certificate set.

    Checks:
    - CA certificate is valid
    - CA private key matches CA certificate
    - Server certificate is valid
    - Server private key matches server certificate
    - Server certificate was signed by the local CA
    - Client certificate is valid
    - Client private key matches client certificate
    - Client certificate was signed by the local CA
    """

    logger.info("Validating MQTT certificate set")

    # Validate CA certificate and its private key.
    validate_certificate(CA_CERT)
    validate_key_matches_cert(CA_CERT, CA_KEY)

    # Validate Mosquitto server certificate.
    validate_certificate(SERVER_CERT)
    validate_key_matches_cert(SERVER_CERT, SERVER_KEY)
    validate_signed_by_ca(SERVER_CERT)

    # Validate Cytech Comfort client certificate.
    validate_certificate(CLIENT_CERT)
    validate_key_matches_cert(CLIENT_CERT, CLIENT_KEY)
    validate_signed_by_ca(CLIENT_CERT)

    logger.info("MQTT certificate set validation successful")


def recover_interrupted_server_renewal() -> None:
    """
    Recover safely from an interrupted Mosquitto server certificate renewal.

    Renewal may leave live, backup (.bak), or temporary (.new) files if the
    add-on or host stops during certificate replacement.

    A backup pair is restored only when its certificate and private key can
    be validated as a matching pair signed by this installation's CA.
    """

    temp_cert = SSL_CERT_DIR / "mqtt-server.crt.new"
    temp_key = SSL_CERT_DIR / "mqtt-server.key.new"

    backup_cert = SSL_CERT_DIR / "mqtt-server.crt.bak"
    backup_key = SSL_CERT_DIR / "mqtt-server.key.bak"

    # ------------------------------------------------------------
    # 1. Temporary .new files are never considered authoritative.
    # ------------------------------------------------------------

    if temp_cert.exists() or temp_key.exists():
        logger.warning(
            "Temporary Mosquitto server certificate renewal files found; "
            "removing them"
        )

        temp_cert.unlink(missing_ok=True)
        temp_key.unlink(missing_ok=True)

    # ------------------------------------------------------------
    # 2. No backup files means no interrupted replacement to recover.
    # ------------------------------------------------------------

    if not backup_cert.exists() and not backup_key.exists():
        return

    logger.warning(
        "Mosquitto server certificate backup files found; "
        "checking for interrupted renewal"
    )

    # The installation CA must be trustworthy before using it to
    # validate either the live or backup server certificate.
    validate_certificate(CA_CERT)
    validate_key_matches_cert(CA_CERT, CA_KEY)

    # ------------------------------------------------------------
    # 3. If the live certificate/key form a valid pair, keep them.
    # ------------------------------------------------------------

    live_valid = False

    if SERVER_CERT.is_file() and SERVER_KEY.is_file():
        try:
            validate_certificate(SERVER_CERT)
            validate_key_matches_cert(SERVER_CERT, SERVER_KEY)
            validate_signed_by_ca(SERVER_CERT)
            live_valid = True

        except Exception:
            logger.warning(
                "Installed Mosquitto server certificate/key pair is not valid"
            )

    if live_valid:
        logger.info(
            "Installed Mosquitto server certificate/key pair is valid; "
            "discarding stale backup files"
        )

        backup_cert.unlink(missing_ok=True)
        backup_key.unlink(missing_ok=True)
        return

    # ------------------------------------------------------------
    # 4. Try to identify a valid old pair.
    #
    # During the backup operation there are two important possible
    # interrupted states:
    #
    #   backup certificate + live key
    #   backup certificate + backup key
    #
    # During rollback we may also encounter:
    #
    #   live certificate + backup key
    # ------------------------------------------------------------

    candidate_pairs = (
        (backup_cert, backup_key),
        (backup_cert, SERVER_KEY),
        (SERVER_CERT, backup_key),
    )

    recovery_cert = None
    recovery_key = None

    for cert_path, key_path in candidate_pairs:
        if not cert_path.is_file() or not key_path.is_file():
            continue

        try:
            validate_certificate(cert_path)
            validate_key_matches_cert(cert_path, key_path)
            validate_signed_by_ca(cert_path)

            recovery_cert = cert_path
            recovery_key = key_path
            break

        except Exception:
            continue

    if recovery_cert is None or recovery_key is None:
        raise RuntimeError(
            "Interrupted Mosquitto server certificate renewal detected, "
            "but no valid recoverable certificate/key pair was found"
        )

    logger.warning(
        "Recovering previous Mosquitto server certificate/key pair"
    )

    # Read the validated pair before changing any of the files. This is
    # important when one member of the pair is already at its live path.
    recovered_cert_bytes = recovery_cert.read_bytes()
    recovered_key_bytes = recovery_key.read_bytes()

    # Write the validated pair back to the normal live locations.
    SERVER_CERT.write_bytes(recovered_cert_bytes)
    SERVER_KEY.write_bytes(recovered_key_bytes)
    SERVER_KEY.chmod(0o600)

    # Validate what we actually installed.
    validate_certificate(SERVER_CERT)
    validate_key_matches_cert(SERVER_CERT, SERVER_KEY)
    validate_signed_by_ca(SERVER_CERT)

    # Recovery is complete, so backup files are no longer needed.
    backup_cert.unlink(missing_ok=True)
    backup_key.unlink(missing_ok=True)

    logger.info(
        "Interrupted Mosquitto server certificate renewal recovered successfully"
    )



def ensure_certificate_set() -> None:
    """
    Ensure that this installation has a complete MQTT certificate set.

    Behaviour:
      - Complete certificate set:
          Validate it and leave it unchanged.

      - No certificate files:
          Generate a new installation-specific CA, server certificate,
          and client certificate.

      - Valid CA exists but server/client certificates are missing:
          Recover safely by generating the missing certificate pairs
          using the existing CA.

      - Partial certificate/key pair or incomplete CA:
          Stop rather than replacing existing cryptographic material.
    """
    ensure_certificate_directories()

    # Recover any server certificate renewal that was interrupted by
    # an add-on restart, host restart, or power failure.
    recover_interrupted_server_renewal()

    status = certificate_status()

    # ------------------------------------------------------------
    # 1. Complete certificate set already exists
    # ------------------------------------------------------------
    if all(status.values()):
        logger.info("MQTT certificate set already exists")

        validate_certificate_set()

        logger.info("Existing MQTT certificate set validated successfully")
        return

    # ------------------------------------------------------------
    # 2. Nothing exists - completely new installation
    # ------------------------------------------------------------
    if not any(status.values()):
        logger.info(
            "No MQTT certificates found - generating new certificate set"
        )

        generate_ca()
        generate_server_certificate()
        generate_client_certificate()

        validate_certificate_set()

        logger.info(
            "MQTT certificate set generated and validated successfully"
        )
        return

    # ------------------------------------------------------------
    # 3. CA exists - possible interrupted certificate generation
    # ------------------------------------------------------------
    if status["ca_key"] and status["ca_cert"]:
        logger.warning(
            "Incomplete MQTT certificate set found - "
            "attempting safe recovery using existing local CA"
        )

        # Never use the existing CA unless its certificate is valid
        # and its private key matches.
        validate_certificate(CA_CERT)
        validate_key_matches_cert(CA_CERT, CA_KEY)

        # --------------------------------------------------------
        # Mosquitto server certificate
        # --------------------------------------------------------

        # A certificate without its key (or vice versa) is not safe
        # to repair automatically.
        if status["server_key"] != status["server_cert"]:
            raise RuntimeError(
                "Incomplete Mosquitto server certificate/key pair detected; "
                "automatic recovery has been stopped"
            )

        # Neither exists, so safely generate a new pair using
        # the existing installation CA.
        if not status["server_key"]:
            logger.info(
                "Mosquitto server certificate not found - generating it"
            )
            generate_server_certificate()

        # --------------------------------------------------------
        # Cytech Comfort client certificate
        # --------------------------------------------------------

        if status["client_key"] != status["client_cert"]:
            raise RuntimeError(
                "Incomplete Comfort client certificate/key pair detected; "
                "automatic recovery has been stopped"
            )

        if not status["client_key"]:
            logger.info(
                "Comfort MQTT client certificate not found - generating it"
            )
            generate_client_certificate()

        # --------------------------------------------------------
        # Validate the completed/recovered certificate set
        # --------------------------------------------------------

        validate_certificate_set()

        logger.info(
            "MQTT certificate set recovery completed successfully"
        )
        return

    # ------------------------------------------------------------
    # 4. Something exists, but there is not a complete CA
    # ------------------------------------------------------------

    missing = [
        name
        for name, exists in status.items()
        if not exists
    ]

    existing = [
        name
        for name, exists in status.items()
        if exists
    ]

    logger.error(
        "Incomplete MQTT certificate set. Existing: %s; Missing: %s",
        ", ".join(existing),
        ", ".join(missing),
    )

    raise RuntimeError(
        "Incomplete MQTT certificate set detected and a complete local CA "
        "is not available; automatic certificate generation has been stopped"
    )


def get_home_assistant_ipv4() -> ipaddress.IPv4Address:
    """
    Return the primary Home Assistant host IPv4 address.

    The address is obtained from the Home Assistant Supervisor network API,
    not from the add-on container's own Docker address.
    """

    token = os.getenv("SUPERVISOR_TOKEN")

    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN is not available")

    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.get(
            "http://supervisor/network/info",
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()

        payload = response.json()
        data = payload.get("data", payload)

        interfaces = data.get("interfaces", [])

        for interface in interfaces:
            if not interface.get("primary"):
                continue

            if not interface.get("enabled", True):
                continue

            if not interface.get("connected", True):
                continue

            ipv4 = interface.get("ipv4")

            if not ipv4:
                continue

            address = ipv4.get("ip_address")

            if not address:
                continue

            # Supervisor returns an address such as:
            # 192.168.1.50/24
            return ipaddress.ip_interface(address).ip

    except Exception as exc:
        raise RuntimeError(
            "Unable to determine Home Assistant primary IPv4 address"
        ) from exc

    raise RuntimeError(
        "No active primary Home Assistant IPv4 interface was found"
    )







if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    try:
        ensure_certificate_set()
        logger.info("Certificate setup completed successfully")
    except Exception:
        logger.exception("Certificate setup failed")
        raise