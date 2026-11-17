"""Owner/harness signing for approvals and critic evidence (Ed25519).

Public-key signatures separate the two jobs:

* the PRIVATE key signs. Only the Project Owner and the trusted harness use
  it. Keep it outside every working copy, chmod 600, and ideally owned by a
  different OS user from the one the agents run as;
* the PUBLIC key verifies. The dispatcher, pre-launch hook and evidence
  checker only ever need this, so giving agents' tools the public key does
  not let them forge approvals or evidence.

Requires the ``cryptography`` package (pip install cryptography).
"""
import base64
import hashlib
import json
import os
from pathlib import Path

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (Ed25519PrivateKey,
                                                                   Ed25519PublicKey)
except ImportError:  # pragma: no cover - reported clearly at use time
    Ed25519PrivateKey = None

ALGORITHM = 'Ed25519'


def _require_crypto():
    if Ed25519PrivateKey is None:
        raise ValueError('Signing needs the cryptography package: pip install cryptography')


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _not_inside(path, folders):
    path = Path(path).resolve()
    for folder in folders:
        folder = Path(folder).resolve()
        if path == folder or folder in path.parents:
            raise ValueError('Signing keys must not be inside the working copy or project')
    return path


def fingerprint(public_key_or_path):
    """SHA-256 of the raw public key; pin this value in host configuration."""
    _require_crypto()
    key = public_key_or_path
    if not isinstance(key, Ed25519PublicKey):
        key = serialization.load_pem_public_key(Path(key).read_bytes())
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def create_keypair(private_path, public_path, passphrase=None):
    _require_crypto()
    private_path, public_path = Path(private_path), Path(public_path)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.BestAvailableEncryption(passphrase)
                                       if passphrase else serialization.NoEncryption()))
    fd = os.open(public_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo))
    return private_path, public_path


def load_private_key(path, *, not_inside=(), passphrase=None, require_encrypted=False):
    _require_crypto()
    path = _not_inside(path, not_inside)
    if not path.is_file():
        raise ValueError('Private signing key missing')
    if os.name == 'posix' and path.stat().st_mode & 0o077:
        raise ValueError('Private signing key is readable by other users; run chmod 600 on it')
    data = path.read_bytes()
    encrypted = b'ENCRYPTED' in data.split(b'\n', 1)[0]
    if require_encrypted and not encrypted:
        raise ValueError('Owner signing key must be passphrase-protected')
    try:
        key = serialization.load_pem_private_key(data, password=passphrase if encrypted else None)
    except (TypeError, ValueError):
        raise ValueError('Private signing key could not be unlocked (wrong or missing passphrase)')
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Private signing key is not Ed25519')
    return key


def load_public_key(path, *, not_inside=()):
    _require_crypto()
    path = _not_inside(path, not_inside)
    if not path.is_file():
        raise ValueError('Public verification key missing')
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError('Public verification key is not Ed25519')
    return key


def _body(obj):
    return canonical({k: v for k, v in obj.items() if k != 'signature'})


def sign(obj, private_key):
    return base64.b64encode(private_key.sign(_body(obj))).decode('ascii')


def attach(obj, private_key):
    return {**{k: v for k, v in obj.items() if k != 'signature'},
            'signature': {'alg': ALGORITHM, 'value': sign(obj, private_key)}}


def verify(obj, public_key):
    signature = obj.get('signature') if isinstance(obj, dict) else None
    if not isinstance(signature, dict) or signature.get('alg') != ALGORITHM:
        return False
    try:
        public_key.verify(base64.b64decode(signature.get('value', ''), validate=True), _body(obj))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Create an owner or harness signing key pair')
    parser.add_argument('private_key', help='Private key path (owner only, outside any working copy)')
    parser.add_argument('public_key', help='Public key path (safe to give to checkers)')
    parser.add_argument('--role', choices=('owner', 'harness'), required=True,
                        help='owner keys are always passphrase-protected')
    args = parser.parse_args()
    passphrase = None
    if args.role == 'owner':
        import getpass
        passphrase = getpass.getpass('New owner key passphrase: ').encode('utf-8')
        if passphrase != getpass.getpass('Repeat passphrase: ').encode('utf-8') or len(passphrase) < 12:
            raise SystemExit('Passphrases differ or shorter than 12 characters')
    private_path, public_path = create_keypair(args.private_key, args.public_key, passphrase)
    print(json.dumps({'role': args.role, 'private_key': str(private_path),
                      'public_key': str(public_path),
                      'fingerprint_to_pin': fingerprint(public_path)}, indent=2))
