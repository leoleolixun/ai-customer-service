export interface AdminMe {
  id: string;
  email: string;
  is_platform_admin: boolean;
  tenant_id: string | null;
  role: 'tenant_admin' | 'agent' | null;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  status: 'active' | 'disabled';
  created_at: string;
  updated_at: string;
}

export interface Application {
  id: string;
  tenant_id: string;
  name: string;
  public_key: string;
  allowed_origins: string[];
  rate_limit_per_minute: number;
  status: 'active' | 'disabled';
  created_at: string;
  updated_at: string;
}

export interface ApiCredential {
  id: string;
  application_id: string;
  key_prefix: string;
  scopes: string[];
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface ProviderAccount {
  id: string;
  tenant_id: string | null;
  scope: 'platform' | 'tenant';
  name: string;
  kind: 'fake' | 'openai_compatible';
  base_url: string | null;
  has_api_key: boolean;
  can_manage: boolean;
  status: 'draft' | 'ready' | 'disabled';
  created_at: string;
  updated_at: string;
}

export interface ModelConfig {
  id: string;
  tenant_id: string;
  provider_account_id: string;
  name: string;
  model_name: string;
  purpose: 'chat' | 'embedding';
  embedding_dimension: number | null;
  temperature: number;
  max_tokens: number;
  thinking_mode: 'provider_default' | 'disabled' | 'enabled';
  status: 'inactive' | 'active';
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  embedding_model_config_id: string;
  embedding_model_name: string;
  embedding_dimension: number;
  embedding_version: string;
  chunking_version: string;
  keyword_score_threshold: number;
  vector_similarity_threshold: number;
  status: 'active' | 'disabled';
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocument {
  id: string;
  knowledge_base_id: string;
  supersedes_document_id: string | null;
  version: number;
  title: string;
  source_filename: string;
  source_url: string | null;
  mime_type: string;
  byte_size: number;
  content_hash: string;
  status: 'uploaded' | 'processing' | 'ready' | 'failed' | 'disabled' | 'deleted';
  error_message: string | null;
  can_restore: boolean;
  restore_block_reason:
    | 'document_restore_base_disabled'
    | 'document_restore_version_conflict'
    | null;
  created_at: string;
  updated_at: string;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_title: string;
  source_url: string | null;
  content: string;
  heading_path: string[];
  score: number;
  vector_similarity: number;
  keyword_score: number;
}

export interface Member {
  id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: 'tenant_admin' | 'agent';
  status: 'active' | 'disabled';
  created_at: string;
}

export interface Handoff {
  id: string;
  application_id: string;
  conversation_id: string;
  assigned_staff_user_id: string | null;
  status: 'pending' | 'accepted' | 'closed' | 'cancelled';
  reason: string;
  summary: string;
  accepted_at: string | null;
  closed_at: string | null;
  close_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  id: string;
  source_title: string;
  source_url: string | null;
  quote: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender: 'user' | 'ai' | 'agent' | 'system';
  content: string;
  status: 'generating' | 'completed' | 'failed';
  error_code: string | null;
  citations: Citation[];
  created_at: string;
  updated_at: string;
}

export interface AdminConversation {
  id: string;
  application_id: string;
  end_user_id: string;
  external_user_id: string;
  mode: 'ai' | 'human';
  status: 'open' | 'closed';
  created_at: string;
  updated_at: string;
}

export interface AdminConversationPage {
  items: AdminConversation[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface AdminMessage extends Message {
  model_info: Record<string, unknown>;
}

export interface AdminMessagePage {
  items: AdminMessage[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface UsageSummary {
  from_at: string;
  to_at: string;
  application_id: string | null;
  total_requests: number;
  completed_requests: number;
  failed_requests: number;
  prompt_tokens: number;
  completion_tokens: number;
  average_duration_ms: number;
  estimated_cost_micros: number;
}

export interface ModelCall {
  id: string;
  application_id: string;
  conversation_id: string;
  message_id: string;
  model_config_id: string;
  model_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  duration_ms: number;
  estimated_cost_micros: number;
  status: 'completed' | 'failed';
  error_code: string | null;
  created_at: string;
}

export interface AuditLog {
  id: string;
  actor_type: string;
  actor_id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  request_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ConversationFeedback {
  id: string;
  application_id: string;
  conversation_id: string;
  message_id: string;
  rating: 'helpful' | 'unhelpful';
  comment: string | null;
  message_excerpt: string;
  created_at: string;
  updated_at: string;
}
