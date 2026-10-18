"""
License activation — verifies a signed activation key issued by the
developer's own license_key_generator.py tool, using the SAME ECDSA
scheme (SECP256R1 / SHA-256), message format ("<fingerprint>|<expiration>"),
and key format ("<expiration>:<base64url signature, no padding>") that tool
produces. The generator and its license_private_key.pem NEVER ship with
this app — only the PUBLIC key below does, which lets this code verify a
signature but never create one. See license_key_generator.py's own
docstring (the developer keeps that file and its .pem private) for the
full workflow this pairs with:

  1. This device shows its fingerprint() below.
  2. The owner sends that fingerprint to the developer (by whatever
     channel — chat, email).
  3. The developer runs license_key_generator.py, pastes the fingerprint,
     picks a duration, and sends back the resulting activation key.
  4. The owner activates it here: Pulse-Setup.exe license <key>.

The fingerprint is Windows' own per-install MachineGuid (no admin rights
needed to read it) — stable across reboots/reinstalls of this app, but
unique per Windows installation, so a key issued for one PC's Windows
install cannot be reused on another. The Inno Setup installer reads the
exact same registry value directly (see installer/pulse_setup.iss) so the
fingerprint it displays during setup matches this one exactly.
"""
import winreg
import base64
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

from . import db

# The PUBLIC half of license_private_key.pem (derived once with
# `priv.public_key()`, never the other way around). Safe to ship — it can
# only verify signatures, never produce one.
_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9hskm3ufgTN+cmD+Vhzv2w6OIiuw
RL/YjNVP/aJaT05+91ZOAv634CJt812D8dP5TtfS6XpAeHRX8ALMi95b9Q==
-----END PUBLIC KEY-----
"""

_public_key = serialization.load_pem_public_key(_PUBLIC_KEY_PEM)


def fingerprint():
    """Windows' own per-install identifier — readable by any user, no
    admin needed. Matches installer/pulse_setup.iss's GetMachineFingerprint
    exactly (same registry value, same uppercase-no-dashes formatting)."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography', 0,
                             winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            guid, _ = winreg.QueryValueEx(key, 'MachineGuid')
        return guid.strip().upper().replace('-', '')
    except Exception:
        return 'UNKNOWN-DEVICE'


def verify(license_key, fp):
    """Returns (expiration, error) — error is None on success, 'EXPIRED' if
    the signature is valid but the date has passed, or a short message for
    anything else wrong with the key."""
    if not license_key or ':' not in license_key:
        return None, 'bad_format'
    exp, sig_b64 = license_key.strip().split(':', 1)
    pad = '=' * (-len(sig_b64) % 4)
    try:
        signature = base64.urlsafe_b64decode(sig_b64 + pad)
    except Exception:
        return None, 'bad_encoding'

    message = f'{fp.strip().upper()}|{exp}'.encode('utf-8')
    try:
        _public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return None, 'invalid_signature'

    if exp != 'PERMANENT':
        try:
            exp_date = datetime.strptime(exp, '%Y%m%d')
        except ValueError:
            return None, 'bad_expiration'
        if datetime.now() > exp_date:
            return exp, 'EXPIRED'
    return exp, None


def activate(license_key):
    """Verifies the key against THIS device's fingerprint and, if valid
    (even if already expired — so status/`license` can still report
    exactly what's wrong), stores it. Returns (ok, exp, error)."""
    exp, err = verify(license_key, fingerprint())
    if err and err != 'EXPIRED':
        return False, None, err
    db.put('license_key', license_key.strip())
    return err != 'EXPIRED', exp, err


def status():
    """Re-validates the stored key fresh every call (never trusts a cached
    yes/no) so an expiration date that has since passed is always caught.
    Returns (licensed: bool, state: str, exp: str|None) where state is one
    of 'ok', 'no_license', 'expired', 'invalid'."""
    key = db.get_str('license_key')
    if not key:
        return False, 'no_license', None
    exp, err = verify(key, fingerprint())
    if err == 'EXPIRED':
        return False, 'expired', exp
    if err:
        return False, 'invalid', None
    return True, 'ok', exp


def is_licensed():
    licensed, _, _ = status()
    return licensed
