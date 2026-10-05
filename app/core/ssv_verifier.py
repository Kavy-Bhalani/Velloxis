import base64
import logging
import time
from typing import Dict, Any, Optional
import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.backends import default_backend
from app.core.config import get_settings

logger = logging.getLogger("velloxis.ssv")
settings = get_settings()

_ADMOB_KEYS_CACHE: Dict[int, Any] = {}
_ADMOB_KEYS_EXPIRY: float = 0.0

async def fetch_admob_public_keys() -> Dict[int, Any]:
    global _ADMOB_KEYS_CACHE, _ADMOB_KEYS_EXPIRY
    now = time.time()
    if _ADMOB_KEYS_CACHE and now < _ADMOB_KEYS_EXPIRY:
        return _ADMOB_KEYS_CACHE

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(settings.ADMOB_KEY_URL)
            if resp.status_code == 200:
                data = resp.json()
                keys_dict = {}
                for key_entry in data.get("keys", []):
                    key_id = key_entry.get("keyId")
                    pem_base64 = key_entry.get("pem")
                    if key_id and pem_base64:
                        from cryptography.hazmat.primitives.serialization import load_pem_public_key
                        pub_key = load_pem_public_key(pem_base64.encode("utf-8"), backend=default_backend())
                        keys_dict[int(key_id)] = pub_key

                _ADMOB_KEYS_CACHE = keys_dict
                _ADMOB_KEYS_EXPIRY = now + (24 * 3600)  # Cache 24 hours
                return _ADMOB_KEYS_CACHE
    except Exception as e:
        logger.error(f"Error fetching AdMob SSV public keys: {e}")

    return _ADMOB_KEYS_CACHE

async def verify_admob_ssv(query_string: str, query_params: Dict[str, str]) -> bool:
    """
    Verifies the cryptographic signature of an AdMob SSV callback.
    """
    if settings.DEV_BYPASS_AUTH:
        return True

    signature_str = query_params.get("signature")
    key_id_str = query_params.get("key_id")

    if not signature_str or not key_id_str:
        logger.warning("SSV callback missing signature or key_id.")
        return False

    try:
        key_id = int(key_id_str)
        keys = await fetch_admob_public_keys()
        public_key = keys.get(key_id)
        if not public_key:
            logger.warning(f"AdMob key_id {key_id} not found in public keys.")
            return False

        # Construct message content: standard AdMob query string up to &signature=
        # e.g., ad_network=...&ad_unit=...&custom_data=...&key_id=...&reward_amount=...
        sig_index = query_string.find("&signature=")
        if sig_index != -1:
            data_to_verify = query_string[:sig_index].encode("utf-8")
        else:
            # Fallback if signature isn't at the end
            parts = [f"{k}={v}" for k, v in query_params.items() if k != "signature"]
            data_to_verify = "&".join(parts).encode("utf-8")

        raw_signature = base64.urlsafe_b64decode(signature_str + "==")

        # AdMob uses ECDSA with SHA-256 (ASN.1 DER or IEEE P1363)
        try:
            public_key.verify(raw_signature, data_to_verify, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            # Try decoding as raw (r, s) if standard DER fails
            if len(raw_signature) == 64:
                from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
                r = int.from_bytes(raw_signature[:32], byteorder="big")
                s = int.from_bytes(raw_signature[32:], byteorder="big")
                der_signature = encode_dss_signature(r, s)
                public_key.verify(der_signature, data_to_verify, ec.ECDSA(hashes.SHA256()))
                return True
            raise

    except Exception as e:
        logger.warning(f"AdMob SSV verification failed: {e}")
        return False
