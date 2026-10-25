"""
test_ledger_e2e.py - Automated verification test suite for ForexLedger and ledger.py.
"""
import os
import secrets
from datetime import datetime, timezone
import ledger

def test_ledger_suite():
    print("--- 1. Testing Hashing Utilities ---")
    record1 = {
        "timestamp": "2026-10-25T10:00:00Z",
        "pair": "EURUSD",
        "timeframe": "1mo",
        "model": "random_forest",
        "signal": "UP",
        "confidence": 0.725,
        "input_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "nonce": "a1b2c3d4e5f6",
    }
    # Verify canonical sorting (key order doesn't affect hash)
    record2 = dict(reversed(list(record1.items())))
    h1 = ledger.make_hash(record1)
    h2 = ledger.make_hash(record2)
    assert h1 == h2, f"Canonical JSON hash failed: {h1} != {h2}"
    print(f"Canonical hash test passed: {h1}")

    # Test file hashing
    readme_path = "requirements.txt"
    fh = ledger.hash_file(readme_path)
    assert len(fh) == 64
    print(f"File hash test passed ({readme_path}): {fh}")

    print("\n--- 2. Testing Ledger Smart Contract Connection ---")
    led = ledger.Ledger()
    print(f"Connected to chain. Contract address: {led._contract.address}")
    print(f"Owner address: {led._account.address}")

    print("\n--- 3. Testing anchor_model ---")
    dummy_model_hash = secrets.token_hex(32)
    info_model = led.anchor_model(dummy_model_hash)
    assert info_model["hash"] == dummy_model_hash
    assert "tx_hash" in info_model
    print(f"Model anchored: hash={dummy_model_hash[:16]}..., tx={info_model['tx_hash'][:16]}...")

    # Test duplicate hash rejection
    duplicate_failed = False
    try:
        led.anchor_model(dummy_model_hash)
    except Exception as e:
        duplicate_failed = True
        print(f"Duplicate model hash rejected as expected: {type(e).__name__}")
    assert duplicate_failed, "Duplicate model hash was not rejected!"

    print("\n--- 4. Testing anchor_signal ---")
    dummy_signal_nonce = secrets.token_hex(16)
    dummy_signal_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pair": "GBPUSD",
        "timeframe": "1y",
        "model": "random_forest",
        "signal": "DOWN",
        "confidence": 0.8123,
        "input_hash": dummy_model_hash,
        "nonce": dummy_signal_nonce,
    }
    dummy_signal_hash = ledger.make_hash(dummy_signal_record)
    info_signal = led.anchor_signal(dummy_signal_hash, record=dummy_signal_record, nonce=dummy_signal_nonce)
    assert info_signal["hash"] == dummy_signal_hash
    print(f"Signal anchored: hash={dummy_signal_hash[:16]}..., tx={info_signal['tx_hash'][:16]}...")

    # Test duplicate signal rejection
    duplicate_sig_failed = False
    try:
        led.anchor_signal(dummy_signal_hash)
    except Exception as e:
        duplicate_sig_failed = True
        print(f"Duplicate signal hash rejected as expected: {type(e).__name__}")
    assert duplicate_sig_failed, "Duplicate signal hash was not rejected!"

    print("\n--- 5. Testing verify() on-chain ---")
    # Verify model
    v_model = led.verify(dummy_model_hash)
    assert v_model["exists"] is True
    assert v_model["kind"] == "model"
    assert v_model["writer"].lower() == led._account.address.lower()
    assert v_model["timestamp"] > 0
    print(f"Verified model: exists={v_model['exists']}, kind={v_model['kind']}, timestamp={v_model['timestamp']}")

    # Verify with 0x prefix
    v_model_0x = led.verify("0x" + dummy_model_hash)
    assert v_model_0x["exists"] is True

    # Verify signal
    v_signal = led.verify(dummy_signal_hash)
    assert v_signal["exists"] is True
    assert v_signal["kind"] == "signal"
    assert v_signal["writer"].lower() == led._account.address.lower()
    print(f"Verified signal: exists={v_signal['exists']}, kind={v_signal['kind']}, timestamp={v_signal['timestamp']}")

    # Verify non-existent hash
    random_hash = secrets.token_hex(32)
    v_none = led.verify(random_hash)
    assert v_none["exists"] is False
    assert v_none["kind"] == "none"
    print(f"Verified non-existent: exists={v_none['exists']}, kind={v_none['kind']}")

    print("\n--- 6. Testing module-level functions ---")
    v_mod = ledger.verify(dummy_model_hash)
    assert v_mod["exists"] is True

    # Test DB retrieval
    record_db = led.get_record(dummy_signal_hash)
    assert record_db is not None
    assert record_db["nonce"] == dummy_signal_nonce
    print(f"Local database retrieval passed. Stored nonce: {record_db['nonce']}")

    print("\n🎉 ALL LEDGER TESTS PASSED SUCCESSFULLY! 🎉")

if __name__ == "__main__":
    test_ledger_suite()
