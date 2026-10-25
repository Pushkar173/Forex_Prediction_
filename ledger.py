"""
ledger.py – Blockchain audit layer for Forex Prediction Project.

Compiles and deploys contracts/ForexLedger.sol, then exposes helpers
to anchor SHA-256 hashes on-chain and verify them later.

Chain connection priority:
  1. Ganache / any local JSON-RPC read from .env (RPC_URL, PRIVATE_KEY)
  2. eth-tester in-memory chain (automatic fallback for dev/testing)

Mainnet is explicitly refused so you never accidentally anchor there.
"""

import os
import json
import hashlib
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from web3 import Web3
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

_PROJECT_DIR = Path(__file__).resolve().parent
_CONTRACT_SRC = _PROJECT_DIR / "contracts" / "ForexLedger.sol"
_COMPILED_ABI = _PROJECT_DIR / "contracts" / "ForexLedger_abi.json"
_COMPILED_BIN = _PROJECT_DIR / "contracts" / "ForexLedger_bin.txt"
_DB_PATH      = _PROJECT_DIR / "ledger.db"

# ---------------------------------------------------------------------------
# SQLite helpers (shared by main.py and app.py, multi-thread safe)
# ---------------------------------------------------------------------------

_db_lock = threading.Lock()

def _get_db(path=None):
    """Open (and lazily create) the ledger database safely across threads."""
    db_path = path or str(_DB_PATH)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    with _db_lock:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS anchors (
                hash         TEXT PRIMARY KEY,
                kind         TEXT NOT NULL,           -- 'model' or 'signal'
                tx_hash      TEXT,
                block_number INTEGER,
                anchored     INTEGER DEFAULT 1,       -- 0 = not anchored, 1 = anchored
                record_json  TEXT,                     -- full signal record (signals only)
                salt         TEXT,                     -- random nonce / salt
                created_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    return conn

# ---------------------------------------------------------------------------
# Hashing & String utilities
# ---------------------------------------------------------------------------

def _clean_hash(hex_hash: str) -> str:
    """Normalize hex hash: strip whitespace and optional 0x/0X prefix."""
    h = hex_hash.strip()
    if h.startswith("0x") or h.startswith("0X"):
        h = h[2:]
    if len(h) != 64:
        raise ValueError(f"Invalid SHA-256 hash length ({len(h)} characters, expected 64 hex chars).")
    return h.lower()

def make_hash(record: dict) -> str:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)."""
    canonical = json.dumps(record, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def hash_file(path: str) -> str:
    """SHA-256 of a file's raw bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

# ---------------------------------------------------------------------------
# Compilation (uses py-solc-x to get the right solc binary)
# ---------------------------------------------------------------------------

def _compile_contract():
    """Compile ForexLedger.sol and cache ABI + bytecode on disk."""
    if _COMPILED_ABI.exists() and _COMPILED_BIN.exists():
        abi = json.loads(_COMPILED_ABI.read_text())
        bytecode = _COMPILED_BIN.read_text().strip()
        return abi, bytecode

    from solcx import install_solc, compile_source  # type: ignore

    solc_version = "0.8.24"
    install_solc(solc_version, show_progress=False)

    source = _CONTRACT_SRC.read_text()
    compiled = compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version=solc_version,
    )

    contract_key = [k for k in compiled if "ForexLedger" in k][0]
    abi      = compiled[contract_key]["abi"]
    bytecode = compiled[contract_key]["bin"]

    _COMPILED_ABI.write_text(json.dumps(abi, indent=2))
    _COMPILED_BIN.write_text(bytecode)

    return abi, bytecode

# ---------------------------------------------------------------------------
# Chain connection
# ---------------------------------------------------------------------------

_MAINNET_IDS = {1, 56, 137, 42161, 10, 43114, 250}
_shared_tester_provider = None

def _connect():
    """
    Return (w3, account) using .env settings or eth-tester fallback.

    Environment variables (loaded from .env):
      RPC_URL     – e.g. http://127.0.0.1:8545
      PRIVATE_KEY – hex-encoded private key
    """
    global _shared_tester_provider
    load_dotenv(_PROJECT_DIR / ".env")
    rpc_url     = os.getenv("RPC_URL")
    private_key = os.getenv("PRIVATE_KEY")

    if rpc_url and private_key:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if w3.is_connected():
            chain_id = w3.eth.chain_id
            if chain_id in _MAINNET_IDS:
                raise RuntimeError(
                    f"Refusing to run on Ethereum mainnet (chain_id={chain_id}). "
                    "Use a local devnet or testnet."
                )
            account = w3.eth.account.from_key(private_key)
            return w3, account

    # Fallback: in-memory eth-tester chain (shared within process)
    if _shared_tester_provider is None:
        try:
            from web3 import EthereumTesterProvider  # type: ignore
            _shared_tester_provider = EthereumTesterProvider()
        except ImportError:
            from eth_tester import EthereumTester  # type: ignore
            from web3.providers.eth_tester import EthereumTesterProvider as ETP  # type: ignore
            _shared_tester_provider = ETP(EthereumTester())

    w3 = Web3(_shared_tester_provider)

    class _FakeAccount:
        def __init__(self, addr):
            self.address = addr
    account = _FakeAccount(w3.eth.accounts[0])

    return w3, account

# ---------------------------------------------------------------------------
# Deployment & contract instance
# ---------------------------------------------------------------------------

_DEPLOY_CACHE = _PROJECT_DIR / "contracts" / ".deployed_address"

def _deploy_or_load(w3, account):
    """Deploy ForexLedger (or reuse a previously deployed address)."""
    abi, bytecode = _compile_contract()
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    if _DEPLOY_CACHE.exists():
        addr = _DEPLOY_CACHE.read_text().strip()
        if w3.is_address(addr):
            code = w3.eth.get_code(Web3.to_checksum_address(addr))
            if code and code != b"" and code != b"\x00":
                return w3.eth.contract(
                    address=Web3.to_checksum_address(addr), abi=abi
                )

    tx = Contract.constructor().build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 2_000_000,
        "gasPrice": w3.eth.gas_price,
    })

    if hasattr(account, "sign_transaction"):
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    else:
        tx_hash = w3.eth.send_transaction(tx)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    address = receipt.contractAddress

    _DEPLOY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _DEPLOY_CACHE.write_text(address)

    return w3.eth.contract(address=address, abi=abi)

# ---------------------------------------------------------------------------
# Ledger Class
# ---------------------------------------------------------------------------

class Ledger:
    """
    High-level wrapper around the ForexLedger smart contract.

    Usage:
        ledger = Ledger()
        h = ledger.hash_file("models/random_forest.pkl")
        tx = ledger.anchor_model(h)
        result = ledger.verify(h)
    """

    def __init__(self):
        self.w3, self._account = _connect()
        self._contract = _deploy_or_load(self.w3, self._account)
        self._db = _get_db()
        self._lock = _db_lock
        self._tx_lock = threading.Lock()

    @staticmethod
    def make_hash(record: dict) -> str:
        return make_hash(record)

    @staticmethod
    def hash_file(path: str) -> str:
        return hash_file(path)

    def _send_tx(self, fn):
        """Build, sign (if needed), send, and wait for receipt safely across threads."""
        with self._tx_lock:
            tx = fn.build_transaction({
                "from": self._account.address,
                "nonce": self.w3.eth.get_transaction_count(self._account.address),
                "gas": 200_000,
                "gasPrice": self.w3.eth.gas_price,
            })
            if hasattr(self._account, "sign_transaction"):
                signed = self._account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            else:
                tx_hash = self.w3.eth.send_transaction(tx)

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.get("status") == 0:
                tx_repr = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
                raise RuntimeError(f"Transaction reverted on-chain (status=0): {tx_repr}")
            return receipt

    # -- write operations --

    def anchor_model(self, hex_hash: str) -> dict:
        """Register a model hash on chain. Returns receipt info dict."""
        clean_h = _clean_hash(hex_hash)
        existing = self.verify(clean_h)
        if existing["exists"]:
            raise ValueError(f"Duplicate hash rejected: model hash {clean_h} is already registered on-chain.")

        h_bytes = bytes.fromhex(clean_h)
        receipt = self._send_tx(
            self._contract.functions.registerModel(h_bytes)
        )
        tx_hex = receipt.transactionHash.hex()
        if not tx_hex.startswith("0x"):
            tx_hex = "0x" + tx_hex

        info = {
            "hash": clean_h,
            "tx_hash": tx_hex,
            "block_number": receipt.blockNumber,
        }
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO anchors (hash, kind, tx_hash, block_number, anchored)"
                " VALUES (?, 'model', ?, ?, 1)",
                (clean_h, info["tx_hash"], info["block_number"]),
            )
            self._db.commit()
        return info

    def anchor_signal(self, hex_hash: str, record: dict = None,
                      nonce: str = None, salt: str = None) -> dict:
        """Record a prediction-signal hash on chain. Returns receipt info dict."""
        clean_h = _clean_hash(hex_hash)
        existing = self.verify(clean_h)
        if existing["exists"]:
            raise ValueError(f"Duplicate hash rejected: signal hash {clean_h} is already registered on-chain.")

        effective_nonce = nonce or salt
        h_bytes = bytes.fromhex(clean_h)
        receipt = self._send_tx(
            self._contract.functions.recordSignal(h_bytes)
        )
        tx_hex = receipt.transactionHash.hex()
        if not tx_hex.startswith("0x"):
            tx_hex = "0x" + tx_hex

        info = {
            "hash": clean_h,
            "tx_hash": tx_hex,
            "block_number": receipt.blockNumber,
        }
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO anchors "
                "(hash, kind, tx_hash, block_number, anchored, record_json, salt)"
                " VALUES (?, 'signal', ?, ?, 1, ?, ?)",
                (
                    clean_h,
                    info["tx_hash"],
                    info["block_number"],
                    json.dumps(record, sort_keys=True) if record else None,
                    effective_nonce,
                ),
            )
            self._db.commit()
        return info

    # -- read operations --

    def verify(self, hex_hash: str) -> dict:
        """
        Call the on-chain verify() and return a dict:
          exists (bool), kind ('model'/'signal'/'none'), writer (address), timestamp (int)
        """
        clean_h = _clean_hash(hex_hash)
        h_bytes = bytes.fromhex(clean_h)
        exists, kind_enum, writer, ts = self._contract.functions.verify(
            h_bytes
        ).call()
        kind_map = {0: "none", 1: "model", 2: "signal"}
        return {
            "exists": exists,
            "kind": kind_map.get(kind_enum, "none"),
            "writer": writer,
            "timestamp": ts,
        }

    def get_record(self, hex_hash: str) -> Optional[dict]:
        """Fetch the full record from SQLite."""
        clean_h = _clean_hash(hex_hash)
        with self._lock:
            row = self._db.execute(
                "SELECT record_json, salt, tx_hash, block_number, anchored, kind "
                "FROM anchors WHERE hash = ?",
                (clean_h,),
            ).fetchone()
        if row is None:
            return None
        return {
            "record_json": row[0],
            "nonce": row[1],
            "salt": row[1],
            "tx_hash": row[2],
            "block_number": row[3],
            "anchored": bool(row[4]),
            "kind": row[5],
        }

    def save_unanchored(self, hex_hash: str, kind: str,
                        record: dict = None, nonce: str = None, salt: str = None):
        """Save a record locally when the chain is unreachable."""
        clean_h = _clean_hash(hex_hash)
        effective_nonce = nonce or salt
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO anchors "
                "(hash, kind, tx_hash, block_number, anchored, record_json, salt)"
                " VALUES (?, ?, NULL, NULL, 0, ?, ?)",
                (
                    clean_h,
                    kind,
                    json.dumps(record, sort_keys=True) if record else None,
                    effective_nonce,
                ),
            )
            self._db.commit()


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

_default_ledger: Optional[Ledger] = None

def get_ledger() -> Ledger:
    """Return a shared Ledger instance."""
    global _default_ledger
    if _default_ledger is None:
        _default_ledger = Ledger()
    return _default_ledger

def anchor_model(hex_hash: str) -> dict:
    """Convenience function to anchor a model hash using the default ledger."""
    return get_ledger().anchor_model(hex_hash)

def anchor_signal(hex_hash: str, record: dict = None,
                  nonce: str = None, salt: str = None) -> dict:
    """Convenience function to anchor a signal hash using the default ledger."""
    return get_ledger().anchor_signal(hex_hash, record=record, nonce=nonce, salt=salt)

def verify(hex_hash: str) -> dict:
    """Convenience function to verify a hash using the default ledger."""
    return get_ledger().verify(hex_hash)
