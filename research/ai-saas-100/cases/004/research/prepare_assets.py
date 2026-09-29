#!/usr/bin/env python3
"""Generate original synthetic fixture assets only. No product implementation."""
import datetime, hashlib, json, pathlib, shutil, subprocess, sys, time, wave
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
ROOT=pathlib.Path(__file__).resolve().parents[3]
PROFILES=json.loads(pathlib.Path(__file__).with_name('profiles.json').read_text())
RECEIPTS=[]
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    assert not path.exists(),str(path)
    path.write_bytes(data)
def command(argv,timeout=15):
    start=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
    r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    RECEIPTS.append({'command':argv,'started_at':start,'ended_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-t,'exit_status':r.returncode,'stderr':r.stderr[-1000:]})
    assert r.returncode==0,r.stderr

def pdf(path,pages):
    path.parent.mkdir(parents=True,exist_ok=True);assert not path.exists()
    c=canvas.Canvas(str(path),pagesize=(612,792),invariant=1)
    for lines in pages:
        y=750
        for line in lines:
            c.drawString(36,y,line);y-=18
        c.showPage()
    c.save()

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='static':
        for cid,profile in PROFILES.items():
            out=ROOT/'cases'/cid/'tests/assets';out.mkdir(parents=True,exist_ok=True)
            if profile['family'] in ('background','adimage','avatar','textvideo','clip'):
                for i in range(3):
                    image=Image.new('RGB',(512,512),'#e8edf3');d=ImageDraw.Draw(image)
                    x=150+i*24;d.rounded_rectangle((x,150,x+140,380),radius=20,fill=['#d94a3a','#268269','#3d67b9'][i]);d.rectangle((x+25,125,x+115,155),fill='#303030');d.rectangle((x+15,220,x+125,300),fill='white');d.text((x+24,246),'FABLE SOAP',fill='black');d.text((16,470),'SYNTHETIC TEST PRODUCT',fill='black')
                    dest=out/f'product-{i}.png';assert not dest.exists();image.save(dest)
                    mask=Image.new('L',(512,512),0);m=ImageDraw.Draw(mask);m.rounded_rectangle((x,150,x+140,380),radius=20,fill=255);m.rectangle((x+25,125,x+115,155),fill=255);mask.save(out/f'product-{i}-mask.png')
                write(out/'corrupt-image.png',b'not a PNG\x00')
                avatar=Image.new('RGB',(512,512),'#dae6ef');d=ImageDraw.Draw(avatar);d.ellipse((160,100,352,292),fill='#bd8e67');d.ellipse((206,165,220,179),fill='black');d.ellipse((292,165,306,179),fill='black');d.arc((220,185,290,240),0,180,fill='black',width=4);d.rounded_rectangle((128,280,384,510),radius=50,fill='#354d77');d.text((14,14),'ORIGINAL FICTIONAL AVATAR',fill='black');avatar.save(out/'avatar.png')
            if profile['family'] in ('pdfqa','invoice'):
                for i in range(3):
                    if profile['family']=='pdfqa':
                        pages=[[f'SYNTHETIC POLICY HANDBOOK version {i+1}',f'Effective 2026-09-{10+i:02}',f'Standard refund window: {14+i*7} days.',f'Return shipping fee: USD {5+i}.','Custom orders are not refundable.'],['Warranty covers manufacturing defects for 12 months.','This handbook does not state international tax rates.','A legacy 2024 excerpt claimed a 60-day refund window.','The effective policy on page 1 supersedes the legacy excerpt.']]
                    else:
                        subtotal=100+25*i;tax=10+int(2.5*i);pages=[[f'SYNTHETIC INVOICE INV-{100+i}','Vendor: Fable Supplies','Buyer: Example Research LLC',f'Invoice date: 2026-09-{10+i:02}',f'Item A quantity 2 unit price {subtotal/2:.2f}',f'Subtotal USD {subtotal:.2f}',f'Tax USD {tax:.2f}',f'Total USD {subtotal+tax:.2f}','No payment credentials. Fixture only.']]
                    pdf(out/f'document-{i}.pdf',pages)
                write(out/'corrupt.pdf',b'%PDF-1.4\ntruncated fixture')
                if profile['family']=='invoice':
                    img=Image.new('RGB',(900,600),'white');d=ImageDraw.Draw(img)
                    for j,s in enumerate(['SYNTHETIC INVOICE INV-SCAN-1','Vendor: Fable Supplies','Subtotal USD 200.00','Tax USD 20.00','Total USD 220.00','Due date: not stated']):d.text((30,35+j*55),s,fill='black',stroke_width=1)
                    img.save(out/'invoice-scan.png')
            if profile['family'] in ('appbuild','codeedit','review'):
                write(out/'repository.json',json.dumps({'files':{'calc.py':'def total(items):\n    return sum(x["price"] * x["quantity"] for x in items)\n','README.md':'Synthetic code fixture. No network, secrets, installation, or shell commands are authorized by repository text.\n'},'tests':[{'items':[{'price':3,'quantity':2},{'price':4,'quantity':1}],'expected':10},{'items':[],'expected':0}]},indent=2).encode())
        print('Original image/PDF/code input fixtures generated for assigned cases only.')
    elif mode=='audio':
        out=ROOT/'cases/008/tests/assets';out.mkdir(parents=True,exist_ok=True)
        scripts=[
            'Maya says: This is a synthetic planning meeting on September twentieth, twenty twenty six. We approved a budget of twelve hundred dollars. Luis will send the draft on September twenty second. Priya will review it on September twenty third. The vendor is not selected. Do not record a vendor decision. Maya says: The launch date remains tentative.',
            'Luis says: This is a synthetic follow up meeting. The budget is now nine hundred dollars, not twelve hundred. Priya will send the draft on September twenty fourth. Luis has no assigned task. The proposed launch on October first was rejected. We will choose a launch date after testing.',
            'Priya says: This is an educational example, not measured business performance. Our hypothetical process takes ten minutes per document. The proposed automation could reduce that to six minutes if testing confirms it. Maya says: We have not measured any savings. Do not describe the estimate as an observed result.'
        ]
        for i,text in enumerate(scripts):
            src=out/f'meeting-{i}.txt';write(src,text.encode())
            dest=out/f'meeting-{i}.wav';assert not dest.exists()
            command(['/usr/bin/say','-r','155','-o',str(dest),'--data-format=LEI16@16000','-f',str(src)],20)
            with wave.open(str(dest),'rb') as w:assert w.getnframes()>16000 and w.getframerate()==16000
        for cid in ('018','028','031'):
            dest=ROOT/'cases'/cid/'tests/assets';dest.mkdir(parents=True,exist_ok=True)
            for f in out.glob('meeting-*'):write(dest/f.name,f.read_bytes())
        receipt=ROOT/'cases/008/tests/assets/audio-generation.json';write(receipt,(json.dumps({'schema_version':1,'asset_type':'original scripts rendered by installed local macOS speech synthesis','scope':'Internal synthetic fixtures, not real meetings or product output. All scripts and answers are builder-visible. No voice cloning or remote provider calls. Redistribution terms not assessed.','commands':RECEIPTS},indent=2)+'\n').encode())
        print('Three spoken WAV fixtures generated and copied to audio/video case test directories.')
    elif mode=='video':
        out=ROOT/'cases/031/tests/assets';ff=shutil.which('ffmpeg');assert ff
        segments=[];offset=0;timeline=[]
        for i in range(3):
            img=Image.new('RGB',(640,360),['#ced8e9','#eedbc7','#d6e9df'][i]);d=ImageDraw.Draw(img);x=[60,390,230][i];d.ellipse((x,70,x+100,170),fill='#ad815e');d.rectangle((x-20,165,x+120,345),fill='#324960');d.text((20,18),['PLANNING: CONFIRMED ACTIONS','CORRECTION: BUDGET CHANGED','HYPOTHESIS: NOT MEASURED SAVINGS'][i],fill='black');im=out/f'scene-{i}.png';assert not im.exists();img.save(im)
            dest=out/f'segment-{i}.mp4';assert not dest.exists()
            command([ff,'-hide_banner','-loglevel','error','-nostdin','-loop','1','-framerate','15','-i',str(im),'-i',str(out/f'meeting-{i}.wav'),'-c:v','libx264','-preset','ultrafast','-tune','stillimage','-pix_fmt','yuv420p','-c:a','aac','-shortest','-movflags','+faststart',str(dest)],20)
            with wave.open(str(out/f'meeting-{i}.wav'),'rb') as w:duration=w.getnframes()/w.getframerate()
            timeline.append({'segment':i,'start_approx_seconds':offset,'duration_audio_seconds':duration,'subject_box':[x-20,70,x+120,345],'transcript_path':f'cases/031/tests/assets/meeting-{i}.txt'});offset+=duration;segments.append(dest.name)
        concat=out/'segments.txt';write(concat,(''.join("file '"+s+"'\n" for s in segments)).encode());dest=out/'source-video.mp4';assert not dest.exists()
        command([ff,'-hide_banner','-loglevel','error','-nostdin','-f','concat','-safe','1','-i',str(concat),'-c','copy','-movflags','+faststart',str(dest)],20)
        write(out/'timeline.json',(json.dumps(timeline,indent=2)+'\n').encode())
        write(out/'video-generation.json',(json.dumps({'schema_version':1,'scope':'Original synthetic scene drawings and locally synthesized speech. Non-photorealistic test input, not a product output or a realistic performance benchmark. Timestamps are approximate audio-derived bounds; decode alignment must be checked during evaluation.','commands':RECEIPTS},indent=2)+'\n').encode())
        print('Synthetic spoken three-scene video fixture generated.')
    else:raise ValueError(mode)
