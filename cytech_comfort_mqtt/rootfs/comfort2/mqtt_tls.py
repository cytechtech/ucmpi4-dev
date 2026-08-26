# Copyright (c) 2026 Cytech Technology Pte Ltd
#
# MQTT TLS helpers shared by the Comfort bridge and ingress web UI.

import logging
import os
import ssl
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key

logger = logging.getLogger("mqtt_tls")

SSL_ROOT = Path("/ssl")


def certificate_path(filename: str | None) -> Path | None:
    """Return a certificate path below /ssl, rejecting path traversal."""
    if filename is None or not str(filename).strip():
        return None

    relative = Path(str(filename).strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Invalid certificate path: {filename!r}")

    return SSL_ROOT / relative


def validate_certificate(path: Path | None) -> None:
    """Raise RuntimeError if a PEM certificate is missing, invalid or expired."""
    if path is None:
        raise RuntimeError("Certificate filename is not configured")
    if not path.is_file():
        raise RuntimeError(f"Certificate not found: {path}")

    try:
        cert = x509.load_pem_x509_certificate(path.read_bytes(), default_backend())
    except Exception as exc:
        raise RuntimeError(f"Certificate is corrupt or invalid: {path}") from exc

    now = datetime.now(timezone.utc)
    valid_from = cert.not_valid_before_utc
    valid_to = cert.not_valid_after_utc
    if not (valid_from <= now < valid_to):
        raise RuntimeError(
            f"Certificate is outside its validity period: {path} "
            f"({valid_from.isoformat()} to {valid_to.isoformat()})"
        )


def validate_key_matches_cert(cert_path: Path, key_path: Path) -> None:
    """Raise RuntimeError unless a private key matches its certificate."""
    if not key_path.is_file():
        raise RuntimeError(f"Private key not found: {key_path}")

    try:
        private_key = load_pem_private_key(
            key_path.read_bytes(), password=None, backend=default_backend()
        )
        cert = x509.load_pem_x509_certificate(
            cert_path.read_bytes(), default_backend()
        )
    except Exception as exc:
        raise RuntimeError(
            f"Unable to read certificate/private key: {cert_path}, {key_path}"
    ) from exc

    cert_public_key = cert.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    if cert_public_key != key_public_key:
        raise RuntimeError(
        f"Private key does not match certificate: {cert_path}"
    )

def configure_client_tls(
    client,
    *,
    enabled: bool,
    mutual_tls: bool,
    ca_filename: str | None,
    client_cert_filename: str | None = None,
    client_key_filename: str | None = None,
) -> None:
    """Configure a Paho MQTT client for verified TLS/mTLS.

    TLS is fail-closed: if enabled and the certificate configuration is invalid,
    this function raises and the caller must not reconnect using plaintext MQTT.
    """
    if not enabled:
        return

    ca_path = certificate_path(ca_filename)
    validate_certificate(ca_path)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.load_verify_locations(cafile=os.fspath(ca_path))

    if mutual_tls:
        cert_path = certificate_path(client_cert_filename)
        key_path = certificate_path(client_key_filename)
        validate_certificate(cert_path)
        if key_path is None:
            raise RuntimeError("MQTT client private key filename is not configured")
        validate_key_matches_cert(cert_path, key_path)
        context.load_cert_chain(certfile=os.fspath(cert_path), keyfile=os.fspath(key_path))
        logger.info("MQTT mutual TLS configured with client certificate %s", cert_path)
    else:
        logger.info("MQTT server-authenticated TLS configured with CA %s", ca_path)

    client.tls_set_context(context)
    client.tls_insecure_set(False)
