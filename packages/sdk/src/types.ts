export type ConversationMode = 'ai' | 'human';
export type ConversationStatus = 'open' | 'closed';
export type MessageSender = 'user' | 'ai' | 'agent' | 'system';
export type MessageStatus = 'generating' | 'completed' | 'failed';
export type HandoffStatus = 'pending' | 'accepted' | 'closed' | 'cancelled';
export type FeedbackRating = 'helpful' | 'unhelpful';
export type SupportedLocale = 'en' | 'zh-CN';

export interface Conversation {
  id: string;
  application_id: string;
  mode: ConversationMode;
  status: ConversationStatus;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  id: string;
  document_id: string;
  chunk_id: string;
  quote: string;
  source_title: string;
  source_url: string | null;
  score: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender: MessageSender;
  content: string;
  status: MessageStatus;
  error_code: string | null;
  citations: Citation[];
  created_at: string;
  updated_at: string;
}

export interface Handoff {
  id: string;
  application_id: string;
  conversation_id: string;
  assigned_staff_user_id: string | null;
  status: HandoffStatus;
  reason: string;
  summary: string;
  accepted_at: string | null;
  closed_at: string | null;
  close_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Feedback {
  id: string;
  application_id: string;
  conversation_id: string;
  message_id: string;
  rating: FeedbackRating;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export type StreamEvent =
  | { type: 'message.started'; data: { message_id: string; replay: boolean } }
  | { type: 'message.delta'; data: { delta: string } }
  | { type: 'message.completed'; data: Message }
  | { type: 'message.error'; data: { code: string; message: string } };
