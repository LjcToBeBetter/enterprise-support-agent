import { Alert, Empty, Skeleton, Tag, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ApiError } from '../api/client';

export const roleNames: Record<string, string> = { admin: '管理员', support: '技术支持', employee: '成员' };
export const statusNames: Record<string, string> = { pending: '待发送', queued: '排队中', running: '处理中', succeeded: '处理成功', failed: '处理失败', processing: '处理中', parsed: '已解析', chunked: '已切块', ready: '可检索', open: '待处理', in_progress: '处理中', resolved: '已解决', closed: '已关闭' };
export const priorityNames: Record<string, string> = { low: '低', medium: '中', high: '高', urgent: '紧急' };
export const dateText = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';
export function StatusTag({ value }: { value: string }) {
  const color = ['ready', 'succeeded', 'resolved'].includes(value) ? 'success' : value === 'failed' ? 'error' : ['processing','running','in_progress'].includes(value) ? 'processing' : ['pending','queued','open'].includes(value) ? 'warning' : 'default';
  return <Tag color={color}>{statusNames[value] || value}</Tag>;
}
export function ErrorNotice({ error, onClose }: { error: unknown; onClose?: () => void }) {
  if (!error) return null;
  const value = error instanceof Error ? error.message : String(error);
  return <Alert className="error-notice" type="error" showIcon closable={!!onClose} onClose={onClose} message={value} description={error instanceof ApiError && error.requestId ? <>请求编号：<Typography.Text copyable>{error.requestId}</Typography.Text></> : undefined} />;
}
export function Markdown({ children }: { children: string }) { return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown></div>; }
export function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action && <div className="heading-action">{action}</div>}</div>;
}
export function LoadingPage() { return <div className="surface page-loading"><Skeleton active paragraph={{ rows: 5 }} /></div>; }
export function EmptyPanel({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) { return <div className="empty-panel"><Empty description={<><h3>{title}</h3><p>{description}</p></>} />{action}</div>; }
export function IdText({ value }: { value: string }) { return <Typography.Text className="id-text" copyable={{ text: value }} title={value}>{value.slice(0, 8)}…</Typography.Text>; }
