import React from 'react';
import ReactDOM from 'react-dom/client';
import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter } from 'react-router-dom';
import App from './app/App';
import { WorkspaceProvider } from './app/workspace';
import './styles/global.css';
import { ErrorBoundary } from './app/ErrorBoundary';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ConfigProvider button={{ autoInsertSpace: false }} locale={zhCN} theme={{ token: { colorPrimary: '#14695e', colorInfo: '#14695e', colorText: '#24362f', colorTextSecondary: '#7a8580', colorBorder: '#e2e8e3', borderRadius: 8, fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif', controlHeight: 38 }, components: { Button: { primaryShadow: 'none' }, Table: { headerBg: '#f7f9f6' } } }}><AntApp><BrowserRouter><WorkspaceProvider><ErrorBoundary><App/></ErrorBoundary></WorkspaceProvider></BrowserRouter></AntApp></ConfigProvider></React.StrictMode>,
);
