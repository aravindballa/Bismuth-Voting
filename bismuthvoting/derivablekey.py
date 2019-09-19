"""
A DerivableKey class for use with the Bismuth Governance Voting Protocol.
"""

import hmac
import struct
from six import int2byte
from hashlib import sha256, sha512
from coincurve import PrivateKey
from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes

from bismuthvoting.bip39 import BIP39


__version__ = "0.0.2"


FIELD_ORDER = 2 ** 256


# from ecdsa.ecdsa
def int_to_string(x):
    """Convert integer x into a string of bytes, as per X9.62."""
    assert x >= 0
    if x == 0:
        return b"\0"
    result = []
    while x:
        ordinal = x & 0xFF
        result.append(int2byte(ordinal))
        x >>= 8

    result.reverse()
    return b"".join(result)


def string_to_int(s):
    """Convert a string of bytes into an integer, as per X9.62."""
    result = 0
    for c in s:
        if not isinstance(c, int):
            c = ord(c)
        result = 256 * result + c
    return result


def random_padding(data: bytes, block_size: int=16, pad_with_zeros=False) -> bytes:
    padding_len = block_size-len(data)%block_size
    if pad_with_zeros:
        padding = b'\x00' * padding_len
    else:
        padding = get_random_bytes(padding_len)
    return data + padding


class DerivableKey:
    def __init__(self, entropy: bytes = None, seed: bytes = None):
        if seed is None:
            # reconstruct seed from entropy via BIP39
            assert entropy is not None
            bip39 = BIP39(entropy)
            self.seed = bip39.to_seed()
        else:
            self.seed = seed
        # seed is a 512 bits (kpar, cpar) privkey, code

    def to_pubkey(self) -> bytes:
        """Computes and sends back pubkey, point(kpar) of current key(kpar)"""
        kpar = PrivateKey.from_hex(self.seed[:32].hex())
        K = kpar.public_key.format(compressed=False)
        return K

    def to_aes_key(self) -> bytes:
        """Returns sha256 hash of the pubkey, to use as AES key"""
        pubkey = self.to_pubkey()
        return sha256(pubkey).digest()

    def derive(self, s: str) -> "DerivableKey":
        """Derive with given buffer"""
        data = self.to_pubkey().hex() + s
        I = hmac.new(self.seed[32:], data.encode("utf-8"), sha512).digest()
        IL, IR = I[:32], I[32:]
        ks_int = (
            string_to_int(IL) + string_to_int(self.seed[:32])
        ) % FIELD_ORDER
        ks = int_to_string(ks_int)
        cs = IR
        return DerivableKey(seed=ks + cs)

    @classmethod
    def encrypt(cls, aes_key: bytes, data: str, pad_with_zeroes=False, iv: bytes=None) -> bytes:
        assert len(aes_key) == 32
        # Add space to vote option
        data += " "
        data = data.encode('utf-8')
        # Pad to 16 bytes -
        data = random_padding(data, 16, pad_with_zeros=pad_with_zeroes)
        # print("padded data", data)
        # AES is stateful, needs one instance per operation
        if iv is None:
            # iv is needed for CBC, we use a fixed iv - 16 bytes long - to limit data to transmit by default.
            iv = "Bismuth BGVP IV.".encode('utf-8')
        aes = AES.new(aes_key, AES.MODE_CBC, iv=iv)
        encrypted = aes.encrypt(data)
        return encrypted

    @classmethod
    def decrypt(cls, aes_key: bytes, data: bytes, iv: bytes=None) -> str:
        assert len(aes_key) == 32
        # AES is stateful, needs one instance per operation
        if iv is None:
            # iv is needed for CBC, we use a fixed iv - 16 bytes long - to limit data to transmit by default.
            iv = "Bismuth BGVP IV.".encode('utf-8')
        aes = AES.new(aes_key, AES.MODE_CBC, iv=iv)
        clear = aes.decrypt(data)
        # print(clear)
        clear, _ = clear.split(b" ")
        return clear.decode("utf-8")

