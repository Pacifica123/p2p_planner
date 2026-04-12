export interface PageInfo {
  nextCursor?: string | null;
  prevCursor?: string | null;
  hasNextPage?: boolean;
  hasPrevPage?: boolean;
}

export interface Workspace {
  id: string;
  name: string;
  slug?: string | null;
  description?: string | null;
  visibility: 'private' | 'shared';
  ownerUserId: string;
  memberCount?: number;
  isArchived: boolean;
  createdAt: string;
  updatedAt: string;
  archivedAt?: string | null;
}

export interface WorkspaceListResponse {
  items: Workspace[];
  pageInfo: PageInfo;
}

export interface Board {
  id: string;
  workspaceId: string;
  name: string;
  description?: string | null;
  boardType: 'kanban';
  isArchived: boolean;
  createdAt: string;
  updatedAt: string;
  archivedAt?: string | null;
}

export interface BoardListResponse {
  items: Board[];
  pageInfo: PageInfo;
}

export interface BoardColumn {
  id: string;
  boardId: string;
  name: string;
  description?: string | null;
  position: number;
  colorToken?: string | null;
  wipLimit?: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface ColumnListResponse {
  items: BoardColumn[];
}

export type CardStatus = 'todo' | 'in_progress' | 'blocked' | 'done' | null;
export type CardPriority = 'low' | 'medium' | 'high' | 'urgent' | null;

export interface Card {
  id: string;
  boardId: string;
  columnId: string;
  parentCardId?: string | null;
  title: string;
  description?: string | null;
  status: CardStatus;
  priority: CardPriority;
  position: number;
  startAt?: string | null;
  dueAt?: string | null;
  completedAt?: string | null;
  isArchived: boolean;
  labelIds?: string[];
  checklistCount?: number;
  checklistCompletedItemCount?: number;
  commentCount?: number;
  createdByUserId?: string | null;
  createdAt: string;
  updatedAt: string;
  archivedAt?: string | null;
}

export interface CardListResponse {
  items: Card[];
  pageInfo: PageInfo;
}

export interface ActivityActor {
  userId: string | null;
  displayName: string | null;
}

export interface ActivityEntry {
  id: string;
  createdAt: string;
  kind: string;
  workspaceId: string;
  boardId: string;
  cardId: string | null;
  entityType: string;
  entityId: string;
  actor: ActivityActor;
  fieldMask: string[];
  payload: Record<string, unknown>;
  requestId: string | null;
}

export interface ActivityListResponse {
  items: ActivityEntry[];
  nextCursor: string | null;
}


export type AppTheme = 'system' | 'light' | 'dark';
export type Density = 'comfortable' | 'compact';
export type WallpaperKind = 'none' | 'solid' | 'gradient' | 'preset';
export type CardPreviewMode = 'compact' | 'expanded';

export interface WallpaperConfig {
  kind: WallpaperKind;
  value?: string | null;
}

export interface UserAppearancePreferences {
  userId: string;
  isCustomized: boolean;
  appTheme: AppTheme;
  density: Density;
  reduceMotion: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface UpdateUserAppearancePreferencesRequest {
  appTheme?: AppTheme;
  density?: Density;
  reduceMotion?: boolean;
}

export interface BoardAppearanceSettings {
  boardId: string;
  isCustomized: boolean;
  themePreset: string;
  wallpaper: WallpaperConfig;
  columnDensity: Density;
  cardPreviewMode: CardPreviewMode;
  showCardDescription: boolean;
  showCardDates: boolean;
  showChecklistProgress: boolean;
  customProperties: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface UpdateBoardAppearanceRequest {
  themePreset?: string;
  wallpaper?: WallpaperConfig;
  columnDensity?: Density;
  cardPreviewMode?: CardPreviewMode;
  showCardDescription?: boolean;
  showCardDates?: boolean;
  showChecklistProgress?: boolean;
  customProperties?: Record<string, unknown>;
}


export interface IntegrationProviderSummary {
  key: string;
  displayName: string;
  providerType: 'third_party' | 'system';
  status: 'stub' | 'planned' | 'active';
  authMode: string;
  supportsImport: boolean;
  supportsExport: boolean;
  supportsInboundWebhooks: boolean;
  supportsOutboundWebhooks: boolean;
}

export interface IntegrationTouchpoint {
  key: string;
  direction: 'import' | 'export' | 'bidirectional';
  payloadFormat: string;
  description: string;
  status: 'stub' | 'planned' | 'active';
}

export interface DomainEventSubscription {
  eventType: string;
  deliveryMode: 'pull' | 'batch' | 'outbox' | 'push';
  purpose: string;
}

export interface WebhookContract {
  mode: 'inbound' | 'outbound';
  signatureScheme: string;
  eventTypes: string[];
  description: string;
}

export interface IntegrationProviderCatalogResponse {
  items: IntegrationProviderSummary[];
}

export interface IntegrationProviderDetailResponse {
  provider: IntegrationProviderSummary;
  importTouchpoints: IntegrationTouchpoint[];
  exportTouchpoints: IntegrationTouchpoint[];
  domainEventSubscriptions: DomainEventSubscription[];
  inboundWebhook?: WebhookContract | null;
  outboundWebhook?: WebhookContract | null;
  boundaryRules: string[];
  notes: string[];
}

export interface CreateImportJobRequest {
  providerKey: string;
  workspaceId?: string | null;
  sourceRef?: string | null;
  options?: Record<string, unknown>;
}

export interface CreateExportJobRequest {
  providerKey: string;
  workspaceId?: string | null;
  targetRef?: string | null;
  options?: Record<string, unknown>;
}

export interface IntegrationOperationStubResponse {
  operation: string;
  providerKey: string;
  status: 'stub_only';
  message: string;
}

export interface WebhookReceiptResponse {
  providerKey: string;
  status: 'stub_only';
  message: string;
  acceptedEventTypes: string[];
}
