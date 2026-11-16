/** 与现有FastAPI响应对应的类型，避免把组织ID、文档ID和任务ID混用。 */
export interface User { id: string; email: string; display_name: string; is_active: boolean }
export interface Organization { id: string; name: string; code: string; is_active: boolean }
export type Role = 'employee' | 'support' | 'admin';
export interface Membership { id: string; organization_id: string; user_id: string; role: Role }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number; total_pages: number }
export interface KnowledgeDocument { id: string; organization_id: string; original_filename: string; file_size_bytes: number; content_type: string; status: string; version: number; error_message: string | null; created_at: string; updated_at: string }
export interface ProcessingJob { id: string; document_id: string; organization_id: string; status: 'pending'|'queued'|'running'|'succeeded'|'failed'; attempt_count: number; max_attempts: number; error_message: string | null; started_at: string | null; finished_at: string | null }
export type TicketStatus = 'open'|'in_progress'|'resolved'|'closed';
export type Priority = 'low'|'medium'|'high'|'urgent';
export interface Ticket { id: string; organization_id: string; creator_user_id: string; assignee_user_id: string | null; title: string; description: string; priority: Priority; status: TicketStatus; created_at: string; updated_at: string }
export interface Conversation { id: string; title: string; organization_id: string; user_id: string; created_at: string }
export interface PendingApproval { tool_call_id: string; tool_name: 'create_ticket'; arguments: { title: string; description: string; priority: Priority } }
export interface AgentResult { status: 'completed'|'awaiting_approval'; answer: string | null; tool_call_count: number; conversation_id: string; pending_approval: PendingApproval | null }
/** 后端存档中的当前任务状态；页面刷新后仍以它为准。 */
export interface AgentExecutionState { conversation_id: string; execution_id: string | null; status: 'idle'|'running'|'failed'|'awaiting_approval'|'completed'; can_retry: boolean; allow_ticket_creation: boolean | null; answer: string | null; tool_call_count: number; pending_approval: PendingApproval | null; message: string | null }
export interface SearchHit { chunk_id: string; document_id: string; document_version: number; page_number: number; chunk_index: number; content: string; rrf_score: number; vector_score: number | null; bm25_score: number | null; rerank_score: number | null; rerank_rank: number | null }
export interface SearchResult { query: string; items: SearchHit[]; returned_count: number }
export interface AnswerSource { source_number: number; chunk_id: string; document_id: string; page_number: number; content: string; rerank_score: number | null }
export interface AnswerResult { query: string; answer: string; sources: AnswerSource[]; used_source_count: number; no_answer: boolean }
