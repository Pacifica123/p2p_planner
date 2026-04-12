use super::dto::{
    DomainEventSubscription, IntegrationProviderDetailResponse, IntegrationProviderSummary,
    IntegrationTouchpoint, WebhookContract,
};

pub trait IntegrationProvider: Send + Sync {
    fn manifest(&self) -> IntegrationProviderDetailResponse;
}

pub struct ObsidianProvider;
pub struct GithubProvider;
pub struct ImportExportProvider;
pub struct WebhookBridgeProvider;

impl IntegrationProvider for ObsidianProvider {
    fn manifest(&self) -> IntegrationProviderDetailResponse {
        IntegrationProviderDetailResponse {
            provider: IntegrationProviderSummary {
                key: "obsidian".to_string(),
                display_name: "Obsidian Vault Adapter".to_string(),
                provider_type: "third_party".to_string(),
                status: "stub".to_string(),
                auth_mode: "local_filesystem".to_string(),
                supports_import: true,
                supports_export: true,
                supports_inbound_webhooks: false,
                supports_outbound_webhooks: false,
            },
            import_touchpoints: vec![IntegrationTouchpoint {
                key: "vault_markdown_import".to_string(),
                direction: "import".to_string(),
                payload_format: "markdown_bundle".to_string(),
                description: "Import boards, cards and notes from an Obsidian vault snapshot without coupling core domain services to markdown parsing.".to_string(),
                status: "stub".to_string(),
            }],
            export_touchpoints: vec![IntegrationTouchpoint {
                key: "vault_markdown_export".to_string(),
                direction: "export".to_string(),
                payload_format: "markdown_bundle".to_string(),
                description: "Export selected workspace or board data into markdown files that can later be mapped to an Obsidian vault.".to_string(),
                status: "stub".to_string(),
            }],
            domain_event_subscriptions: vec![
                DomainEventSubscription {
                    event_type: "board.snapshot.requested".to_string(),
                    delivery_mode: "pull".to_string(),
                    purpose: "Build markdown-friendly board snapshots for export jobs.".to_string(),
                },
                DomainEventSubscription {
                    event_type: "card.changed".to_string(),
                    delivery_mode: "batch".to_string(),
                    purpose: "Prepare note regeneration without leaking markdown concerns into card services.".to_string(),
                },
            ],
            inbound_webhook: None,
            outbound_webhook: None,
            boundary_rules: vec![
                "Obsidian-specific file layout lives inside the adapter and never inside board/card services.".to_string(),
                "Import produces normalized domain commands instead of direct table writes.".to_string(),
            ],
            notes: vec![
                "Stub provider for future vault import/export.".to_string(),
                "No filesystem access is wired in the current backend build.".to_string(),
            ],
        }
    }
}

impl IntegrationProvider for GithubProvider {
    fn manifest(&self) -> IntegrationProviderDetailResponse {
        IntegrationProviderDetailResponse {
            provider: IntegrationProviderSummary {
                key: "github".to_string(),
                display_name: "GitHub Adapter".to_string(),
                provider_type: "third_party".to_string(),
                status: "stub".to_string(),
                auth_mode: "oauth_or_pat".to_string(),
                supports_import: true,
                supports_export: true,
                supports_inbound_webhooks: true,
                supports_outbound_webhooks: false,
            },
            import_touchpoints: vec![IntegrationTouchpoint {
                key: "issues_import".to_string(),
                direction: "import".to_string(),
                payload_format: "github_rest_or_graphql".to_string(),
                description: "Import issues, labels or project items into normalized planner entities through adapter-owned mapping rules.".to_string(),
                status: "stub".to_string(),
            }],
            export_touchpoints: vec![IntegrationTouchpoint {
                key: "issues_export".to_string(),
                direction: "export".to_string(),
                payload_format: "github_rest_or_graphql".to_string(),
                description: "Publish selected planner records back to GitHub issues or project fields without embedding GitHub DTOs into the core domain.".to_string(),
                status: "stub".to_string(),
            }],
            domain_event_subscriptions: vec![
                DomainEventSubscription {
                    event_type: "card.created".to_string(),
                    delivery_mode: "outbox".to_string(),
                    purpose: "Future issue creation mirror.".to_string(),
                },
                DomainEventSubscription {
                    event_type: "card.updated".to_string(),
                    delivery_mode: "outbox".to_string(),
                    purpose: "Future issue field synchronization.".to_string(),
                },
            ],
            inbound_webhook: Some(WebhookContract {
                mode: "inbound".to_string(),
                signature_scheme: "hmac_sha256".to_string(),
                event_types: vec![
                    "issues".to_string(),
                    "issue_comment".to_string(),
                    "projects_v2_item".to_string(),
                ],
                description: "Reserved webhook receiver contract for GitHub events. The receiver exists as a stub and must later translate external payloads into validated integration commands.".to_string(),
            }),
            outbound_webhook: None,
            boundary_rules: vec![
                "GitHub credentials and rate limiting stay inside the adapter boundary.".to_string(),
                "Core services emit neutral domain events instead of GitHub-specific DTOs.".to_string(),
            ],
            notes: vec![
                "Stub provider for future GitHub issues/projects integration.".to_string(),
                "No OAuth, PAT storage or webhook verification is implemented yet.".to_string(),
            ],
        }
    }
}

impl IntegrationProvider for ImportExportProvider {
    fn manifest(&self) -> IntegrationProviderDetailResponse {
        IntegrationProviderDetailResponse {
            provider: IntegrationProviderSummary {
                key: "import_export".to_string(),
                display_name: "Generic Import / Export Adapter".to_string(),
                provider_type: "system".to_string(),
                status: "stub".to_string(),
                auth_mode: "local_user_context".to_string(),
                supports_import: true,
                supports_export: true,
                supports_inbound_webhooks: false,
                supports_outbound_webhooks: false,
            },
            import_touchpoints: vec![IntegrationTouchpoint {
                key: "json_snapshot_import".to_string(),
                direction: "import".to_string(),
                payload_format: "p2p_planner_bundle_v1".to_string(),
                description: "Import a portable project bundle through the same integration orchestration layer that future third-party providers will use.".to_string(),
                status: "stub".to_string(),
            }],
            export_touchpoints: vec![IntegrationTouchpoint {
                key: "json_snapshot_export".to_string(),
                direction: "export".to_string(),
                payload_format: "p2p_planner_bundle_v1".to_string(),
                description: "Export workspace or board snapshots for backup, transfer or offline archiving without leaking file packaging logic into domain modules.".to_string(),
                status: "stub".to_string(),
            }],
            domain_event_subscriptions: vec![DomainEventSubscription {
                event_type: "workspace.snapshot.requested".to_string(),
                delivery_mode: "pull".to_string(),
                purpose: "Prepare portable export bundles and restore flows.".to_string(),
            }],
            inbound_webhook: None,
            outbound_webhook: None,
            boundary_rules: vec![
                "Portable file formats are versioned integration contracts, not direct database dumps.".to_string(),
                "Restore/import must go through validated application commands and conflict-aware reconciliation.".to_string(),
            ],
            notes: vec![
                "System-level adapter for future import/export and backup flows.".to_string(),
            ],
        }
    }
}

impl IntegrationProvider for WebhookBridgeProvider {
    fn manifest(&self) -> IntegrationProviderDetailResponse {
        IntegrationProviderDetailResponse {
            provider: IntegrationProviderSummary {
                key: "webhooks".to_string(),
                display_name: "Webhook Bridge Adapter".to_string(),
                provider_type: "system".to_string(),
                status: "stub".to_string(),
                auth_mode: "signing_secret".to_string(),
                supports_import: false,
                supports_export: true,
                supports_inbound_webhooks: true,
                supports_outbound_webhooks: true,
            },
            import_touchpoints: vec![],
            export_touchpoints: vec![IntegrationTouchpoint {
                key: "domain_event_outbox".to_string(),
                direction: "export".to_string(),
                payload_format: "json_webhook_event".to_string(),
                description: "Reserve an outbox-style push contract for selected domain events without making board/card services aware of HTTP delivery semantics.".to_string(),
                status: "stub".to_string(),
            }],
            domain_event_subscriptions: vec![
                DomainEventSubscription {
                    event_type: "workspace.changed".to_string(),
                    delivery_mode: "outbox".to_string(),
                    purpose: "Notify external systems about workspace-level changes.".to_string(),
                },
                DomainEventSubscription {
                    event_type: "board.changed".to_string(),
                    delivery_mode: "outbox".to_string(),
                    purpose: "Notify automation systems about board-level lifecycle changes.".to_string(),
                },
                DomainEventSubscription {
                    event_type: "card.changed".to_string(),
                    delivery_mode: "outbox".to_string(),
                    purpose: "Notify automation systems about card lifecycle and field updates.".to_string(),
                },
            ],
            inbound_webhook: Some(WebhookContract {
                mode: "inbound".to_string(),
                signature_scheme: "hmac_sha256".to_string(),
                event_types: vec!["generic.event".to_string()],
                description: "Reserved incoming webhook boundary for trusted external automation systems.".to_string(),
            }),
            outbound_webhook: Some(WebhookContract {
                mode: "outbound".to_string(),
                signature_scheme: "hmac_sha256".to_string(),
                event_types: vec![
                    "workspace.changed".to_string(),
                    "board.changed".to_string(),
                    "card.changed".to_string(),
                ],
                description: "Reserved outgoing webhook contract with signing secret and retriable delivery semantics.".to_string(),
            }),
            boundary_rules: vec![
                "Webhook retries, signatures and delivery history live in the adapter boundary, not in core CRUD services.".to_string(),
                "External webhook payloads must be translated into validated integration commands before touching domain state.".to_string(),
            ],
            notes: vec![
                "System adapter for inbound and outbound webhooks.".to_string(),
            ],
        }
    }
}

pub fn builtin_providers() -> Vec<Box<dyn IntegrationProvider>> {
    vec![
        Box::new(ObsidianProvider),
        Box::new(GithubProvider),
        Box::new(ImportExportProvider),
        Box::new(WebhookBridgeProvider),
    ]
}

pub fn find_provider(provider_key: &str) -> Option<IntegrationProviderDetailResponse> {
    builtin_providers().into_iter().find_map(|provider| {
        let manifest = provider.manifest();
        (manifest.provider.key == provider_key).then_some(manifest)
    })
}
