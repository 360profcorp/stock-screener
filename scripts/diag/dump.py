"""Read-only diagnostic: decrypt state/trader.enc, drop the Schwab token, encrypt the copy
with a one-off public key (hybrid RSA-OAEP + Fernet) -> scripts/diag/out.bin. Never writes
state/trader.enc."""
import hashlib, json, os, sys
sys.path.insert(0, os.getcwd())
import vault
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

raw = open(vault.STATE_PATH, "rb").read()
st = vault.decrypt(raw, os.environ["STATE_PASSWORD"])
tok = st.pop("token", None)
st["_token_present"] = tok is not None
st["_enc_sha256"] = hashlib.sha256(raw).hexdigest()
data = json.dumps(st, default=str).encode()
k = Fernet.generate_key()
pub = serialization.load_pem_public_key(open("scripts/diag/pub.pem", "rb").read())
wk = pub.encrypt(k, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
open("scripts/diag/out.bin", "wb").write(len(wk).to_bytes(2, "big") + wk + Fernet(k).encrypt(data))
print("ok", len(data), "bytes; enc sha", st["_enc_sha256"][:12])
