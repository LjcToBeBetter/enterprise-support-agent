import { useEffect, useState } from 'react';
import { Avatar, Button, Drawer, Dropdown, Select, Space, Spin, Tag } from 'antd';
import { ApartmentOutlined, BookOutlined, CheckCircleOutlined, CommentOutlined, DownOutlined, LogoutOutlined, MenuOutlined, QuestionCircleOutlined, TeamOutlined } from '@ant-design/icons';
import { Link, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { api } from '../api/client';
import { useWorkspace } from './workspace';
import { ErrorNotice, roleNames } from '../components/ui';
import { AuthPage } from '../pages/AuthPage';
import { AgentPage } from '../pages/AgentPage';
import { KnowledgePage } from '../pages/KnowledgePage';
import { DocumentsPage } from '../pages/DocumentsPage';
import { TicketsPage } from '../pages/TicketsPage';
import { TeamPage } from '../pages/TeamPage';

const navigation = [
  { path: '/agent', label: '智能助手', icon: <CommentOutlined aria-hidden="true"/>, caption: '提问、查询与协作' },
  { path: '/knowledge', label: '知识问答', icon: <QuestionCircleOutlined aria-hidden="true"/>, caption: '检索与引用验证' },
  { path: '/documents', label: '知识文档', icon: <BookOutlined aria-hidden="true"/>, caption: '上传与处理进度' },
  { path: '/tickets', label: '工单中心', icon: <CheckCircleOutlined aria-hidden="true"/>, caption: '跟进每一个问题' },
  { path: '/team', label: '组织与成员', icon: <TeamOutlined aria-hidden="true"/>, caption: '成员与访问权限' },
];

export default function App() {
  const workspace = useWorkspace(); const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const check = () => api('/health', { signal: controller.signal }).then(() => setBackendOnline(true)).catch(error => { if (error.name !== 'AbortError') setBackendOnline(false); });
    void check(); const timer = setInterval(check, 30000);
    return () => { clearInterval(timer); controller.abort(); };
  }, []);
  useEffect(() => setMobileOpen(false), [location.pathname]);
  if (workspace.authLoading) return <div className="initial-loading"><Spin size="large"/><span>正在打开工作台…</span></div>;
  if (!workspace.user) return <AuthPage/>;
  const current = navigation.find(item => location.pathname.startsWith(item.path)) || navigation[0];
  const sidebar = <><Link to="/agent" className="brand"><img src="/favicon.svg" alt=""/><span>知序<span className="brand-en">SUPPORT WORKSPACE</span></span></Link><div className="nav-label">工作空间</div><nav aria-label="主导航">{navigation.map(item => <NavLink key={item.path} to={item.path} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>{item.icon}<span>{item.label}</span><span className="nav-dot"/></NavLink>)}</nav><div className="sidebar-note"><span className="small-kicker">在一个空间里，连接答案与行动</span><p>从知识中找到依据，<br/>让问题得到妥善跟进。</p><span className="sidebar-note-symbol">↗</span></div><div className="sidebar-bottom"><span className={`connection-dot ${backendOnline === false ? 'offline' : ''}`}/>{backendOnline === null ? '正在连接服务' : backendOnline ? '后端服务已连接' : '后端暂时无法连接'}</div></>;
  return <div className="workspace-shell"><aside className="sidebar">{sidebar}</aside><Drawer placement="left" width={250} open={mobileOpen} onClose={() => setMobileOpen(false)} styles={{ body: { padding: 20 } }} className="mobile-nav">{sidebar}</Drawer><div className="main-shell"><header className="topbar"><div className="topbar-location"><Button className="mobile-menu" type="text" icon={<MenuOutlined aria-hidden="true"/>} aria-label="打开导航" onClick={() => setMobileOpen(true)}/><span className="breadcrumb-root">工作台</span><span className="breadcrumb-separator">/</span><strong>{current.label}</strong></div><div className="topbar-right"><ApartmentOutlined aria-hidden="true"/><Select aria-label="当前组织" className="organization-select" placeholder="选择组织" value={workspace.organizationId || undefined} loading={workspace.organizationsLoading} onChange={workspace.setOrganizationId} options={workspace.organizations.map(org => ({ label: org.name, value: org.id }))} notFoundContent="暂无可访问的组织"/><span className="topbar-divider"/><Dropdown trigger={['click']} menu={{ items: [{ key: 'profile', disabled: true, label: workspace.user.email }, { key: 'logout', label: '退出登录', icon: <LogoutOutlined aria-hidden="true"/>, onClick: workspace.logout }] }}><Button type="text" className="user-menu"><Avatar size={30} style={{ background: '#e3eee6', color: '#346051' }}>{workspace.user.display_name.slice(0,1)}</Avatar><span>{workspace.user.display_name}</span><DownOutlined aria-hidden="true"/></Button></Dropdown></div></header><main className="page-content"><div className="workspace-meta"><span><span className="live-dot"/> {workspace.organization?.name || '欢迎来到工作台'}</span>{workspace.role && <Tag bordered={false}>{roleNames[workspace.role]}</Tag>}</div><ErrorNotice error={workspace.workspaceError}/>{!!workspace.workspaceError && <Button className="retry-workspace" onClick={() => void workspace.refreshOrganizations()}>重新加载组织</Button>}<Routes><Route path="/agent" element={<AgentPage key={workspace.organizationId}/>}/><Route path="/knowledge" element={<KnowledgePage key={workspace.organizationId}/>}/><Route path="/documents" element={<DocumentsPage key={workspace.organizationId}/>}/><Route path="/tickets" element={<TicketsPage key={workspace.organizationId}/>}/><Route path="/team" element={<TeamPage key={workspace.organizationId}/>}/><Route path="*" element={<Navigate to="/agent" replace/>}/></Routes></main><footer className="workspace-footer"><span>知序 · 企业支持工作台</span><span>让知识流动，让协作有序</span></footer></div></div>;
}
