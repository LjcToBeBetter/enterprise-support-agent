import { Component, type ReactNode } from 'react';

/** 意外渲染错误也提供恢复入口，避免用户只能看到一张白屏。 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div className="initial-loading"><div><h2>页面暂时无法显示</h2><p>可以重新加载页面恢复连接，已保存的会话仍可继续。</p><button className="recovery-button" onClick={() => window.location.reload()}>重新加载</button></div></div>;
    return this.props.children;
  }
}
