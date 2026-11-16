import { useEffect, useRef, useState } from 'react';
import { App, Button, Empty, Form, Input, Modal, Select, Space, Switch, Tag, Tooltip, Typography } from 'antd';
import { ArrowRightOutlined, CheckOutlined, CloseOutlined, FileSearchOutlined, FolderOpenOutlined, LinkOutlined, PlusOutlined, ReloadOutlined, SendOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { api, jsonBody } from '../api/client';
import type { AgentExecutionState, AgentResult, Conversation, PendingApproval } from '../types';
import { EmptyPanel, ErrorNotice, IdText, Markdown, PageHeading, priorityNames } from '../components/ui';
import { useWorkspace } from '../app/workspace';

interface ChatMessage { id: string; role: 'user'|'assistant'; content: string; tools?: number }
interface LocalConversation { conversation: Conversation; messages: ChatMessage[]; pending: PendingApproval | null; execution?: AgentExecutionState; creationAllowed?: boolean }

/** 后端保存真实Agent状态；本浏览器保留会话入口和已展示的消息，按用户及组织分开。 */
export function AgentPage() {
  const { organizationId, organization, user, organizationsLoading } = useWorkspace();
  const { message } = App.useApp();
  const storageKey = `support.conversations.${user!.id}.${organizationId}`;
  const [conversations, setConversations] = useState<LocalConversation[]>(() => {
    try { return JSON.parse(localStorage.getItem(storageKey) || '[]'); } catch { return []; }
  });
  const [activeId, setActiveId] = useState(() => conversations[0]?.conversation.id || '');
  const [query, setQuery] = useState(''); const [allowCreate, setAllowCreate] = useState(() => conversations[0]?.creationAllowed ?? false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>();
  const [checking, setChecking] = useState(false);
  // 较早的状态请求不能盖掉刚完成的发送、重试或审批结果。
  const statusVersions = useRef<Record<string, number>>({});
  const [createOpen, setCreateOpen] = useState(false); const [restoreOpen, setRestoreOpen] = useState(false);
  const [legacyRetryOpen, setLegacyRetryOpen] = useState(false);
  const [modalBusy, setModalBusy] = useState(false); const [modalError, setModalError] = useState<unknown>();
  const controller = useRef<AbortController | null>(null); const bottom = useRef<HTMLDivElement>(null);
  const active = conversations.find(item => item.conversation.id === activeId);
  useEffect(() => { try { localStorage.setItem(storageKey, JSON.stringify(conversations)); } catch { /* 存储满时仍允许继续当前对话。 */ } }, [conversations, storageKey]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!active?.messages.length && !active?.pending && !busy) return;
    // 只滚动消息区，不把整个页面和输入框一起滚走。
    const area = bottom.current?.parentElement;
    if (area) area.scrollTo({ top: area.scrollHeight, behavior: 'smooth' });
  }, [active?.messages.length, active?.pending, busy]);
  const changeConversation = (id: string, update: (value: LocalConversation) => LocalConversation) => setConversations(values => values.map(value => value.conversation.id === id ? update(value) : value));
  const invalidateStatus = (id: string) => { statusVersions.current[id] = (statusVersions.current[id] || 0) + 1; };
  const refreshExecution = async (id: string, signal?: AbortSignal, restoreAuthorization = false) => {
    invalidateStatus(id); const version = statusVersions.current[id];
    const state = await api<AgentExecutionState>(`/organizations/${organizationId}/agent/conversations/${id}/execution`, { signal });
    if (signal?.aborted || statusVersions.current[id] !== version) return;
    if (state.status === 'completed' || state.status === 'awaiting_approval') setError(undefined);
    // 进入会话时从后端恢复已记录的授权；后台轮询不覆盖用户刚切换的开关。
    if (restoreAuthorization && typeof state.allow_ticket_creation === 'boolean') setAllowCreate(state.allow_ticket_creation);
    changeConversation(id, value => {
      const last = value.messages.at(-1);
      // 响应丢失后查到已完成结果，只补展示一次，不再次运行任务。
      const showAnswer = state.status === 'completed' && state.answer && !(last?.role === 'assistant' && last.content === state.answer);
      return { ...value, execution: state,
        creationAllowed: restoreAuthorization && typeof state.allow_ticket_creation === 'boolean' ? state.allow_ticket_creation : value.creationAllowed,
        pending: state.status === 'running' ? value.pending : state.pending_approval,
        messages: showAnswer ? [...value.messages, { id: crypto.randomUUID(), role: 'assistant', content: state.answer!, tools: state.tool_call_count }] : value.messages,
      };
    });
  };
  const checkExecution = async () => {
    if (!activeId || busy || checking) return;
    setChecking(true);
    try { await refreshExecution(activeId); }
    catch (reason) { setError(reason); }
    finally { setChecking(false); }
  };
  useEffect(() => {
    setLegacyRetryOpen(false);
    if (!activeId || busy) return;
    const savedChoice = conversations.find(value => value.conversation.id === activeId)?.creationAllowed;
    setAllowCreate(savedChoice ?? false);
    const abort = new AbortController(); setChecking(true);
    void refreshExecution(activeId, abort.signal, savedChoice === undefined).catch(reason => { if (!abort.signal.aborted) setError(reason); }).finally(() => { if (!abort.signal.aborted) setChecking(false); });
    return () => { abort.abort(); invalidateStatus(activeId); setChecking(false); };
  }, [activeId]);
  useEffect(() => {
    if (!activeId || busy || active?.execution?.status !== 'running') return;
    const abort = new AbortController();
    const timer = setInterval(() => { void refreshExecution(activeId, abort.signal).catch(reason => { if (!abort.signal.aborted) setError(reason); }); }, 3000);
    return () => { clearInterval(timer); abort.abort(); };
  }, [activeId, active?.execution?.status, busy]);
  const createConversation = async (title = '新会话', creationAllowed = false) => {
    const conversation = await api<Conversation>(`/organizations/${organizationId}/agent/conversations`, { method: 'POST', body: jsonBody({ title }) });
    setConversations(values => [{ conversation, messages: [], pending: null, creationAllowed }, ...values]); setActiveId(conversation.id); setAllowCreate(creationAllowed); setError(undefined);
    return conversation;
  };
  const applyResult = (result: AgentResult) => {
    invalidateStatus(result.conversation_id);
    changeConversation(result.conversation_id, value => ({ ...value, execution: undefined, pending: result.pending_approval, messages: result.answer ? [...value.messages, { id: crypto.randomUUID(), role: 'assistant', content: result.answer, tools: result.tool_call_count }] : value.messages }));
  };
  const send = async (text = query) => {
    if (!text.trim() || busy || checking || active?.pending || ['failed', 'running'].includes(active?.execution?.status || '')) return;
    const prompt = text.trim(); setBusy(true); setError(undefined);
    const abort = new AbortController(); controller.current = abort;
    let targetId = activeId;
    try {
      const conversation = active?.conversation || await createConversation(prompt.slice(0, 30), allowCreate);
      if (abort.signal.aborted) return;
      targetId = conversation.id; invalidateStatus(targetId);
      changeConversation(conversation.id, value => ({ ...value, execution: undefined, messages: [...value.messages, { id: crypto.randomUUID(), role: 'user', content: prompt }] })); setQuery('');
      const result = await api<AgentResult>(`/organizations/${organizationId}/agent/chat`, { method: 'POST', signal: abort.signal, body: jsonBody({ query: prompt, allow_ticket_creation: allowCreate, conversation_id: conversation.id }) });
      applyResult(result);
    } catch (reason) { if (!abort.signal.aborted) { setError(reason); if (targetId) await refreshExecution(targetId, abort.signal).catch(() => {}); } }
    finally { if (!abort.signal.aborted) setBusy(false); }
  };
  const approve = async (approved: boolean) => {
    if (!active?.pending || busy || checking) return;
    setBusy(true); setError(undefined); const abort = new AbortController(); controller.current = abort;
    invalidateStatus(active.conversation.id);
    try {
      const result = await api<AgentResult>(`/organizations/${organizationId}/agent/conversations/${active.conversation.id}/approval`, { method: 'POST', signal: abort.signal, body: jsonBody({ tool_call_id: active.pending.tool_call_id, approved }) });
      applyResult(result); message.success(approved ? '审批已提交' : '已拒绝本次创建');
    } catch (reason) { if (!abort.signal.aborted) { setError(reason); await refreshExecution(active.conversation.id, abort.signal).catch(() => {}); } }
    finally { if (!abort.signal.aborted) setBusy(false); }
  };
  const retry = async (legacyAuthorization?: boolean) => {
    if (!active?.execution?.can_retry || !active.execution.execution_id || busy || checking) return;
    if (active.execution.allow_ticket_creation === null && legacyAuthorization === undefined) {
      setLegacyRetryOpen(true);
      return;
    }
    const permission = active.execution.allow_ticket_creation ?? legacyAuthorization!;
    setLegacyRetryOpen(false); setAllowCreate(permission);
    const id = active.conversation.id; const executionId = active.execution.execution_id;
    changeConversation(id, value => ({ ...value, creationAllowed: permission }));
    setBusy(true); setError(undefined); invalidateStatus(id);
    const abort = new AbortController(); controller.current = abort;
    try {
      // 不调用send、不追加用户消息。让后端继续同一任务；审批仍单独处理。
      const result = await api<AgentResult>(`/organizations/${organizationId}/agent/conversations/${id}/retry`, {
        method: 'POST', signal: abort.signal,
        body: jsonBody({ execution_id: executionId, allow_ticket_creation: permission }),
      });
      applyResult(result);
    } catch (reason) { if (!abort.signal.aborted) { setError(reason); await refreshExecution(id, abort.signal).catch(() => {}); } }
    finally { if (!abort.signal.aborted) setBusy(false); }
  };
  const runModal = async (values: { title?: string; conversation_id?: string }) => {
    setModalBusy(true); setModalError(undefined);
    try {
      if (createOpen) { await createConversation(values.title); setCreateOpen(false); }
      else {
        // 必须先由后端确认会话归属，不能凭任意UUID加载别人的会话。
        const conversation = await api<Conversation>(`/organizations/${organizationId}/agent/conversations/${values.conversation_id!.trim()}`);
        setConversations(items => items.some(item => item.conversation.id === conversation.id) ? items : [{ conversation, messages: [], pending: null }, ...items]);
        setActiveId(conversation.id); setRestoreOpen(false); setError(undefined);
        message.success('已连接到这段会话，可以继续提问');
      }
    } catch (reason) { setModalError(reason); }
    finally { setModalBusy(false); }
  };
  if (!organizationId) return <><PageHeading eyebrow="AI WORKSPACE" title="智能助手" description="连接知识与行动，让每一次支持都有进展。"/><EmptyPanel title={organizationsLoading ? '正在加载组织' : '先选择或创建一个组织'} description="助手会在当前组织的知识库和工单范围内工作。" action={<Button href="/team" type="primary">前往组织管理</Button>}/></>;
  const blocked = busy || checking || !!active?.pending || ['failed', 'running'].includes(active?.execution?.status || '');
  const suggestions = [
    { icon: <FileSearchOutlined aria-hidden="true"/>, title: '查找排障方法', text: 'E1007数据库连接超时应该检查哪些地方？', hint: '从知识库中寻找处理依据' },
    { icon: <ThunderboltOutlined aria-hidden="true"/>, title: '整理排查工单', text: '请先查询数据库连接超时的排查资料，再帮我整理一张高优先级的排查工单。未知信息请注明未知，不要编造。', hint: '结合知识资料整理问题' },
    { icon: <FolderOpenOutlined aria-hidden="true"/>, title: '查询已有工单', text: '我想查询一张已有工单的状态和优先级，请告诉我需要提供什么信息。', hint: '跟进问题当前的处理状态' },
  ];
  return <><PageHeading eyebrow="AI WORKSPACE" title="智能助手" description="从查找答案，到推动问题解决。" action={<Space><Button icon={<LinkOutlined aria-hidden="true"/>} disabled={busy} onClick={() => { setModalError(undefined); setRestoreOpen(true); }}>继续已有会话</Button><Button type="primary" icon={<PlusOutlined aria-hidden="true"/>} disabled={busy} onClick={() => { setModalError(undefined); setCreateOpen(true); }}>新建会话</Button></Space>}/>
    <div className="agent-layout"><section className="surface chat-panel"><div className="chat-toolbar"><Space><span className="assistant-mark"><img src="/favicon.svg" alt=""/></span><div><strong>知序助手</strong><span className="toolbar-subtitle">{busy ? '正在处理你的请求…' : '准备好与你一起解决问题'}</span></div></Space><Select aria-label="当前会话" className="conversation-select" placeholder="新会话" value={activeId || undefined} disabled={busy} onChange={id => { setActiveId(id); setError(undefined); }} options={conversations.map(value => ({ label: value.conversation.title, value: value.conversation.id }))} /></div>
      <div className="chat-messages" aria-live="polite">{!active?.messages.length && <div className="assistant-welcome"><span className="welcome-emblem">✳</span><h2>你好，{user!.display_name}。</h2><p>今天有什么需要一起解决的？</p><div className="suggestions">{suggestions.map(item => <button className="suggestion" key={item.title} disabled={busy || !!active?.pending} onClick={() => setQuery(item.text)}><span className="suggestion-icon">{item.icon}</span><strong>{item.title}</strong><span>{item.hint}</span><ArrowRightOutlined aria-hidden="true"/></button>)}</div></div>}
        {active?.messages.map(item => <div key={item.id} className={`chat-message ${item.role}`}><span className="message-avatar">{item.role === 'assistant' ? '知' : user!.display_name.slice(0,1)}</span><div className="message-content"><span className="message-author">{item.role === 'assistant' ? '知序助手' : '你'}</span><div className="message-bubble"><Markdown>{item.content}</Markdown></div>{item.tools !== undefined && <span className="message-footnote">本次工具调用 {item.tools} 次</span>}</div></div>)}
        {busy && <div className="thinking"><span/><span/><span/><span className="thinking-label">正在梳理资料与执行步骤</span></div>}
        {active?.pending && <div className="approval-card"><div className="approval-kicker">需要你的确认</div><h3>助手准备创建一张工单</h3><p>确认以下内容后才会执行创建。</p><div className="approval-details"><strong>{active.pending.arguments.title}</strong><Tag color="orange">{priorityNames[active.pending.arguments.priority]}优先级</Tag><p>{active.pending.arguments.description}</p></div><Space><Button type="primary" icon={<CheckOutlined aria-hidden="true"/>} loading={busy} onClick={() => void approve(true)}>同意并创建</Button><Button icon={<CloseOutlined aria-hidden="true"/>} disabled={busy} onClick={() => void approve(false)}>拒绝创建</Button></Space></div>}
        <ErrorNotice error={error} onClose={() => setError(undefined)}/>
        {active?.execution?.status === 'failed' && <div className="execution-recovery"><h3>本次任务执行中断</h3><p>{active.execution.message || '恢复相关服务后，可以在这个会话重试。已有问题和历史消息会保留。'}</p>{active.execution.allow_ticket_creation === null && active.execution.can_retry && <p>此旧任务未记录创建权限，点击重试后会请你明确选择。</p>}<Space wrap><Button type="primary" icon={<ReloadOutlined aria-hidden="true"/>} disabled={!active.execution.can_retry || checking} loading={busy} onClick={() => void retry()}>重试本次任务</Button><Button loading={checking} disabled={busy} onClick={() => void checkExecution()}>检查任务状态</Button></Space></div>}
        {active?.execution?.status === 'running' && <div className="execution-recovery"><h3>任务正在执行</h3><p>请等待原任务完成，页面会自动检查状态。</p><Button loading={checking} onClick={() => void checkExecution()}>检查任务状态</Button></div>}
        {!!error && active && active.execution?.status !== 'failed' && active.execution?.status !== 'running' && <Button loading={checking} disabled={busy} icon={<ReloadOutlined aria-hidden="true"/>} onClick={() => void checkExecution()}>检查任务状态</Button>}<div ref={bottom}/>
      </div><div className="composer"><Input.TextArea aria-label="给智能助手发送问题" value={query} onChange={event => setQuery(event.target.value)} placeholder={active?.pending ? '请先处理上方待审批操作，再继续对话' : active?.execution?.status === 'failed' ? '请先重试上方中断的任务' : '描述你的问题，或告诉助手你希望完成什么…'} autoSize={{ minRows: 2, maxRows: 6 }} maxLength={2000} disabled={blocked} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }}/><div className="composer-bottom"><Tooltip title="打开后，助手才有资格发起创建；真正创建前仍需你确认。"><label className="permission-switch"><Switch size="small" checked={allowCreate} disabled={busy || checking} onChange={value => { setAllowCreate(value); if (activeId) changeConversation(activeId, item => ({ ...item, creationAllowed: value })); }}/><span>允许发起工单创建</span></label></Tooltip><Space><span className="keyboard-hint">Enter 发送</span><Button type="primary" icon={<SendOutlined aria-hidden="true"/>} loading={busy} disabled={!query.trim() || blocked} onClick={() => void send()}>发送</Button></Space></div></div></section>
      <aside className="agent-context"><div className="surface context-card"><span className="eyebrow">YOUR WORKSPACE</span><h3>在当前组织内协作</h3><p>{organization?.name}</p><div className="context-rule"><span>01</span><div><strong>知识先行</strong><p>检索组织知识，找到问题依据。</p></div></div><div className="context-rule"><span>02</span><div><strong>行动有序</strong><p>查询工单，整理后续处理事项。</p></div></div><div className="context-rule"><span>03</span><div><strong>确认后执行</strong><p>创建工单前，由你核对并审批。</p></div></div></div><div className="context-tip"><span className="tip-dot"/>会话记忆{active ? <><p>当前会话会保留上下文，可在同一会话继续追问。</p><IdText value={active.conversation.id}/></> : <p>第一次发送时会自动创建会话。</p>}<p className="small-text">下拉框保留此浏览器的会话入口。其他会话可通过真实会话 ID 继续。</p></div></aside>
    </div>
    <Modal title="确认旧任务的创建权限" open={legacyRetryOpen} onCancel={() => setLegacyRetryOpen(false)} footer={[
      <Button key="cancel" onClick={() => setLegacyRetryOpen(false)}>暂不重试</Button>,
      <Button key="read" onClick={() => void retry(false)}>只恢复查询</Button>,
      <Button key="create" type="primary" onClick={() => void retry(true)}>允许发起审批并重试</Button>,
    ]}><p>这个任务来自旧版本，未保存原来的创建开关。请选择本次恢复允许的操作。</p><p>允许发起审批也不会直接创建工单，实际创建前仍会展示工单内容，请你确认。</p></Modal>
    <Modal open={createOpen || restoreOpen} onCancel={() => { if (!modalBusy) { setCreateOpen(false); setRestoreOpen(false); } }} footer={null} title={createOpen ? '新建会话' : '继续已有会话'} destroyOnHidden><ErrorNotice error={modalError}/><Form key={createOpen ? 'new' : 'restore'} layout="vertical" onFinish={runModal} initialValues={{ title: '新会话' }}>{createOpen ? <Form.Item name="title" label="会话名称" rules={[{ required: true, whitespace: true, max: 200 }]}><Input placeholder="例如：数据库故障排查"/></Form.Item> : <Form.Item name="conversation_id" label="会话 ID" extra="后端会检查该会话是否属于当前组织和你的账号。" rules={[{ required: true, pattern: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i, message: '请输入完整的会话UUID' }]}><Input placeholder="粘贴已有会话ID"/></Form.Item>}<Button block type="primary" htmlType="submit" loading={modalBusy}>{createOpen ? '创建会话' : '连接会话'}</Button></Form></Modal>
  </>;
}
