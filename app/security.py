import base64
import os
import time
import hashlib
from argon2 import PasswordHasher
from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

hasher = PasswordHasher()

def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()

class Vault:
    """Master key never leaves memory; no server-key fallback for vault secrets."""
    def __init__(self, store):
        self.store = store
        self.keys = {}

    def derive(self, password, salt):
        return hash_secret_raw(password.encode(), salt, time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, type=Type.ID)

    def setup(self, password):
        if self.store.config('vault'): raise HTTPException(409, 'Vault already configured')
        if len(password) < 12: raise HTTPException(400, 'Use at least 12 characters')
        salt = os.urandom(16)
        key = self.derive(password, salt)
        nonce = os.urandom(12)
        self.store.set_config('vault', {'salt':base64.b64encode(salt).decode(), 'check':base64.b64encode(nonce + AESGCM(key).encrypt(nonce, b'tgtop-vault-v1', None)).decode()})

    def unlock(self, session, password):
        config = self.store.config('vault')
        if not config: raise HTTPException(400, 'Set up the vault first')
        key = self.derive(password, base64.b64decode(config['salt']))
        check = base64.b64decode(config['check'])
        try: AESGCM(key).decrypt(check[:12], check[12:], None)
        except Exception: raise HTTPException(403, 'Unable to unlock vault')
        self.keys[session] = (bytearray(key), time.monotonic() + 300)

    def lock(self, session):
        value = self.keys.pop(session, None)
        if value:
            for i in range(len(value[0])): value[0][i] = 0

    def key(self, session):
        value = self.keys.get(session)
        if not value or value[1] < time.monotonic():
            self.lock(session)
            raise HTTPException(423, 'Vault locked; explicitly unlock first')
        return bytes(value[0])

    def seal(self, session, text, id):
        key = self.key(session)
        nonce = os.urandom(12)
        return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, text.encode(), id.encode())).decode()

    def reveal(self, session, record):
        key = self.key(session)
        blob = base64.b64decode(record['ciphertext'])
        return AESGCM(key).decrypt(blob[:12], blob[12:], record['id'].encode()).decode()
