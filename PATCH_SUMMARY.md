# Fix reqwest JSON build and roaming catalog recovery

Base: supplied snapshot `ec0ea8c`.

Fixes the network-recovery path using the supplied 2.1.0 sources. Web enables reqwest JSON and retains its updated Cargo.lock, rejects compile errors as retryable network failures, supervises roaming worker startup and filters catalogs by recipient. Android polls catalogs independently of HTTP/type of network, merges discovered boards into the visible list, permits scoped introductions from trusted peers, applies only the newest authenticated catalog, refuses stale epochs/key changes and invalid relay quorums, and validates received relay filter scope. Provisioned board reads no longer wait for a private HTTP endpoint.

No schema or wire-protocol change, profile reset, session clearing or re-import. Documentation contains update order and explicit cross-network/offline acceptance. devctl gates stay dependency-download-free; compiled/typechecked/Jest evidence is separate. Real smartphone/Docker/PostgreSQL/ISP testing is pending.

Rollback: devctl source rollback. User data/keys/queues are not bundled or erased. Existing pending journal is retained when relay quorum is unavailable.
