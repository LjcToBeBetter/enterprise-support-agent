import type { AnswerResult, Page } from '../types';

const TOKEN_KEY = 'support.session.token';
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (value: string) => sessionStorage.setItem(TOKEN_KEY, value),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

/** 保留后端错误码和请求编号，页面既能显示中文原因，也便于查日志。 */
export class ApiError extends Error {
  constructor(message: string, public status = 0, public requestId?: string, public code?: string, public retryAfter?: string) { super(message); }
}

async function checkedFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  const token = tokenStore.get();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  let response: Response;
  try { response = await fetch(`/api${path}`, { ...options, headers }); }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('无法连接后端，请确认后端服务已启动。');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== '/auth/login') {
      tokenStore.clear(); window.dispatchEvent(new Event('session-expired'));
    }
    throw new ApiError(data.message || data.detail || `请求失败（${response.status}）`, response.status, data.request_id, data.code, response.headers.get('Retry-After') || undefined);
  }
  return response;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await checkedFetch(path, options);
  if (response.status === 204) return undefined as T;
  return response.json();
}
export const jsonBody = (value: unknown) => JSON.stringify(value);

/** 拉取真实分页数据，组织下拉框、成员选择等不只显示第一页。 */
export async function allPages<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const items: T[] = [];
  let page = 1;
  while (true) {
    const result = await api<Page<T>>(`${path}${path.includes('?') ? '&' : '?'}page=${page}&page_size=100`, { signal });
    items.push(...result.items);
    if (page >= result.total_pages || result.items.length === 0) return items;
    page += 1;
  }
}

/** 下载同样携带JWT，再把后端返回的文件交给浏览器保存。 */
export async function downloadDocument(orgId: string, id: string, filename: string) {
  const response = await checkedFetch(`/organizations/${orgId}/documents/${id}/download`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** SSE可以在任意字节位置分段：先积累完整事件，再解析JSON，不能直接逐网络块JSON.parse。 */
export class SseDecoder {
  private buffer = '';
  push(text: string): { event: string; data: unknown }[] {
    this.buffer += text;
    const frames: { event: string; data: unknown }[] = [];
    let match: RegExpExecArray | null;
    while ((match = /\r?\n\r?\n/.exec(this.buffer))) {
      const block = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      let event = 'message'; const lines: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) lines.push(line.slice(5).replace(/^ /, ''));
      }
      if (lines.length) frames.push({ event, data: JSON.parse(lines.join('\n')) });
    }
    return frames;
  }
}

export async function streamAnswer(orgId: string, body: unknown, signal: AbortSignal, onDelta: (text: string) => void): Promise<AnswerResult> {
  const response = await checkedFetch(`/organizations/${orgId}/knowledge/answer/stream`, { method: 'POST', body: jsonBody(body), signal });
  if (!response.body) throw new ApiError('浏览器无法读取回答流，请切换普通问答。');
  const reader = response.body.getReader(); const decoder = new TextDecoder(); const parser = new SseDecoder();
  let result: AnswerResult | undefined;
  try {
    while (true) {
      const { value, done } = await reader.read();
      const frames = parser.push(decoder.decode(value, { stream: !done }));
      for (const frame of frames) {
        if (frame.event === 'delta') onDelta((frame.data as { text: string }).text);
        if (frame.event === 'error') {
          const error = frame.data as { message: string; request_id?: string; code?: string };
          throw new ApiError(error.message, 502, error.request_id, error.code);
        }
        if (frame.event === 'done') result = frame.data as AnswerResult;
      }
      if (result || done) break;
    }
    // 只有收到done才能把临时文字当作最终答案；中断不能当成功。
    if (!result) throw new ApiError('回答连接中断，未收到完成确认，请重新提问。');
    return result;
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
