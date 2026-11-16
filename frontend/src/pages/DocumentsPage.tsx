import { useCallback, useEffect, useRef, useState } from 'react';
import { App, Button, Checkbox, Descriptions, Drawer, Form, Input, Modal, Popconfirm, Progress, Select, Space, Table, Tag, Upload } from 'antd';
import type { UploadFile } from 'antd';
import { CloudUploadOutlined, DownloadOutlined, FilePdfOutlined, PlayCircleOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { allPages, api, downloadDocument } from '../api/client';
import type { KnowledgeDocument, ProcessingJob } from '../types';
import { dateText, EmptyPanel, ErrorNotice, IdText, PageHeading, StatusTag } from '../components/ui';
import { useWorkspace } from '../app/workspace';

export function DocumentsPage() {
  const { organizationId, role, user } = useWorkspace(); const { message } = App.useApp();
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]); const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(); const [keyword, setKeyword] = useState(''); const [status, setStatus] = useState<string>();
  const [uploadOpen, setUploadOpen] = useState(false); const [files, setFiles] = useState<UploadFile[]>([]); const [uploading, setUploading] = useState(false);
  const [autoProcess, setAutoProcess] = useState(true); const [uploadError, setUploadError] = useState<unknown>(); const [uploadProgress, setUploadProgress] = useState(0);
  const [selected, setSelected] = useState<KnowledgeDocument>(); const [jobDetail, setJobDetail] = useState<ProcessingJob>();
  const [lookupOpen, setLookupOpen] = useState(false); const [lookupBusy, setLookupBusy] = useState(false); const [lookupError, setLookupError] = useState<unknown>();
  const [actionId, setActionId] = useState(''); const mounted = useRef(true);
  const jobsKey = `support.jobs.${user!.id}.${organizationId}`;
  const [jobs, setJobs] = useState<Record<string, ProcessingJob>>(() => { try { return JSON.parse(sessionStorage.getItem(jobsKey) || '{}'); } catch { return {}; } });
  const jobsRef = useRef(jobs); jobsRef.current = jobs;
  const canUpload = role === 'admin' || role === 'support';
  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (!organizationId) return;
    setLoading(true);
    try { const values = await allPages<KnowledgeDocument>(`/organizations/${organizationId}/documents`, signal); if (mounted.current) { setDocuments(values); setError(undefined); } }
    catch (reason) { if (mounted.current && !(reason instanceof DOMException && reason.name === 'AbortError')) setError(reason); }
    finally { if (mounted.current) setLoading(false); }
  }, [organizationId]);
  useEffect(() => { mounted.current = true; const controller = new AbortController(); void refresh(controller.signal); return () => { mounted.current = false; controller.abort(); }; }, [refresh]);
  useEffect(() => { try { sessionStorage.setItem(jobsKey, JSON.stringify(jobs)); } catch { /* 任务仍可通过真实任务ID查询。 */ } }, [jobs, jobsKey]);
  useEffect(() => {
    if (role !== 'admin' || !organizationId) return;
    const abort = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const active = Object.values(jobsRef.current).filter(job => ['pending','queued','running'].includes(job.status));
      let finished = false;
      await Promise.all(active.map(async job => {
        try {
          const next = await api<ProcessingJob>(`/organizations/${organizationId}/documents/processing-jobs/${job.id}`, { signal: abort.signal });
          if (!abort.signal.aborted) {
            setJobs(values => values[next.document_id]?.id === next.id ? { ...values, [next.document_id]: next } : values);
            if (['succeeded','failed'].includes(next.status)) finished = true;
          }
        } catch (reason) { if (!abort.signal.aborted) setError(reason); }
      }));
      if (!abort.signal.aborted) { if (finished) await refresh(abort.signal); timer = setTimeout(poll, 3000); }
    };
    timer = setTimeout(poll, 1500);
    return () => { abort.abort(); clearTimeout(timer); };
  }, [organizationId, role, refresh]);
  const processDocument = async (doc: KnowledgeDocument) => {
    setActionId(doc.id); setError(undefined);
    try {
      const job = await api<ProcessingJob>(`/organizations/${organizationId}/documents/${doc.id}/process`, { method: 'POST' });
      if (mounted.current) { setJobs(values => ({ ...values, [doc.id]: job })); message.success('处理任务已提交，进度将自动更新'); }
    } catch (reason) { if (mounted.current) setError(reason); }
    finally { if (mounted.current) setActionId(''); }
  };
  const upload = async () => {
    setUploading(true); setUploadError(undefined); setUploadProgress(0);
    // 每成功一份就从待上传列表移除；部分失败后重试不会重复提交已成功的文件。
    const pending = [...files]; let completed = 0;
    try {
      for (const item of pending) {
        const file = item.originFileObj;
        if (!file) throw new Error('无法读取选择的文件，请重新选择。');
        if (file.size > 20 * 1024 * 1024) throw new Error(`${file.name} 超过20MiB上限。`);
        if (!file.name.toLowerCase().endsWith('.pdf')) throw new Error('当前文档处理仅支持PDF文件。');
        const body = new FormData(); body.append('file', file);
        const doc = await api<KnowledgeDocument>(`/organizations/${organizationId}/documents`, { method: 'POST', body });
        if (!mounted.current) return;
        setFiles(values => values.filter(value => value.uid !== item.uid)); completed += 1; setUploadProgress(Math.round(completed / pending.length * 100));
        if (autoProcess && role === 'admin') {
          const job = await api<ProcessingJob>(`/organizations/${organizationId}/documents/${doc.id}/process`, { method: 'POST' });
          if (mounted.current) setJobs(values => ({ ...values, [doc.id]: job }));
        }
      }
      if (mounted.current) { setUploadOpen(false); message.success('文件已上传'); }
    } catch (reason) { if (mounted.current) setUploadError(reason); }
    finally { if (mounted.current) { setUploading(false); void refresh(); } }
  };
  const lookup = async ({ job_id }: { job_id: string }) => {
    setLookupBusy(true); setLookupError(undefined);
    try {
      const job = await api<ProcessingJob>(`/organizations/${organizationId}/documents/processing-jobs/${job_id.trim()}`);
      setJobs(values => ({ ...values, [job.document_id]: job })); setJobDetail(job); setLookupOpen(false);
    } catch (reason) { setLookupError(reason); }
    finally { setLookupBusy(false); }
  };
  if (!organizationId) return <><PageHeading eyebrow="KNOWLEDGE LIBRARY" title="知识文档" description="让团队知识成为随时可用的支持资料。"/><EmptyPanel title="请先选择一个组织"/></>;
  const visible = documents.filter(doc => (!status || doc.status === status) && `${doc.original_filename} ${doc.id}`.toLowerCase().includes(keyword.toLowerCase()));
  return <><PageHeading eyebrow="KNOWLEDGE LIBRARY" title="知识文档" description="上传、处理和管理组织资料，为每次回答提供依据。" action={<Space>{role === 'admin' && <Button icon={<SearchOutlined aria-hidden="true"/>} onClick={() => { setLookupError(undefined); setLookupOpen(true); }}>查询任务</Button>}<Button icon={<ReloadOutlined aria-hidden="true"/>} loading={loading} onClick={() => void refresh()}>刷新</Button>{canUpload && <Button type="primary" icon={<CloudUploadOutlined aria-hidden="true"/>} onClick={() => { setUploadError(undefined); setUploadOpen(true); }}>上传文档</Button>}</Space>}/>
    <div className="library-overview"><div><span className="metric-label">组织文档</span><strong>{documents.length}<small>份</small></strong></div><div><span className="metric-label">已就绪，可检索</span><strong>{documents.filter(doc => doc.status === 'ready').length}<small>份</small></strong></div><div className="library-overview-note"><BookGlyph/><p>知识从这里开始流动<span>处理成功的文档可用于知识检索与问答</span></p></div></div><ErrorNotice error={error} onClose={() => setError(undefined)}/>
    <section className="surface data-panel"><div className="table-toolbar"><Input aria-label="搜索文档" placeholder="搜索文件名或文档ID" prefix={<SearchOutlined aria-hidden="true"/>} value={keyword} onChange={event => setKeyword(event.target.value)} allowClear/><Select aria-label="筛选文档状态" allowClear placeholder="全部状态" value={status} onChange={setStatus} options={['pending','processing','parsed','chunked','ready','failed'].map(value => ({ value, label: <StatusTag value={value}/> }))}/><span className="table-total">共 {visible.length} 份文档</span></div><Table<KnowledgeDocument> rowKey="id" loading={loading} dataSource={visible} scroll={{ x: 850 }} pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }} locale={{ emptyText: <EmptyPanel title={keyword || status ? '没有匹配的文档' : '知识库还没有文档'} description={canUpload ? '上传一份PDF，开始积累组织知识。' : '请联系组织管理员或技术支持上传文档。'}/> }} columns={[
      { title: '文档', key: 'name', render: (_, doc) => <button className="document-name" onClick={() => setSelected(doc)}><span className="pdf-icon"><FilePdfOutlined aria-hidden="true"/></span><span><strong>{doc.original_filename}</strong><small>{doc.id.slice(0,8)} · {(doc.file_size_bytes / 1024).toFixed(1)} KB</small></span></button> },
      { title: '状态', key: 'status', width: 145, render: (_, doc) => <><StatusTag value={doc.status}/>{jobs[doc.id] && <button className="job-link" onClick={() => setJobDetail(jobs[doc.id])}><StatusTag value={jobs[doc.id].status}/></button>}</> },
      { title: '版本', key: 'version', width: 70, render: (_, doc) => `v${doc.version}` },
      { title: '上传时间', key: 'time', width: 170, render: (_, doc) => dateText(doc.created_at) },
      { title: '操作', key: 'actions', width: 185, render: (_, doc) => { const active = jobs[doc.id] && ['pending','queued','running'].includes(jobs[doc.id].status); return <Space size={2}><Button type="text" size="small" icon={<DownloadOutlined aria-hidden="true"/>} aria-label={`下载${doc.original_filename}`} onClick={() => { void downloadDocument(organizationId,doc.id,doc.original_filename).catch(setError); }}/>{role === 'admin' && <Popconfirm title={doc.status === 'ready' ? '重新处理这份文档？' : '提交文档处理任务？'} description="将重新解析、切块并生成向量。" disabled={active} onConfirm={() => processDocument(doc)}><Button type="link" size="small" disabled={active} loading={actionId === doc.id} icon={<PlayCircleOutlined aria-hidden="true"/>}>{active ? '处理中' : doc.status === 'ready' ? '重新处理' : '处理文档'}</Button></Popconfirm>}</Space>; } },
    ]}/></section>
    <Modal open={uploadOpen} title="上传知识文档" footer={null} onCancel={() => { if (!uploading) setUploadOpen(false); }} destroyOnHidden><p className="muted">上传到当前组织。管理员可在上传后直接提交处理任务。</p><ErrorNotice error={uploadError}/><Upload.Dragger accept=".pdf,application/pdf" multiple maxCount={10} beforeUpload={() => false} fileList={files} onChange={({ fileList }) => setFiles(fileList)} disabled={uploading}><p className="upload-symbol"><CloudUploadOutlined aria-hidden="true"/></p><h3>点击选择，或将PDF拖到这里</h3><p>每份不超过20MiB，一次最多10份</p></Upload.Dragger>{role === 'admin' && <label className="upload-process-option"><Checkbox checked={autoProcess} disabled={uploading} onChange={event => setAutoProcess(event.target.checked)}>上传后自动提交处理任务</Checkbox></label>}{uploading && <Progress percent={uploadProgress}/>}<Button className="modal-submit" block type="primary" loading={uploading} disabled={!files.length} onClick={() => void upload()}>上传{files.length ? ` ${files.length} 份文档` : ''}</Button></Modal>
    <Drawer open={!!selected} title="文档详情" width={520} onClose={() => setSelected(undefined)}>{selected && <><h2>{selected.original_filename}</h2><Descriptions column={1} bordered size="small" items={[{ key: 'id', label: '文档ID', children: <span className="full-id"><IdText value={selected.id}/></span> },{ key: 'status', label: '状态', children: <StatusTag value={selected.status}/> },{ key: 'version', label: '版本', children: selected.version },{ key: 'size', label: '大小', children: `${selected.file_size_bytes} 字节` },{ key: 'created', label: '上传时间', children: dateText(selected.created_at) }]}/>{selected.error_message && <ErrorNotice error={selected.error_message}/>}<div className="drawer-actions"><Button icon={<DownloadOutlined aria-hidden="true"/>} onClick={() => void downloadDocument(organizationId,selected.id,selected.original_filename).catch(setError)}>下载原文</Button>{role === 'admin' && <Popconfirm title="删除文档及其知识内容？" description="此操作会影响后续检索，删除后无法从页面恢复。" onConfirm={async () => { try { await api(`/organizations/${organizationId}/documents/${selected.id}`,{ method:'DELETE' }); setJobs(values => { const next = { ...values }; delete next[selected.id]; return next; }); setSelected(undefined); message.success('文档已删除'); await refresh(); } catch(reason){setError(reason);} }}><Button danger>删除文档</Button></Popconfirm>}</div></>}</Drawer>
    <Drawer open={!!jobDetail} title="文档处理任务" width={520} onClose={() => setJobDetail(undefined)}>{jobDetail && <><Descriptions column={1} bordered size="small" items={[{key:'id',label:'任务ID',children:<IdText value={jobDetail.id}/>},{key:'doc',label:'文档ID',children:<IdText value={jobDetail.document_id}/>},{key:'state',label:'状态',children:<StatusTag value={jobs[jobDetail.document_id]?.id === jobDetail.id ? jobs[jobDetail.document_id].status : jobDetail.status}/>},{key:'attempt',label:'执行次数',children:`${jobs[jobDetail.document_id]?.attempt_count ?? jobDetail.attempt_count} / ${jobDetail.max_attempts}`},{key:'started',label:'开始时间',children:dateText(jobDetail.started_at)},{key:'finished',label:'结束时间',children:dateText(jobs[jobDetail.document_id]?.finished_at || jobDetail.finished_at)}]}/><ErrorNotice error={jobs[jobDetail.document_id]?.error_message || jobDetail.error_message}/><Space className="drawer-actions"><Button icon={<ReloadOutlined aria-hidden="true"/>} onClick={() => void lookup({ job_id: jobDetail.id })}>刷新任务</Button>{role === 'admin' && (jobs[jobDetail.document_id]?.status || jobDetail.status) === 'pending' && <Button onClick={async () => { try { const next = await api<ProcessingJob>(`/organizations/${organizationId}/documents/processing-jobs/${jobDetail.id}/retry-publish`,{method:'POST'}); setJobs(values=>({...values,[next.document_id]:next})); setJobDetail(next); } catch(reason){setError(reason);} }}>重新发送任务</Button>}</Space></>}</Drawer>
    <Modal open={lookupOpen} title="查询已有处理任务" footer={null} onCancel={() => setLookupOpen(false)} destroyOnHidden><ErrorNotice error={lookupError}/><Form layout="vertical" onFinish={lookup}><Form.Item name="job_id" label="任务ID" rules={[{required:true,pattern:/^[0-9a-f-]{36}$/i,message:'请输入完整任务UUID'}]}><Input placeholder="粘贴提交任务时返回的ID"/></Form.Item><Button block type="primary" htmlType="submit" loading={lookupBusy}>查询任务</Button></Form></Modal>
  </>;
}
function BookGlyph() { return <span className="library-glyph">▤</span>; }
