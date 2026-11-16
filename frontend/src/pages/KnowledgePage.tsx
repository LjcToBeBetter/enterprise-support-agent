import { useEffect, useRef, useState } from 'react';
import { Button, Collapse, Form, Input, InputNumber, Segmented, Space, Spin, Switch, Tag } from 'antd';
import { ArrowRightOutlined, BookOutlined, SearchOutlined } from '@ant-design/icons';
import { api, jsonBody, streamAnswer } from '../api/client';
import type { AnswerResult, SearchHit, SearchResult } from '../types';
import { EmptyPanel, ErrorNotice, IdText, Markdown, PageHeading } from '../components/ui';
import { useWorkspace } from '../app/workspace';

export function KnowledgePage() {
  const { organizationId } = useWorkspace();
  const [mode, setMode] = useState('answer'); const [streaming, setStreaming] = useState(true);
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>();
  const [answer, setAnswer] = useState<AnswerResult>(); const [partial, setPartial] = useState('');
  const [search, setSearch] = useState<SearchResult>(); const [lastQuery, setLastQuery] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const submit = async (values: { query: string; candidate_top_k: number; rrf_top_k: number; final_top_k: number }) => {
    if (!values.query.trim() || busy) return;
    if (values.final_top_k > values.rrf_top_k) { setError(new Error('最终资料数不能超过RRF候选数。')); return; }
    setBusy(true); setError(undefined); setAnswer(undefined); setSearch(undefined); setPartial(''); setLastQuery(values.query.trim());
    const abort = new AbortController(); controller.current = abort;
    try {
      const body = { ...values, query: values.query.trim() };
      if (mode === 'search') setSearch(await api<SearchResult>(`/organizations/${organizationId}/knowledge/search`, { method: 'POST', body: jsonBody(body), signal: abort.signal }));
      else if (streaming) setAnswer(await streamAnswer(organizationId, body, abort.signal, delta => setPartial(value => value + delta)));
      else setAnswer(await api<AnswerResult>(`/organizations/${organizationId}/knowledge/answer`, { method: 'POST', body: jsonBody(body), signal: abort.signal }));
    } catch (reason) {
      // 后端要求引用校验失败时丢弃临时答案，不能将已输出的片段当作可靠结果。
      if (!abort.signal.aborted) { setPartial(''); setError(reason); }
    } finally { if (!abort.signal.aborted) setBusy(false); }
  };
  if (!organizationId) return <><PageHeading eyebrow="KNOWLEDGE EXPLORER" title="知识问答" description="让答案有来源，让每一次检索都可追溯。"/><EmptyPanel title="请先选择一个组织" description="知识检索只在当前组织范围内进行。"/></>;
  return <><PageHeading eyebrow="KNOWLEDGE EXPLORER" title="知识问答" description="查找相关资料，或让助手基于资料整理答案。"/><div className="knowledge-layout"><section><Form className="surface knowledge-query" layout="vertical" onFinish={submit} initialValues={{ candidate_top_k: 20, rrf_top_k: 20, final_top_k: 5 }}><div className="query-mode"><Segmented value={mode} disabled={busy} onChange={value => { setMode(value as string); setError(undefined); setAnswer(undefined); setSearch(undefined); setPartial(''); }} options={[{ label: '基于资料回答', value: 'answer' }, { label: '只检索资料', value: 'search' }]}/>{mode === 'answer' && <label className="permission-switch"><Switch size="small" checked={streaming} disabled={busy} onChange={setStreaming}/>逐段显示</label>}</div><Form.Item name="query" rules={[{ required: true, whitespace: true, max: 2000, message: '请输入2000字以内的问题' }]}><Input.TextArea aria-label="知识库问题" autoSize={{ minRows: 3, maxRows: 8 }} maxLength={2000} placeholder="例如：E1007 数据库连接超时应该检查哪些地方？" disabled={busy}/></Form.Item><div className="query-footer"><Collapse ghost size="small" items={[{ key: 'parameters', label: '检索参数', children: <div className="parameter-fields"><Form.Item name="candidate_top_k" label="每路召回数"><InputNumber min={1} max={50} disabled={busy}/></Form.Item><Form.Item name="rrf_top_k" label="RRF候选数"><InputNumber min={1} max={50} disabled={busy}/></Form.Item><Form.Item name="final_top_k" label="最终资料数"><InputNumber min={1} max={20} disabled={busy}/></Form.Item></div> }]}/><Button type="primary" htmlType="submit" icon={mode === 'search' ? <SearchOutlined aria-hidden="true"/> : <ArrowRightOutlined aria-hidden="true"/>} loading={busy}>{mode === 'search' ? '开始检索' : '生成答案'}</Button></div></Form><ErrorNotice error={error}/>
      {(busy || answer || partial || search) && <section className="surface answer-panel"><div className="section-heading"><h2>{mode === 'search' ? '检索结果' : '回答'}</h2>{busy ? <Tag color="processing">{partial ? '正在生成' : '正在查找资料'}</Tag> : answer?.no_answer ? <Tag color="warning">资料不足</Tag> : <Tag color="success">已完成</Tag>}</div><p className="result-question">{lastQuery}</p>{busy && !partial && <div className="answer-loading"><Spin/><span>正在查找组织知识库中的相关资料…</span></div>}{(answer || partial) && <Markdown>{answer?.answer || partial}</Markdown>}{busy && partial && <span className="stream-cursor"/>}{search && (search.items.length ? search.items.map((hit, index) => <SearchCard key={hit.chunk_id} hit={hit} index={index}/>) : <EmptyPanel title="没有找到匹配资料" description="可以换一种问法，或先上传并处理相关文档。"/>)}</section>}
      {!busy && !answer && !search && !error && <div className="knowledge-placeholder"><BookOutlined aria-hidden="true"/><h3>把知识变成可以使用的答案</h3><p>先上传并处理文档，再从这里开始提问。<br/>每条引用都能展开查看原始文本。</p></div>}</section>
    <aside className="surface sources-panel"><div className="section-heading"><h3>引用资料</h3><Tag bordered={false}>{answer?.used_source_count || 0} 条</Tag></div>{answer?.sources.length ? <Collapse ghost items={answer.sources.map(source => ({ key: source.source_number, label: <><span className="source-number">{source.source_number}</span>资料 {source.source_number} · 第{source.page_number}页</>, children: <><div className="source-meta"><IdText value={source.document_id}/>{source.rerank_score !== null && <span>相关分数 {source.rerank_score.toFixed(3)}</span>}</div><p className="source-content">{source.content}</p></> }))}/> : <div className="sources-empty"><BookOutlined aria-hidden="true"/><p>完成问答后，<br/>这里会展示答案引用的资料。</p></div>}<div className="source-hint">逐段生成的内容是临时答案；完成后以引用校验通过的最终回答为准。</div></aside></div></>;
}

function SearchCard({ hit, index }: { hit: SearchHit; index: number }) {
  return <article className="search-hit"><div className="search-hit-heading"><strong><span className="source-number">{index + 1}</span>第{hit.page_number}页 · 文本块 {hit.chunk_index + 1}</strong><IdText value={hit.document_id}/></div><p className="source-content">{hit.content}</p><Space wrap size={6}><Tag>向量 {hit.vector_score?.toFixed(3) ?? '未召回'}</Tag><Tag>BM25 {hit.bm25_score?.toFixed(3) ?? '未召回'}</Tag><Tag>RRF {hit.rrf_score.toFixed(5)}</Tag><Tag color={hit.rerank_score === null ? 'warning' : 'green'}>Rerank {hit.rerank_score?.toFixed(3) ?? '已降级'}</Tag></Space></article>;
}
