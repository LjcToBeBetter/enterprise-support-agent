import { describe, expect, it } from 'vitest';
import { SseDecoder } from './client';

describe('SSE网络分段处理', () => {
  it('在每个字符位置切开事件仍能正确还原中文和最终消息', () => {
    const stream = 'event: delta\ndata: {"text":"数据库连接"}\n\nevent: done\ndata: {"answer":"已完成"}\n\n';
    for (let boundary = 0; boundary <= stream.length; boundary++) {
      const parser = new SseDecoder();
      const frames = [...parser.push(stream.slice(0,boundary)), ...parser.push(stream.slice(boundary))];
      expect(frames).toEqual([{event:'delta',data:{text:'数据库连接'}},{event:'done',data:{answer:'已完成'}}]);
    }
  });
  it('支持CRLF分隔、心跳注释和多行data', () => {
    const parser = new SseDecoder();
    expect(parser.push(': heartbeat\r\n\r\nevent: delta\r\ndata: {"text":\r\ndata: "中文"}\r\n\r\n')).toEqual([{event:'delta',data:{text:'中文'}}]);
  });
  it('只有完整事件才输出，半条done不能被当作成功', () => {
    const parser = new SseDecoder();
    expect(parser.push('event: done\ndata: {"answer":"还没结束"}')).toEqual([]);
    expect(parser.push('\n\n')).toHaveLength(1);
  });
});
