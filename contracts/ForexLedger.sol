// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ForexLedger – immutable audit trail for model & signal hashes
/// @notice Only the deployer (owner) can write. Duplicate hashes are rejected.
contract ForexLedger {

    // --- Types -----------------------------------------------------------

    enum Kind { None, Model, Signal }

    struct Entry {
        Kind   kind;
        address writer;
        uint256 timestamp;
    }

    // --- State -----------------------------------------------------------

    address public immutable owner;
    mapping(bytes32 => Entry) private _entries;

    // --- Events ----------------------------------------------------------

    event ModelRegistered(bytes32 indexed hash, address writer, uint256 timestamp);
    event SignalRecorded(bytes32  indexed hash, address writer, uint256 timestamp);

    // --- Errors ----------------------------------------------------------

    error OnlyOwner();
    error DuplicateHash(bytes32 hash);

    // --- Constructor -----------------------------------------------------

    constructor() {
        owner = msg.sender;
    }

    // --- Modifiers -------------------------------------------------------

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    modifier noDuplicate(bytes32 hash) {
        if (_entries[hash].kind != Kind.None) revert DuplicateHash(hash);
        _;
    }

    // --- Write functions -------------------------------------------------

    /// @notice Register a model-file hash on chain.
    function registerModel(bytes32 hash)
        external onlyOwner noDuplicate(hash)
    {
        _entries[hash] = Entry(Kind.Model, msg.sender, block.timestamp);
        emit ModelRegistered(hash, msg.sender, block.timestamp);
    }

    /// @notice Record a prediction-signal hash on chain.
    function recordSignal(bytes32 hash)
        external onlyOwner noDuplicate(hash)
    {
        _entries[hash] = Entry(Kind.Signal, msg.sender, block.timestamp);
        emit SignalRecorded(hash, msg.sender, block.timestamp);
    }

    // --- Read functions --------------------------------------------------

    /// @notice Look up a hash. Returns (exists, kind, writer, timestamp).
    function verify(bytes32 hash)
        external view
        returns (bool exists, Kind kind, address writer, uint256 timestamp)
    {
        Entry storage e = _entries[hash];
        if (e.kind == Kind.None) {
            return (false, Kind.None, address(0), 0);
        }
        return (true, e.kind, e.writer, e.timestamp);
    }
}
