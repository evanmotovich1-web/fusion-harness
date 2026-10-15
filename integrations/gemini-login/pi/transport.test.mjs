import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { invokeBridge } from './transport.mjs';

async function fixture(code) {
  const dir=await mkdtemp(join(tmpdir(),'gemini-transport-'));
  const script=join(dir,'child.mjs');
  await writeFile(script,code);
  return {dir,script};
}

test('SIGTERM-resistant process and its native-style descendant are killed on abort',async()=>{
  const f=await fixture(`import{spawn}from'node:child_process';import{writeFileSync}from'node:fs';
    process.on('SIGTERM',()=>{});
    const child=spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],{stdio:'ignore'});
    writeFileSync(process.argv[2],String(child.pid));setInterval(()=>{},1000);`);
  const pidFile=join(f.dir,'pid'); const c=new AbortController();
  const started=Date.now();
  const pending=invokeBridge({timeout_seconds:10},c.signal,{command:process.execPath,args:[f.script,pidFile],graceMs:60});
  pending.catch(()=>{});
  let pid;
  for(let n=0;n<100;n++){try{pid=Number(await readFile(pidFile,'utf8'));break;}catch{} await new Promise(r=>setTimeout(r,10));}
  assert.ok(pid,'descendant started');
  c.abort();
  await assert.rejects(pending,/aborted/i);
  assert.ok(Date.now()-started<1500,'abort settled within bound');
  await new Promise(r=>setTimeout(r,100));
  assert.throws(()=>process.kill(pid,0),/ESRCH/,'owned descendant gone');
  await rm(f.dir,{recursive:true,force:true});
});

test('descendant cleanup continues when the bridge exits early on SIGTERM',async()=>{
  const f=await fixture(`import{spawn}from'node:child_process';import{writeFileSync}from'node:fs';
    process.on('SIGTERM',()=>process.exit(0));
    const child=spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],{stdio:'ignore'});
    writeFileSync(process.argv[2],String(child.pid));setInterval(()=>{},1000);`);
  const pidFile=join(f.dir,'pid'); const c=new AbortController();
  const pending=invokeBridge({timeout_seconds:10},c.signal,{command:process.execPath,args:[f.script,pidFile],graceMs:60});
  pending.catch(()=>{});
  let pid;
  for(let n=0;n<100;n++){try{pid=Number(await readFile(pidFile,'utf8'));break;}catch{} await new Promise(r=>setTimeout(r,10));}
  assert.ok(pid,'descendant started');
  await new Promise(r=>setTimeout(r,80));
  c.abort();
  await assert.rejects(pending,/aborted/i);
  await new Promise(r=>setTimeout(r,160));
  let alive=true;try{process.kill(pid,0);}catch(e){if(e.code==='ESRCH')alive=false;else throw e;}
  if(alive) process.kill(pid,'SIGKILL');
  await rm(f.dir,{recursive:true,force:true});
  assert.equal(alive,false,'stdio-independent descendant must be gone');
});

test('output excess stops accumulation and settles instead of hanging',async()=>{
  const f=await fixture(`process.on('SIGTERM',()=>{});setInterval(()=>process.stdout.write('x'.repeat(4096)),1);`);
  const started=Date.now();
  await assert.rejects(invokeBridge({timeout_seconds:10},undefined,{command:process.execPath,args:[f.script],maxStdoutBytes:1000,graceMs:30}),/output/i);
  assert.ok(Date.now()-started<1500);
  await rm(f.dir,{recursive:true,force:true});
});

test('hard deadline settles even if SIGTERM is ignored',async()=>{
  const f=await fixture(`process.on('SIGTERM',()=>{});setInterval(()=>{},1000);`);
  await assert.rejects(invokeBridge({timeout_seconds:10},undefined,{command:process.execPath,args:[f.script],timeoutMs:50,graceMs:30}),/timed out/i);
  await rm(f.dir,{recursive:true,force:true});
});
