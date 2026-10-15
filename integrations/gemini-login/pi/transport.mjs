import { spawn } from 'node:child_process';
import { parseBridgeOutput } from './protocol.mjs';

export function invokeBridge(request,signal,config={}) {
  return new Promise((resolve,reject)=>{
    if(signal?.aborted) return reject(new Error('Request aborted'));
    const command=config.command ?? 'python3';
    const args=config.args ?? [config.script];
    const proc=spawn(command,args,{detached:process.platform!=='win32',stdio:['pipe','pipe','pipe'],env:{...process.env,GEMINI_LOGIN_PARENT_PROCESS_GROUP:'1'}});
    let out='',outBytes=0,closed=false,settled=false,cancelReason;
    let killTimer,settleTimer;
    const maxBytes=config.maxStdoutBytes ?? 16_000_000;
    const grace=config.graceMs ?? 5000;
    const send=(signalName)=>{
      if(!proc.pid) return;
      try { if(process.platform==='win32') proc.kill(signalName); else process.kill(-proc.pid,signalName); }
      catch(e) { if(e.code!=='ESRCH') try{proc.kill(signalName);}catch{} }
    };
    const cleanup=()=>{
      clearTimeout(hardTimer);
      // Cancelled groups may retain detached-stdio descendants after the bridge closes.
      // Keep their escalation timer alive until SIGKILL reaches the owned group.
      if(!cancelReason) clearTimeout(killTimer);
      clearTimeout(settleTimer);
      signal?.removeEventListener('abort',onAbort);
    };
    const finish=(error,result)=>{
      if(settled) return;
      settled=true;cleanup();
      if(error) reject(error); else resolve(result);
    };
    const stop=(reason)=>{
      if(closed || cancelReason) return;
      cancelReason=reason;
      send('SIGTERM');
      killTimer=setTimeout(()=>{
        send('SIGKILL');
        if(closed) return;
        settleTimer=setTimeout(()=>{
          proc.stdin.destroy();proc.stdout.destroy();proc.stderr.destroy();proc.unref();
          finish(new Error(cancelReason));
        },250);
      },grace);
    };
    const onAbort=()=>stop('Request aborted');
    const hardTimer=setTimeout(()=>stop('Gemini login bridge timed out'),config.timeoutMs ?? (request.timeout_seconds+15)*1000);
    signal?.addEventListener('abort',onAbort,{once:true});
    proc.stdout.setEncoding('utf8');proc.stderr.setEncoding('utf8');
    proc.stdout.on('data',chunk=>{
      if(cancelReason) return;
      outBytes+=Buffer.byteLength(chunk);
      if(outBytes>maxBytes) { stop('Gemini login bridge exceeded output bound'); return; }
      out+=chunk;
    });
    proc.stderr.on('data',()=>{}); // Diagnostics never become answers or retained prompt logs.
    proc.on('error',error=>finish(error));
    proc.on('close',code=>{
      closed=true;
      if(cancelReason || signal?.aborted) return finish(new Error(cancelReason ?? 'Request aborted'));
      try { finish(undefined,parseBridgeOutput(out,code ?? -1)); } catch(error) { finish(error); }
    });
    proc.stdin.on('error',()=>{});
    proc.stdin.end(JSON.stringify(request));
  });
}
