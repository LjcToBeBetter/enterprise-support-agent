import { test, expect, type Page } from '@playwright/test';

// 所有测试请求都由浏览器拦截，不会创建真实用户、工单或调用收费模型。
const orgId='11111111-1111-4111-8111-111111111111';
const otherOrg='22222222-2222-4222-8222-222222222222';
const userId='33333333-3333-4333-8333-333333333333';
const documentId='44444444-4444-4444-8444-444444444444';
const conversationId='55555555-5555-4555-8555-555555555555';
const ticketId='66666666-6666-4666-8666-666666666666';
const jobId='77777777-7777-4777-8777-777777777777';
const now='2026-11-11T08:00:00Z';
const user={id:userId,email:'ui-test@example.com',display_name:'林知远',is_active:true};
const organization={id:orgId,name:'星河技术支持',code:'xinghe-support',is_active:true};
const source={source_number:1,chunk_id:'chunk-1',document_id:documentId,page_number:2,content:'核对数据库主机、端口、数据库名和账号。',rerank_score:0.88};
const answer={query:'数据库怎么排查',answer:'检查应用配置和网络链路。[资料1]',sources:[source],used_source_count:1,no_answer:false};
const paged=<T>(items:T[])=>({items,total:items.length,page:1,page_size:100,total_pages:items.length?1:0});

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => console.error('Browser error:', error.message));
});

async function setup(page:Page,{role='admin',twoOrganizations=false,delayDocuments=false,emptyOrganizations=false,failAgentOnce=false,legacyAgent=false,retryFailsOnce=false}:{role?:string;twoOrganizations?:boolean;delayDocuments?:boolean;emptyOrganizations?:boolean;failAgentOnce?:boolean;legacyAgent?:boolean;retryFailsOnce?:boolean}={}){
  const state={requests:[] as {path:string;method:string;body:Record<string,unknown>|null}[],pending:false,approved:false,failed:false,completed:false,allowed:(legacyAgent?null:true) as boolean|null,finalAnswer:null as string|null,jobPolls:0,organizations:emptyOrganizations?[]:[organization,...(twoOrganizations?[{...organization,id:otherOrg,name:'北辰测试组织',code:'beichen'}]:[])],documents:[{id:documentId,organization_id:orgId,original_filename:'数据库手册.pdf',file_size_bytes:12500,content_type:'application/pdf',status:'ready',version:1,error_message:null,created_at:now,updated_at:now}],tickets:[{id:ticketId,organization_id:orgId,creator_user_id:userId,assignee_user_id:userId,title:'数据库连接超时',description:'访问数据库时出现连接超时，需要技术支持排查。',priority:'high',status:'open',created_at:now,updated_at:now}]};
  // 只模拟站点根路径下的业务接口；不要拦截/src/api/client.ts等源码模块。
  await page.route(url=>url.pathname.startsWith('/api/'),async route=>{
    const request=route.request();const path=new URL(request.url()).pathname.replace(/^\/api/,'');const method=request.method();
    let body:Record<string,unknown>|null=null;try{body=request.postDataJSON();}catch{/* multipart上传不是JSON。 */}
    state.requests.push({path,method,body});
    const send=(data:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
    if(path==='/health')return send({status:'ok'});
    if(path==='/auth/login')return send({access_token:'fixture-session-token',token_type:'bearer',expires_in:1800});
    if(path==='/auth/me')return send(user);
    if(path==='/users'&&method==='GET')return send(paged([user]));
    if(path==='/users'&&method==='POST')return send({...user,...body},201);
    if(path==='/organizations'&&method==='GET')return send(paged(state.organizations));
    if(path==='/organizations'&&method==='POST'){const created={...organization,name:String(body?.name),code:String(body?.code)};state.organizations.push(created);return send(created,201);}
    if(path.endsWith('/members'))return send([{id:'membership-1',organization_id:path.includes(otherOrg)?otherOrg:orgId,user_id:userId,role,created_at:now,updated_at:now}]);
    if(path.endsWith('/documents')&&method==='GET'){
      const alternate=path.includes(otherOrg);
      if(delayDocuments&&!alternate)await new Promise(resolve=>setTimeout(resolve,750));
      return send(paged(alternate?[{...state.documents[0],id:'other-document',organization_id:otherOrg,original_filename:'北辰独立资料.pdf'}]:state.documents));
    }
    if(path.endsWith('/documents')&&method==='POST'){const next={...state.documents[0],id:'88888888-8888-4888-8888-888888888888',original_filename:'接入测试.pdf',status:'pending'};state.documents.push(next);return send(next,201);}
    if(path.endsWith('/process'))return send({id:jobId,document_id:state.documents.at(-1)!.id,organization_id:orgId,status:'queued',attempt_count:0,max_attempts:3,error_message:null,started_at:null,finished_at:null},202);
    if(path.includes('/processing-jobs/')){state.jobPolls++;const status=state.jobPolls>1?'succeeded':'running';if(status==='succeeded')state.documents.at(-1)!.status='ready';return send({id:jobId,document_id:state.documents.at(-1)!.id,organization_id:orgId,status,attempt_count:1,max_attempts:3,error_message:null,started_at:now,finished_at:status==='succeeded'?now:null});}
    if(path.endsWith('/agent/conversations')&&method==='POST')return send({id:conversationId,title:body?.title||'新会话',organization_id:orgId,user_id:userId,created_at:now},201);
    const pending={tool_call_id:'call-test-1',tool_name:'create_ticket',arguments:{title:'数据库连接超时排查',description:'数据库出现连接超时，需要技术支持排查。',priority:'high'}};
    if(path.endsWith('/execution'))return send({conversation_id:conversationId,execution_id:'execution-original',status:state.failed?'failed':state.pending?'awaiting_approval':state.completed?'completed':'idle',can_retry:state.failed,allow_ticket_creation:state.allowed,answer:state.completed?(state.finalAnswer??(state.approved?'工单已创建，编号为 TEST-001。':'已取消本次工单创建。')):null,tool_call_count:1,pending_approval:state.pending?pending:null,message:state.failed?'任务中断，请重试':null});
    if(path.endsWith('/agent/chat')){if(failAgentOnce){failAgentOnce=false;state.failed=true;return send({code:'INTERNAL_SERVER_ERROR',message:'服务暂时出错，请稍后重试',request_id:'failed-request'},500);}state.pending=true;return send({status:'awaiting_approval',answer:null,tool_call_count:1,conversation_id:conversationId,pending_approval:pending});}
    if(path.endsWith('/retry')){state.allowed=body?.allow_ticket_creation===true;if(retryFailsOnce){retryFailsOnce=false;state.failed=true;return send({code:'INTERNAL_SERVER_ERROR',message:'测试MCP仍未恢复'},500);}state.failed=false;if(!state.allowed){state.completed=true;state.finalAnswer='已完成查询，未启用工单创建。';return send({status:'completed',answer:state.finalAnswer,tool_call_count:1,conversation_id:conversationId,pending_approval:null});}state.pending=true;return send({status:'awaiting_approval',answer:null,tool_call_count:1,conversation_id:conversationId,pending_approval:pending});}
    if(path.endsWith('/approval')){state.approved=body?.approved===true;state.pending=false;state.completed=true;return send({status:'completed',answer:state.approved?'工单已创建，编号为 TEST-001。':'已取消本次工单创建。',tool_call_count:2,conversation_id:conversationId,pending_approval:null});}
    if(path.endsWith('/knowledge/answer/stream')){
      if(String(body?.query).includes('校验失败'))return route.fulfill({status:200,contentType:'text/event-stream',body:'event: delta\ndata: {"text":"不可靠的临时文字"}\n\nevent: error\ndata: {"code":"INVALID_ANSWER_CITATION","message":"答案引用校验失败，请重试","request_id":"test-request"}\n\n'});
      return route.fulfill({status:200,contentType:'text/event-stream',body:`event: delta\ndata: {"text":"临时生成文字"}\n\nevent: done\ndata: ${JSON.stringify(answer)}\n\n`});
    }
    if(path.endsWith('/knowledge/search'))return send({query:body?.query,returned_count:1,items:[{chunk_id:'chunk-1',document_id:documentId,document_version:1,page_number:2,chunk_index:1,content:source.content,rrf_score:0.016,vector_score:0.8,bm25_score:2.9,rerank_score:0.88,rerank_rank:1}]});
    if(path.endsWith('/tickets')&&method==='GET')return send(paged(state.tickets));
    if(path.endsWith('/tickets')&&method==='POST'){const ticket={...state.tickets[0],id:'99999999-9999-4999-8999-999999999999',...body};state.tickets.push(ticket);return send(ticket,201);}
    if(path.includes('/tickets/')){if(path.endsWith('/status')){state.tickets[0].status=String(body?.status);}return send(state.tickets[0]);}
    return send({code:'TEST_UNEXPECTED_ROUTE',message:`未覆盖的测试请求：${method} ${path}`},404);
  });
  return state;
}
async function login(page:Page){await page.goto('/');await page.getByLabel('邮箱',{exact:true}).fill(user.email);await page.getByLabel('密码',{exact:true}).fill('test-only-password');await page.getByRole('button',{name:'登录工作台'}).click();await expect(page.getByRole('heading',{name:'智能助手',exact:true})).toBeVisible();await expect(page.locator('.workspace-meta')).toContainText(organization.name);}

test('登录、Agent发起审批、刷新后确认创建，保留正确工具调用编号',async({page})=>{
  const state=await setup(page);await login(page);
  await page.getByRole('switch').click();
  await page.getByLabel('给智能助手发送问题').fill('请帮我创建一张数据库排查工单。');await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByRole('heading',{name:'助手准备创建一张工单'})).toBeVisible();expect(state.approved).toBe(false);
  const chat=state.requests.find(value=>value.path.endsWith('/agent/chat'))!;
  expect(chat.body).toMatchObject({conversation_id:conversationId,allow_ticket_creation:true});
  await page.reload();await expect(page.getByRole('heading',{name:'助手准备创建一张工单'})).toBeVisible();
  await page.getByRole('button',{name:'同意并创建'}).click();await expect(page.locator('.message-bubble').last()).toContainText('工单已创建');
  expect(state.requests.find(value=>value.path.endsWith('/approval'))?.body).toEqual({tool_call_id:'call-test-1',approved:true});
  await page.screenshot({path:'test-results/agent-workspace.png',fullPage:true});
});

test('Agent失败后原会话刷新重试，不重复问题、不重新发chat、不跳过审批',async({page})=>{
  const state=await setup(page,{failAgentOnce:true});await login(page);
  await page.getByRole('switch').click();await page.getByLabel('给智能助手发送问题').fill('先查知识，再创建数据库排查工单。');
  await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByRole('button',{name:'重试本次任务'})).toBeVisible();await expect(page.getByLabel('给智能助手发送问题')).toBeDisabled();
  await page.reload();await expect(page.getByRole('button',{name:'重试本次任务'})).toBeEnabled();
  await page.getByRole('button',{name:'重试本次任务'}).click();
  await expect(page.getByRole('heading',{name:'助手准备创建一张工单'})).toBeVisible();
  expect(state.requests.filter(value=>value.path.endsWith('/agent/chat'))).toHaveLength(1);
  expect(state.requests.find(value=>value.path.endsWith('/retry'))?.body).toEqual({execution_id:'execution-original',allow_ticket_creation:true});
  expect(state.approved).toBe(false);await expect(page.locator('.chat-message.user')).toHaveCount(1);
  await expect(page.getByRole('button',{name:'重试本次任务'})).toHaveCount(0);
  await page.getByRole('button',{name:'同意并创建'}).click();await expect(page.locator('.message-bubble').last()).toContainText('工单已创建');
});

test('旧任务授权未知时先确认，再次失败并刷新仍保留明确的创建授权',async({page})=>{
  const state=await setup(page,{failAgentOnce:true,legacyAgent:true,retryFailsOnce:true});await login(page);
  await page.getByRole('switch').click();await page.getByLabel('给智能助手发送问题').fill('先查知识，再发起工单审批。');await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByRole('button',{name:'重试本次任务'})).toBeVisible();await page.reload();
  await page.getByRole('button',{name:'重试本次任务'}).click();await expect(page.getByRole('dialog',{name:'确认旧任务的创建权限'})).toBeVisible();
  expect(state.requests.filter(value=>value.path.endsWith('/retry'))).toHaveLength(0);
  await page.getByRole('button',{name:'暂不重试'}).click();await expect(page.getByRole('dialog')).toBeHidden();
  expect(state.requests.filter(value=>value.path.endsWith('/retry'))).toHaveLength(0);
  await page.getByRole('button',{name:'重试本次任务'}).click();await page.getByRole('button',{name:'允许发起审批并重试'}).click();
  await expect(page.getByRole('alert')).toContainText('测试MCP仍未恢复');expect(state.allowed).toBe(true);
  await page.reload();await expect(page.getByRole('switch')).toBeChecked();await page.getByRole('button',{name:'重试本次任务'}).click();
  await expect(page.getByRole('heading',{name:'助手准备创建一张工单'})).toBeVisible();
  expect(state.requests.filter(value=>value.path.endsWith('/retry')).map(value=>value.body?.allow_ticket_creation)).toEqual([true,true]);
  expect(state.requests.filter(value=>value.path.endsWith('/agent/chat'))).toHaveLength(1);expect(state.approved).toBe(false);
});

test('旧任务可以明确选择只恢复查询，不出现工单审批',async({page})=>{
  const state=await setup(page,{failAgentOnce:true,legacyAgent:true});await login(page);
  await page.getByLabel('给智能助手发送问题').fill('恢复知识查询');await page.getByRole('button',{name:'发送',exact:true}).click();
  await page.getByRole('button',{name:'重试本次任务'}).click();await page.getByRole('button',{name:'只恢复查询',exact:true}).click();
  await expect(page.locator('.message-bubble').last()).toContainText('未启用工单创建');
  expect(state.requests.find(value=>value.path.endsWith('/retry'))?.body?.allow_ticket_creation).toBe(false);
  await expect(page.getByRole('heading',{name:'助手准备创建一张工单'})).toHaveCount(0);
});

test('响应丢失后检查到已完成结果，只补展示，不再次执行创建',async({page})=>{
  const state=await setup(page,{failAgentOnce:true});await login(page);
  await page.getByLabel('给智能助手发送问题').fill('测试原任务恢复');await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByRole('button',{name:'重试本次任务'})).toBeVisible();
  state.failed=false;state.completed=true;state.approved=true;
  await page.getByRole('button',{name:'检查任务状态',exact:true}).click();
  await expect(page.locator('.message-bubble').last()).toContainText('工单已创建');await expect(page.getByRole('alert')).toHaveCount(0);
  expect(state.requests.filter(value=>value.path.endsWith('/retry')||value.path.endsWith('/approval'))).toHaveLength(0);
  await page.reload();await expect(page.locator('.chat-message.assistant')).toHaveCount(1);
});

test('批量文档入口发送multipart，202任务持续轮询到成功',async({page})=>{
  const state=await setup(page);await login(page);await page.getByRole('link',{name:'知识文档'}).click();
  await page.getByRole('button',{name:'上传文档',exact:true}).click();await page.locator('input[type=file]').setInputFiles({name:'接入测试.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.7\nfixture')});
  await page.getByRole('button',{name:'上传 1 份文档'}).click();
  await expect(page.getByRole('dialog',{name:'上传知识文档'})).toBeHidden();
  await expect(page.locator('tr').filter({hasText:'接入测试.pdf'})).toContainText('处理成功',{timeout:14000});
  expect(state.jobPolls).toBeGreaterThanOrEqual(2);expect(state.requests.filter(value=>value.path.endsWith('/process'))).toHaveLength(1);
  await page.screenshot({path:'test-results/documents-workspace.png',fullPage:true});
});

test('流式问答采用最终引用结果，引用校验失败时丢弃临时文字',async({page})=>{
  await setup(page);await login(page);await page.getByRole('link',{name:'知识问答'}).click();
  await page.getByLabel('知识库问题').fill('数据库怎么排查');await page.getByRole('button',{name:'生成答案'}).click();
  await expect(page.locator('.answer-panel .markdown')).toContainText(answer.answer);await expect(page.locator('.sources-panel')).toContainText('资料 1');await expect(page.locator('.answer-panel')).not.toContainText('临时生成文字');
  await page.getByLabel('知识库问题').fill('请模拟校验失败');await page.getByRole('button',{name:'生成答案'}).click();
  await expect(page.getByRole('alert')).toContainText('答案引用校验失败');await expect(page.getByText('不可靠的临时文字',{exact:false})).toHaveCount(0);
});

test('成员看不到上传按钮，切换组织时旧响应不会覆盖新组织文档',async({page})=>{
  await setup(page,{role:'employee',twoOrganizations:true,delayDocuments:true});await login(page);await page.getByRole('link',{name:'知识文档'}).click();
  await page.locator('.organization-select').click();await page.getByText('北辰测试组织',{exact:true}).last().click();
  await expect(page.getByRole('button',{name:'上传文档',exact:true})).toHaveCount(0);
  await expect(page.locator('.document-name').filter({hasText:'北辰独立资料'})).toBeVisible();await page.waitForTimeout(1100);
  await expect(page.locator('table')).not.toContainText('数据库手册.pdf');
});

test('工单状态遵守流转规则，修改请求发送真实工单ID和目标状态',async({page})=>{
  const state=await setup(page);await login(page);await page.getByRole('link',{name:'工单中心'}).click();
  await page.locator('.ticket-title').filter({hasText:'数据库连接超时'}).click();await page.getByRole('button',{name:'开始处理',exact:true}).click();await page.getByRole('button',{name:'确定',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('已解决');
  expect(state.requests.find(value=>value.path.endsWith('/status'))).toMatchObject({path:`/organizations/${orgId}/tickets/${ticketId}/status`,body:{status:'in_progress'}});
});

test('无组织账号可创建组织并成为管理员',async({page})=>{
  const state=await setup(page,{emptyOrganizations:true});
  await page.goto('/');await page.getByLabel('邮箱',{exact:true}).fill(user.email);await page.getByLabel('密码',{exact:true}).fill('test-only-password');await page.getByRole('button',{name:'登录工作台'}).click();
  await page.getByRole('link',{name:'组织与成员'}).click();await page.getByRole('button',{name:'创建组织',exact:true}).first().click();
  await page.getByLabel('组织名称').fill('新组织测试');await page.getByLabel('组织编码').fill('new-test-org');await page.getByRole('button',{name:'创建并进入组织'}).click();
  await expect(page.getByRole('heading',{name:'新组织测试',exact:true})).toBeVisible();expect(state.organizations).toHaveLength(1);
});

test('登录失效返回登录页，不继续展示旧组织页面',async({page})=>{
  await setup(page);await login(page);
  await page.route('**/api/organizations/*/agent/chat',route=>route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({code:'HTTP_401',message:'请先登录'})}));
  await page.getByLabel('给智能助手发送问题').fill('查询资料');await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByRole('button',{name:'登录工作台'})).toBeVisible();await expect(page.getByText('登录已过期，请重新登录。')).toBeVisible();
});

test('小屏幕可以打开导航并进入知识文档',async({page})=>{
  await page.setViewportSize({width:390,height:844});await setup(page);await login(page);
  await page.getByRole('button',{name:'打开导航'}).click();await page.getByRole('link',{name:'知识文档'}).click();
  await expect(page.getByRole('heading',{name:'知识文档',exact:true})).toBeVisible();
  await expect(page.locator('.ant-drawer-mask')).toBeHidden();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
  await page.screenshot({path:'test-results/mobile-workspace.png',fullPage:true});
});
