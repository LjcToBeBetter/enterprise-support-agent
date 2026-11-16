import { useCallback, useEffect, useRef, useState } from 'react';
import { App, Avatar, Button, Descriptions, Drawer, Form, Input, Popconfirm, Select, Space, Table, Tag } from 'antd';
import { ArrowRightOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { allPages, api, jsonBody } from '../api/client';
import type { Priority, Ticket, TicketStatus, User } from '../types';
import { dateText, EmptyPanel, ErrorNotice, IdText, PageHeading, priorityNames, StatusTag, statusNames } from '../components/ui';
import { useWorkspace } from '../app/workspace';

const transitions: Record<TicketStatus, TicketStatus[]> = { open: ['in_progress'], in_progress: ['resolved'], resolved: ['closed','in_progress'], closed: [] };
export function TicketsPage() {
  const { organizationId, role, user, memberships } = useWorkspace(); const { message } = App.useApp();
  const [tickets, setTickets] = useState<Ticket[]>([]); const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false); const [error, setError] = useState<unknown>();
  const [keyword, setKeyword] = useState(''); const [status, setStatus] = useState<string>(); const [priority, setPriority] = useState<string>();
  const [createOpen, setCreateOpen] = useState(false); const [creating, setCreating] = useState(false); const [createError, setCreateError] = useState<unknown>();
  const [selected, setSelected] = useState<Ticket>(); const [detailBusy, setDetailBusy] = useState(false); const [detailError, setDetailError] = useState<unknown>();
  const [assignee, setAssignee] = useState<string | null>(null); const mounted = useRef(true);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (!organizationId) return;
    setLoading(true);
    try { const values = await allPages<Ticket>(`/organizations/${organizationId}/tickets`, signal); if (mounted.current) { setTickets(values); setError(undefined); } }
    catch (reason) { if (mounted.current && !(reason instanceof DOMException && reason.name === 'AbortError')) setError(reason); }
    finally { if (mounted.current) setLoading(false); }
  }, [organizationId]);
  useEffect(() => { mounted.current = true; const abort = new AbortController(); void refresh(abort.signal); return () => { mounted.current = false; abort.abort(); }; }, [refresh]);
  useEffect(() => { if (!role || role === 'employee') return; const abort = new AbortController(); allPages<User>('/users',abort.signal).then(setUsers).catch(error => { if (error.name !== 'AbortError') setError(error); }); return () => abort.abort(); }, [role]);
  const userName = (id?: string | null) => !id ? '未分配' : id === user?.id ? `${user.display_name}（我）` : users.find(value => value.id === id)?.display_name || id.slice(0,8);
  const create = async (values: { title: string; description: string; priority: Priority }) => {
    setCreating(true); setCreateError(undefined);
    try { await api<Ticket>(`/organizations/${organizationId}/tickets`,{method:'POST',body:jsonBody(values)}); if (mounted.current) { setCreateOpen(false); message.success('工单已创建'); await refresh(); } }
    catch(reason){if(mounted.current)setCreateError(reason);} finally{if(mounted.current)setCreating(false);}
  };
  const openDetail = async (ticket: Ticket) => {
    setSelected(ticket); setAssignee(ticket.assignee_user_id); setDetailError(undefined); setDetailBusy(true);
    try { const next=await api<Ticket>(`/organizations/${organizationId}/tickets/${ticket.id}`); if(mounted.current){setSelected(next);setAssignee(next.assignee_user_id);} }catch(reason){if(mounted.current)setDetailError(reason);}finally{if(mounted.current)setDetailBusy(false);}
  };
  const update = async (suffix: string, body: unknown) => {
    if (!selected || detailBusy) return;
    setDetailBusy(true); setDetailError(undefined);
    try { const next=await api<Ticket>(`/organizations/${organizationId}/tickets/${selected.id}/${suffix}`,{method:'PATCH',body:jsonBody(body)}); if(mounted.current){setSelected(next);setAssignee(next.assignee_user_id);setTickets(values=>values.map(value=>value.id===next.id?next:value));message.success('工单已更新');} }
    catch(reason){if(mounted.current)setDetailError(reason);}finally{if(mounted.current)setDetailBusy(false);}
  };
  if(!organizationId)return <><PageHeading eyebrow="SUPPORT DESK" title="工单中心" description="让问题有归属，让处理有进展。"/><EmptyPanel title="请先选择一个组织"/></>;
  const visible=tickets.filter(ticket=>(!status||ticket.status===status)&&(!priority||ticket.priority===priority)&&`${ticket.title} ${ticket.description} ${ticket.id}`.toLowerCase().includes(keyword.toLowerCase()));
  const canManage=role==='admin'||role==='support';
  return <><PageHeading eyebrow="SUPPORT DESK" title="工单中心" description={role==='employee'?'查看并跟进你在当前组织中创建的工单。':'在一个地方跟进组织的问题、负责人和处理进展。'} action={<Space><Button icon={<ReloadOutlined aria-hidden="true"/>} loading={loading} onClick={()=>void refresh()}>刷新</Button><Button type="primary" icon={<PlusOutlined aria-hidden="true"/>} onClick={()=>{setCreateError(undefined);setCreateOpen(true);}}>创建工单</Button></Space>}/><div className="ticket-summary">{(['open','in_progress','resolved','closed'] as const).map(value=><button key={value} className={`summary-pill ${status===value?'selected':''}`} onClick={()=>setStatus(status===value?undefined:value)}><span className={`ticket-dot ${value}`}/>{statusNames[value]}<strong>{tickets.filter(ticket=>ticket.status===value).length}</strong></button>)}</div><ErrorNotice error={error} onClose={()=>setError(undefined)}/><section className="surface data-panel"><div className="table-toolbar"><Input aria-label="搜索工单" prefix={<SearchOutlined aria-hidden="true"/>} placeholder="搜索标题、描述或工单ID" value={keyword} onChange={event=>setKeyword(event.target.value)} allowClear/><Select aria-label="筛选工单优先级" placeholder="全部优先级" allowClear value={priority} onChange={setPriority} options={Object.entries(priorityNames).map(([value,label])=>({value,label}))}/><span className="table-total">共 {visible.length} 张工单</span></div><Table<Ticket> rowKey="id" loading={loading} dataSource={visible} scroll={{x:850}} pagination={{pageSize:10,showSizeChanger:false,hideOnSinglePage:true}} locale={{emptyText:<EmptyPanel title={keyword||status||priority?'没有匹配的工单':'暂时没有工单'} description="创建一张工单，让问题得到持续跟进。"/>}} columns={[
    {title:'工单',key:'title',render:(_,ticket)=><button className="ticket-title" onClick={()=>void openDetail(ticket)}><span className="ticket-id">#{ticket.id.slice(0,8)}</span><strong>{ticket.title}</strong></button>},
    {title:'状态',key:'state',width:105,render:(_,ticket)=><StatusTag value={ticket.status}/>},
    {title:'优先级',key:'priority',width:85,render:(_,ticket)=><PriorityTag value={ticket.priority}/>},
    {title:'处理人',key:'assignee',width:150,render:(_,ticket)=><span className="assignee-label">{ticket.assignee_user_id&&<Avatar size={24}>{userName(ticket.assignee_user_id).slice(0,1)}</Avatar>}{userName(ticket.assignee_user_id)}</span>},
    {title:'更新时间',key:'time',width:170,render:(_,ticket)=>dateText(ticket.updated_at)},
    {title:'',key:'action',width:60,render:(_,ticket)=><Button type="text" aria-label={`查看工单${ticket.title}`} icon={<ArrowRightOutlined aria-hidden="true"/>} onClick={()=>void openDetail(ticket)}/>},
  ]}/></section>
    <Drawer open={createOpen} title="创建工单" width={560} onClose={()=>{if(!creating)setCreateOpen(false);}} destroyOnHidden><ErrorNotice error={createError}/><Form layout="vertical" onFinish={create} initialValues={{priority:'medium'}} requiredMark={false}><Form.Item name="title" label="工单标题" rules={[{required:true,min:3,max:200,message:'请输入3～200字的标题'}]}><Input placeholder="用一句话描述需要处理的问题"/></Form.Item><Form.Item name="description" label="问题描述" rules={[{required:true,min:10,max:10000,message:'请输入10～10000字的问题描述'}]}><Input.TextArea rows={7} placeholder="描述故障现象、发生时间、影响范围和已有线索。未知信息请注明未知。"/></Form.Item><Form.Item name="priority" label="优先级"><Select options={Object.entries(priorityNames).map(([value,label])=>({value,label}))}/></Form.Item><Button block type="primary" htmlType="submit" loading={creating}>创建工单</Button></Form></Drawer>
    <Drawer open={!!selected} title="工单详情" width={600} onClose={()=>{if(!detailBusy)setSelected(undefined);}}>{selected&&<><div className="detail-kicker"><IdText value={selected.id}/><StatusTag value={selected.status}/><PriorityTag value={selected.priority}/></div><h2>{selected.title}</h2><p className="ticket-description">{selected.description}</p><ErrorNotice error={detailError}/><Descriptions column={1} size="small" items={[{key:'creator',label:'创建人',children:userName(selected.creator_user_id)},{key:'assignee',label:'处理人',children:userName(selected.assignee_user_id)},{key:'created',label:'创建时间',children:dateText(selected.created_at)},{key:'updated',label:'更新时间',children:dateText(selected.updated_at)}]}/>{canManage&&<section className="detail-section"><h3>分配处理人</h3><Space.Compact block><Select aria-label="选择工单处理人" style={{flex:1}} allowClear placeholder="未分配" value={assignee||undefined} onChange={value=>setAssignee(value||null)} disabled={detailBusy} options={memberships.filter(member=>member.role==='admin'||member.role==='support').map(member=>({value:member.user_id,label:userName(member.user_id)}))}/><Button disabled={detailBusy||assignee===selected.assignee_user_id} onClick={()=>void update('assignee',{assignee_user_id:assignee})}>保存分配</Button></Space.Compact></section>}{(role==='admin'||(role==='support'&&selected.assignee_user_id===user?.id))&&<section className="detail-section"><h3>更新处理状态</h3>{transitions[selected.status].length?<Space wrap>{transitions[selected.status].map(next=><Popconfirm key={next} title={`将工单标记为“${statusNames[next]}”？`} onConfirm={()=>update('status',{status:next})}><Button disabled={detailBusy} type={next==='in_progress'?'primary':'default'}>{next==='in_progress'&&selected.status==='open'?'开始处理':next==='in_progress'?'重新处理':statusNames[next]}</Button></Popconfirm>)}</Space>:<p className="muted">这张工单已关闭，不能继续修改状态。</p>}</section>}</>}</Drawer>
  </>;
}
function PriorityTag({value}:{value:Priority}){return <Tag bordered={false} color={value==='urgent'?'red':value==='high'?'orange':value==='medium'?'blue':'default'}>{priorityNames[value]}</Tag>;}
