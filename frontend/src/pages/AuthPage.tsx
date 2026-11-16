import { useState } from 'react';
import { Alert, Button, Form, Input } from 'antd';
import { ArrowRightOutlined, BookOutlined, SafetyCertificateOutlined, ApartmentOutlined } from '@ant-design/icons';
import { api, jsonBody } from '../api/client';
import { ErrorNotice } from '../components/ui';
import { useWorkspace } from '../app/workspace';

export function AuthPage() {
  const { login, sessionNotice } = useWorkspace();
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const submit = async (values: { email: string; password: string; display_name?: string }) => {
    setBusy(true); setError(undefined);
    try {
      if (register) await api('/users', { method: 'POST', body: jsonBody(values) });
      await login(values.email, values.password);
    } catch (reason) { setError(reason); }
    finally { setBusy(false); }
  };
  return <div className="auth-layout">
    <section className="auth-story"><a className="brand" href="/"><img src="/favicon.svg" alt="" /><span>知序<span className="brand-en">SUPPORT WORKSPACE</span></span></a>
      <div className="auth-story-main"><span className="eyebrow">KNOWLEDGE. CONNECTED.</span><h1>让每一次提问，<br />都有据可循。</h1><p>把分散的知识、复杂的问题和待办工单，<br />连接在一个清晰有序的工作空间。</p>
        <div className="auth-illustration" aria-hidden="true"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="illustration-center"><img src="/favicon.svg" alt=""/></div><div className="floating-label floating-one"><BookOutlined aria-hidden="true"/> 企业知识</div><div className="floating-label floating-two"><ApartmentOutlined aria-hidden="true"/> 智能协作</div><div className="floating-label floating-three"><SafetyCertificateOutlined aria-hidden="true"/> 有序执行</div></div>
      </div><span className="auth-footer">企业知识库与工单协作平台</span></section>
    <section className="auth-form-wrap"><div className="auth-form"><div className="eyebrow">WELCOME TO ZHIXU</div><h2>{register ? '创建你的账号' : '欢迎回来'}</h2><p className="muted">{register ? '注册后创建组织，或请管理员将你加入现有组织。' : '登录工作台，继续你的支持与协作。'}</p>
      {sessionNotice && !error && <Alert type="info" showIcon message={sessionNotice} />}
      <ErrorNotice error={error} onClose={() => setError(undefined)} />
      <Form layout="vertical" onFinish={submit} requiredMark={false} key={register ? 'register' : 'login'} size="large">
        {register && <Form.Item name="display_name" label="姓名" rules={[{ required: true, min: 2, max: 100, message: '请输入2～100字的姓名' }]}><Input placeholder="怎么称呼你" autoComplete="name" /></Form.Item>}
        <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}><Input placeholder="name@company.com" autoComplete="email" /></Form.Item>
        <Form.Item name="password" label="密码" rules={[{ required: true, min: 8, max: 128, message: '密码应为8～128个字符' }]}><Input.Password placeholder="输入你的密码" autoComplete={register ? 'new-password' : 'current-password'} /></Form.Item>
        <Button block type="primary" htmlType="submit" loading={busy} icon={<ArrowRightOutlined aria-hidden="true"/>} iconPosition="end">{register ? '注册并进入工作台' : '登录工作台'}</Button>
      </Form><p className="auth-switch">{register ? '已有账号？' : '还没有账号？'}<Button type="link" onClick={() => { setRegister(!register); setError(undefined); }}>{register ? '返回登录' : '创建账号'}</Button></p>
    </div><span className="auth-form-bottom">知识有来源，操作有确认，协作有记录。</span></section>
  </div>;
}
