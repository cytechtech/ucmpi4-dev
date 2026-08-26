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