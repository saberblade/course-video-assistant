// Requires a built frontend, prepared local .venv and Playwright with Chrome.
// Creates only its own logs/account-ui-* database; credentials are random in memory.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const id = Date.now().toString();
const output = path.join(root, 'logs', `account-ui-${id}`);
fs.mkdirSync(output, { recursive: true });
let base;
const password = randomBytes(20).toString('hex');
const results = [];
let backend, browser;
async function check(name, run) {
  try { await run(); results.push({ name, result:'passed' }); console.log(`PASS ${name}`); }
  catch (e) { results.push({ name, result:'failed', error:e.message.replaceAll(password,'[redacted]') }); throw e; }
}
async function signin(page, username) {
  await page.goto(`${base}/login`);
  await page.getByLabel('用户名', { exact:true }).fill(username);
  await page.getByLabel('密码', { exact:true }).fill(password);
  await page.getByRole('button', { name:'登录并进入云台' }).click();
  await page.waitForURL('**/screen**');
}
async function signout(page) {
  await page.getByRole('button', { name:'账号菜单' }).click();
  await page.getByRole('menuitem', { name:'退出登录' }).click();
  await page.waitForURL('**/login**');
}

(async () => {
  const reservation = net.createServer();
  await new Promise((resolve,reject)=>{ reservation.once('error',reject); reservation.listen(0,'127.0.0.1',resolve); });
  const port = reservation.address().port;
  await new Promise(resolve=>reservation.close(resolve));
  base = `http://127.0.0.1:${port}`;
  const log = fs.openSync(path.join(output, 'service.log'), 'w');
  backend = spawn(path.join(root,'.venv/Scripts/python.exe'), ['-X','utf8',path.join(root,'backend/tests/account_ui_fixture.py')], {
    cwd:root, windowsHide:true, stdio:['ignore',log,log], env:{...process.env, PYTHONDONTWRITEBYTECODE:'1', ACCOUNT_UI_TEST_DIR:output, ACCOUNT_UI_TEST_PASSWORD:password, ACCOUNT_UI_TEST_PORT:String(port)}
  });
  let ready = false;
  for (let i=0; i<80; i++) {
    if (backend.exitCode !== null) throw new Error('QA backend exited. See isolated service.log.');
    try {
      const health = await fetch(`${base}/api/health`);
      if (health.ok && (await health.json()).version === path.basename(output)) { ready = true; break; }
    } catch {}
    await new Promise(resolve => setTimeout(resolve,250));
  }
  if (!ready) throw new Error('Isolated QA service did not become ready; no browser mutations performed.');
  browser = await chromium.launch({ executablePath:process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless:true });
  const context = await browser.newContext({ viewport:{ width:1366,height:768 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  await check('public home and private route redirect', async () => {
    await page.goto(`${base}/`);
    await page.getByRole('link', {name:'登录 / 注册'}).waitFor();
    await page.goto(`${base}/screen?view=library`);
    await page.waitForURL('**/login?**');
    assert.equal(new URL(page.url()).searchParams.get('redirect'), '/screen?view=library');
    await page.screenshot({path:path.join(output,'login-desktop.png'),fullPage:true});
  });
  await check('client validation, registration, duplicate username and incorrect credentials', async () => {
    await page.getByRole('button',{name:'注册',exact:true}).click();
    await page.getByRole('button',{name:'创建账号',exact:true}).first().click();
    await page.getByText('请输入用户名',{exact:true}).waitFor();
    const username = `qa_new_${id}`;
    await page.getByLabel('用户名',{exact:true}).fill(username);
    await page.getByLabel('显示名',{exact:true}).fill('新同学');
    await page.getByLabel('密码',{exact:true}).fill(password);
    await page.getByLabel('确认密码',{exact:true}).fill(password+'x');
    await page.getByRole('button',{name:'创建账号',exact:true}).first().click();
    await page.getByText('两次输入的密码不一致').waitFor();
    await page.getByLabel('确认密码',{exact:true}).fill(password);
    await page.getByRole('button',{name:'创建账号',exact:true}).first().click();
    await page.getByText('注册成功，请用刚刚设置的密码登录。').waitFor();
    assert.equal(await page.getByLabel('密码',{exact:true}).inputValue(), '');
    assert.equal((await context.request.get(`${base}/api/auth/me`)).status(),401);
    await page.getByRole('button',{name:'注册',exact:true}).click();
    await page.getByLabel('密码',{exact:true}).fill(password);
    await page.getByLabel('确认密码',{exact:true}).fill(password);
    await page.getByRole('button',{name:'创建账号',exact:true}).first().click();
    await page.getByRole('alert').filter({hasText:'这个用户名已经有人使用'}).waitFor();
    await page.getByRole('button',{name:'登录',exact:true}).click();
    await page.getByLabel('密码',{exact:true}).fill('incorrect-password');
    await page.getByRole('button',{name:'登录并进入云台'}).click();
    await page.getByRole('alert').filter({hasText:'用户名或密码不正确'}).waitFor();
    assert(new URL(page.url()).pathname === '/login');
  });
  await check('login restores destination; refresh retains HttpOnly session; no stored credentials', async () => {
    await page.getByLabel('用户名',{exact:true}).fill('qa_alpha');
    await page.getByLabel('密码',{exact:true}).fill(password);
    await page.getByRole('button',{name:'登录并进入云台'}).click();
    await page.waitForURL('**/screen?view=library');
    await page.getByText('甲的私有课程',{exact:true}).first().waitFor();
    await page.reload();
    await page.getByText('甲的私有课程',{exact:true}).first().waitFor();
    assert.equal(await page.getByText('乙的私有课程',{exact:true}).count(),0);
    const cookie = (await context.cookies()).find(c=>c.name==='session');
    assert(cookie?.httpOnly && cookie.sameSite==='Lax');
    const storage = await page.evaluate(()=>({local:JSON.stringify(localStorage),session:JSON.stringify(sessionStorage),cookie:document.cookie}));
    assert(!JSON.stringify(storage).includes(password));
    assert(!JSON.stringify(storage).includes(cookie.value));
    assert(!JSON.stringify(storage).includes('csrf_token'));
    await page.screenshot({path:path.join(output,'library-account.png'),fullPage:true});
  });
  let alphaVideo;
  await check('write requests carry CSRF; invalid CSRF never silently retried', async () => {
    const me = await (await context.request.get(`${base}/api/auth/me`)).json();
    alphaVideo = (await (await context.request.get(`${base}/api/videos`)).json()).items[0].id;
    const response = await context.request.post(`${base}/api/assistant/chat`,{data:{messages:[{role:'user',content:'怎么用课迹？'}]}});
    assert.equal(response.status(),403);
    await page.getByRole('button',{name:'课迹助教',exact:true}).click();
    const written = page.waitForRequest(req=>req.url().endsWith('/api/assistant/chat'));
    await page.getByRole('button',{name:'课迹能做什么？',exact:true}).click();
    const request = await written;
    assert.equal(request.headers()['x-csrf-token'],me.csrf_token);
    await page.getByText('站内指引 · 当前使用基础回答',{exact:true}).waitFor();
    await page.getByRole('button',{name:'关闭课迹助教'}).click();
    await page.route('**/api/assistant/chat',route=>route.continue({headers:{...route.request().headers(),'x-csrf-token':'bad-token'}}));
    await page.getByRole('button',{name:'课迹助教',exact:true}).click();
    await page.getByLabel('给课迹助教的问题').fill('如何上传？');
    await page.getByRole('button',{name:'发送问题'}).click();
    await page.getByRole('alert').filter({hasText:'页面校验未通过'}).waitFor();
    assert(!page.url().includes('/login'));
    await page.unroute('**/api/assistant/chat');
    await page.getByRole('button',{name:'关闭课迹助教'}).click();
  });
  await check('legacy anonymous records remain untouched and outside account', async () => {
    const old = JSON.stringify([{key:'legacy',note:'旧匿名私人备注'}]);
    await page.evaluate(value=>localStorage.setItem('course-review:review-records:v1:real',value),old);
    await page.goto(`${base}/screen?view=weak`);
    await page.getByText('待复习清单暂不可用',{exact:true}).waitFor();
    assert.equal(await page.getByText('旧匿名记录仅保留在此浏览器，不会自动绑定或上传到当前账号。',{exact:true}).count(),0);
    assert.equal(await page.getByText('旧匿名私人备注',{exact:true}).count(),0);
    assert.equal(await page.evaluate(()=>localStorage.getItem('course-review:review-records:v1:real')),old);
  });
  await check('logout invalidates session; second account cannot access first account resources', async () => {
    await page.goto(`${base}/videos/${alphaVideo}?from=screen&view=library&t=4`);
    await page.locator('video').waitFor();
    await page.waitForFunction(()=>{
      const video = document.querySelector('video');
      return video?.readyState >= 1 && Math.abs(video.currentTime-4)<.3 && video.paused;
    });
    await page.locator('video').evaluate(el=>{window.__oldVideo=el;});
    await signout(page);
    assert(await page.evaluate(()=>window.__oldVideo.paused && !window.__oldVideo.getAttribute('src')),'old player source was released');
    assert.equal((await context.request.get(`${base}/api/auth/me`)).status(),401);
    await signin(page,'qa_beta');
    await page.getByRole('button',{name:'我的课程',exact:true}).click();
    await page.getByText('乙的私有课程',{exact:true}).first().waitFor();
    assert.equal(await page.getByText('甲的私有课程',{exact:true}).count(),0);
    assert.equal((await context.request.get(`${base}/api/videos/${alphaVideo}`)).status(),404);
    assert.equal((await context.request.get(`${base}/api/videos/${alphaVideo}/content`,{headers:{Range:'bytes=0-99'}})).status(),404);
    assert.equal(await page.locator('.assistant-panel__messages .assistant-bubble').count(),0);
  });
  await check('session expiration redirects and clears private page', async () => {
    await context.clearCookies();
    await page.getByRole('button',{name:'刷新列表',exact:true}).click();
    await page.waitForURL('**/login?**');
    await page.getByText('登录已过期，请重新登录后继续。',{exact:true}).waitFor();
    assert.equal(await page.getByText('乙的私有课程',{exact:true}).count(),0);
  });
  await check('late old-account response cannot restore private content after logout', async () => {
    await signin(page,'qa_alpha');
    await page.getByRole('button',{name:'我的课程',exact:true}).click();
    await page.getByText('甲的私有课程',{exact:true}).first().waitFor();
    let release, intercepted;
    const hold = new Promise(resolve=>release=resolve);
    const reached = new Promise(resolve=>intercepted=resolve);
    await page.route('**/api/videos?*',async route=>{
      const response = await route.fetch(); intercepted(); await hold;
      await route.fulfill({response}).catch(()=>{});
    });
    await page.getByRole('button',{name:'刷新列表',exact:true}).click();
    await reached;
    await signout(page);
    release();
    await page.unroute('**/api/videos?*',{behavior:'wait'});
    await signin(page,'qa_beta');
    await page.getByRole('button',{name:'我的课程',exact:true}).click();
    await page.getByText('乙的私有课程',{exact:true}).first().waitFor();
    assert.equal(await page.getByText('甲的私有课程',{exact:true}).count(),0);
  });
  await check('external redirect rejected and independent browser recovers same-account courses', async () => {
    const second = await browser.newContext();
    const other = await second.newPage();
    await other.goto(`${base}/login?redirect=https%3A%2F%2Fexample.com`);
    await other.getByLabel('用户名',{exact:true}).fill('qa_alpha');
    await other.getByLabel('密码',{exact:true}).fill(password);
    await other.getByRole('button',{name:'登录并进入云台'}).click();
    await other.waitForURL('**/screen');
    await other.getByRole('button',{name:'我的课程',exact:true}).click();
    await other.getByText('甲的私有课程',{exact:true}).first().waitFor();
    await second.close();
  });
  await check('account changes propagate across tabs without retaining previous courses', async () => {
    const other = await context.newPage();
    await other.goto(`${base}/screen?view=library`);
    await other.getByText('乙的私有课程',{exact:true}).first().waitFor();
    await signout(page);
    await other.waitForURL('**/login**');
    assert.equal(await other.getByText('乙的私有课程',{exact:true}).count(),0);
    await signin(page,'qa_alpha');
    await other.goto(`${base}/screen?view=library`);
    await other.getByText('甲的私有课程',{exact:true}).first().waitFor();
    assert.equal(await other.getByText('乙的私有课程',{exact:true}).count(),0);
    await other.close();
  });
  await check('login network failure remains recoverable and never signs in locally', async () => {
    await signout(page);
    await page.route('**/api/auth/login',route=>route.abort('connectionrefused'));
    await page.getByLabel('用户名',{exact:true}).fill('qa_alpha');
    await page.getByLabel('密码',{exact:true}).fill(password);
    await page.getByRole('button',{name:'登录并进入云台'}).click();
    await page.getByRole('alert').filter({hasText:'无法连接服务'}).waitFor();
    assert.equal(new URL(page.url()).pathname,'/login');
    assert.equal((await context.request.get(`${base}/api/auth/me`)).status(),401);
    await page.unroute('**/api/auth/login');
    await signin(page,'qa_alpha');
  });
  await check('mobile registration, login and navigation fit 320/390/768/1366 widths', async () => {
    await signout(page);
    for (const width of [320,390,768,1366]) {
      await page.setViewportSize({width,height:768});
      await page.goto(`${base}/login`);
      await page.getByRole('button',{name:'注册',exact:true}).click();
      assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
      assert(await page.getByRole('button',{name:'创建账号',exact:true}).first().isVisible());
      if (width===390) await page.screenshot({path:path.join(output,'register-mobile.png'),fullPage:true});
    }
    await signin(page,'qa_alpha');
    for (const width of [320,390,768,1366]) {
      await page.setViewportSize({width,height:768});
      await page.getByRole('button',{name:'我的课程',exact:true}).click();
      await page.getByText('甲的私有课程',{exact:true}).first().waitFor();
      const bounds = await page.locator('.scr-topbar').evaluate(el=>({scroll:el.scrollWidth,width:el.clientWidth}));
      assert(bounds.scroll <= bounds.width,`topbar overflow ${width}: ${JSON.stringify(bounds)}`);
    }
  });
  await check('current course shared by navigation and progress; full library and global todo remain independent', async () => {
    await page.setViewportSize({width:1366,height:768});
    const courses = (await (await context.request.get(`${base}/api/videos`)).json()).items;
    const original = courses.find(video=>video.title==='甲的私有课程');
    const another = courses.find(video=>video.title==='甲的另一门课程');
    assert(original && another);
    await page.getByRole('button',{name:'课程知识导航',exact:true}).click();
    const selectCourse = async title => {
      await page.locator('.rw-video-select').click();
      await page.locator('.rw-video-menu.el-popper:visible .el-select-dropdown__item').filter({hasText:title}).click();
      await page.waitForFunction(expected=>new URL(location.href).searchParams.get('video')===expected,title===original.title ? original.id : another.id);
      await page.locator('.rw-course-select').getByText(title,{exact:true}).waitFor();
    };
    await selectCourse(original.title);
    await selectCourse(another.title);
    await page.getByRole('button',{name:'复习进度',exact:true}).click();
    await page.locator('.rw-course-select').getByText(another.title,{exact:true}).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('video'),another.id);
    await page.getByRole('button',{name:'我的课程',exact:true}).click();
    await page.locator('.video-row').filter({hasText:original.title}).waitFor();
    await page.locator('.video-row').filter({hasText:another.title}).waitFor();
    await page.getByRole('button',{name:'课程知识导航',exact:true}).click();
    await page.locator('.rw-course-select').getByText(another.title,{exact:true}).waitFor();
    await page.reload();
    await page.locator('.rw-course-select').getByText(another.title,{exact:true}).waitFor();
    await page.getByRole('button',{name:'待复习清单',exact:true}).click();
    assert.equal(await page.locator('.rw-video-select').count(),0);
    await page.getByRole('button',{name:'复习进度',exact:true}).click();
    await page.locator('.rw-course-select').getByText(another.title,{exact:true}).waitFor();
    await page.getByRole('button',{name:'我的课程',exact:true}).click();
    await page.locator('.video-row').filter({hasText:original.title}).getByRole('button',{name:'打开',exact:true}).click();
    await page.waitForURL(`**/videos/${original.id}**`);
    await page.getByRole('heading',{name:original.title,exact:true}).waitFor();
    await page.getByRole('button',{name:'复习进度',exact:true}).click();
    await page.locator('.rw-course-select').getByText(original.title,{exact:true}).waitFor();
    await page.goBack();
    await page.waitForURL(`**/videos/${original.id}**`);
    await page.goBack();
    await page.getByRole('button',{name:'课程知识导航',exact:true}).click();
    await page.locator('.rw-course-select').getByText(another.title,{exact:true}).waitFor();
    await signout(page);
    await signin(page,'qa_beta');
    await page.locator('.rw-course-select').getByText('乙的私有课程',{exact:true}).waitFor();
    assert.equal(await page.locator('.rw-course-select').getByText(another.title,{exact:true}).count(),0);
  });
  assert.deepEqual(errors,[],'browser runtime errors');
})().catch(error=>{console.error(error.message.replaceAll(password,'[redacted]'));process.exitCode=1;}).finally(async()=>{
  await browser?.close();
  const pidFile = path.join(output,'service.pid');
  if (fs.existsSync(pidFile)) { try { process.kill(Number(fs.readFileSync(pidFile,'ascii'))); } catch {} }
  backend?.kill();
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({timestamp:new Date().toISOString(),service:'isolated FastAPI + production frontend; external LLM disabled',results},null,2));
  console.log(`Report: ${path.join(output,'report.json')}`);
});
