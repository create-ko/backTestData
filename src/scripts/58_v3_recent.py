# -*- coding: utf-8 -*-
"""58 - v3(고정밴드 리밋) 최근 10개 트레이드: TradingView 대조용 차트 + 정확 표.
v3: 돌파봉 반대편 4/4밴드(고정)에 리밋 -> 체결 후 그리드 3(밴드/-1/-2KTR, 랏1/2/3)
-> 트레일SL = max(가장깊은체결-M, 고점-N)KTR. slip 0.3. N=1.0 M=1.0. base=KTR.
각 트레이드: 돌파시각·진입(리밋)가·각 그리드 체결시각/가·SL청산시각/가·PnL 표 + 캔들차트.
data/에서 실행. 콘솔 ASCII만(규칙3). 출력: ../result/v3_recent.html"""
import csv, math, json, time

N=1.0; M=1.0; SLIP=0.3; KSTEP=[0,1,2]; LOTS=[1,2,3]; MAXSCAN=3000

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def boll(src,length,m):
    n=len(src); up=[None]*n; lo=[None]*n; s=ss=0.0
    for i in range(n):
        v=src[i]; s+=v; ss+=v*v
        if i>=length: rm=src[i-length]; s-=rm; ss-=rm*rm
        if i>=length-1:
            mean=s/length; var=ss/length-mean*mean
            if var<0: var=0.0
            d=m*math.sqrt(var); up[i]=mean+d; lo[i]=mean-d
    return up,lo
def kst(e): e=e//1000 if e>1e11 else e; return time.strftime("%Y-%m-%d %H:%M",time.gmtime(e+9*3600))

def v3_trade(bars,fb,limit,d,ktr):
    LONG=(d=="LONG"); n=len(bars)
    E=[limit-KSTEP[k]*ktr if LONG else limit+KSTEP[k]*ktr for k in range(3)]
    filled=[True,False,False]; fillbar=[fb,None,None]; maxk=0
    peak=bars[fb][2] if LONG else bars[fb][3]
    for i in range(fb,min(n,fb+MAXSCAN)):
        h=bars[i][2]; l=bars[i][3]
        for k in range(1,3):
            if not filled[k] and ((LONG and l<=E[k]) or ((not LONG) and h>=E[k])): filled[k]=True; fillbar[k]=i
        maxk=max(k for k in range(3) if filled[k])
        if LONG: peak=max(peak,h)
        else:    peak=min(peak,l)
        deepest=E[maxk]
        if LONG:
            sl=max(deepest-M*ktr,peak-N*ktr)
            if l<=sl:
                ex=sl-SLIP; pnl=sum(LOTS[k]*(ex-(E[k]+SLIP)) for k in range(maxk+1))/ktr
                return {"E":E,"fillbar":fillbar,"maxk":maxk,"exbar":i,"expx":round(ex,3),"pnl":round(pnl,2),"sl":round(sl,3)}
        else:
            sl=min(deepest+M*ktr,peak+N*ktr)
            if h>=sl:
                ex=sl+SLIP; pnl=sum(LOTS[k]*((E[k]-SLIP)-ex) for k in range(maxk+1))/ktr
                return {"E":E,"fillbar":fillbar,"maxk":maxk,"exbar":i,"expx":round(ex,3),"pnl":round(pnl,2),"sl":round(sl,3)}
    j=min(n-1,fb+MAXSCAN-1); c=bars[j][4]
    pnl=sum(LOTS[k]*((c-SLIP)-(E[k]+SLIP) if LONG else (E[k]-SLIP)-(c+SLIP)) for k in range(maxk+1))/ktr
    return {"E":E,"fillbar":fillbar,"maxk":maxk,"exbar":j,"expx":round(c,3),"pnl":round(pnl,2),"sl":None}

DATA={}
for tf in ["5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    opens=[b[1] for b in bars]; u2,l2=boll(opens,4,4.0)
    sig=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None: continue
            k=float(s[8]) if s[8] else 0.0
            if k>0: sig.append((bi,s[4],k))
    sig.sort()
    fills=[]
    for s in range(len(sig)):
        bi,d,ktr=sig[s]; nb=sig[s+1][0] if s+1<len(sig) else len(bars)
        lim=l2[bi] if d=="LONG" else u2[bi]
        if lim is None: continue
        for j in range(bi+1,min(nb,len(bars))):
            if (d=="LONG" and bars[j][3]<=lim) or (d=="SHORT" and bars[j][2]>=lim):
                fills.append((bi,j,d,ktr,lim)); break
    fills=fills[-10:]
    charts=[]
    for bi,fb,d,ktr,lim in fills:
        tr=v3_trade(bars,fb,lim,d,ktr)
        lo=max(0,bi-12); hi=min(len(bars),min(tr["exbar"]+4,bi+160))
        win=[]
        for i in range(lo,hi):
            t,o,h,l,c=bars[i]
            win.append({"o":round(o,3),"h":round(h,3),"l":round(l,3),"c":round(c,3),
                        "b2u":round(u2[i],3) if u2[i] else None,"b2l":round(l2[i],3) if l2[i] else None})
        gf=[]
        for k in range(tr["maxk"]+1):
            fbk=tr["fillbar"][k]
            if fbk is not None: gf.append({"k":k,"dt":kst(bars[fbk][0]),"px":round(tr["E"][k],3),"bk":fbk-lo})
        charts.append({"dir":d,"ktr":round(ktr,3),"brk_dt":kst(bars[bi][0]),"fill_dt":kst(bars[fb][0]),
                       "limit":round(lim,3),"E":[round(e,3) for e in tr["E"]],"stopline":tr["sl"],
                       "ex_dt":kst(bars[tr["exbar"]][0]),"ex_px":tr["expx"],"pnl":tr["pnl"],
                       "bk":bi-lo,"fk":fb-lo,"ek":tr["exbar"]-lo,"gf":gf,"bars":win})
    DATA[tf]=charts
    print(f"{tf}: v3 최근 체결 {len(charts)}개 (마지막 체결 {charts[-1]['fill_dt'] if charts else '-'})")

HTML="""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>v3 최근 10트레이드 (TradingView 대조)</title>
<style>
*{box-sizing:border-box}body{font-family:'Malgun Gothic','Segoe UI',sans-serif;background:#0f1320;color:#dfe6f0;margin:0;padding:16px}
h1{color:#4fc3f7;font-size:1.2em;text-align:center;margin:0 0 4px}
.sub{text-align:center;color:#7e8aa0;font-size:.78em;margin-bottom:8px}
.ctl{display:flex;gap:5px;flex-wrap:wrap;justify-content:center;margin:5px 0}
.btn{padding:5px 10px;border:1px solid #345;background:transparent;color:#9cf;border-radius:6px;cursor:pointer;font-size:.8em}
.btn.on{background:#4fc3f7;color:#0f1320;font-weight:bold}
canvas{background:#121a2e;border-radius:8px;width:100%;max-width:1000px;display:block;margin:6px auto}
table{margin:8px auto;border-collapse:collapse;font-size:.82em;max-width:760px;width:100%}
td,th{padding:4px 9px;border-bottom:1px solid #243150;text-align:left}
th{color:#9cc4e8;width:32%}.r{text-align:right}
.good{color:#5fd97e}.bad{color:#ff6f6f}
.lg{text-align:center;font-size:.7em;color:#8aa;margin-top:4px}
</style></head><body>
<h1>v3 고정밴드 리밋 — 최근 10트레이드 (TradingView 대조)</h1>
<div class=sub>리밋=돌파봉 반대편 4/4밴드 · 그리드 0/−1/−2KTR(랏1/2/3) · 트레일SL max(deepest−1, peak−1)KTR · slip 0.3 · 시각=KST</div>
<div class=ctl id=tfsel></div>
<div class=ctl id=ixsel></div>
<canvas id=cv width=1000 height=420></canvas>
<table id=tbl></table>
<div class=lg>캔들 양/음 · <span style="color:#ff8a8a">붉은선</span>=BB2(4/4) · <span style="color:#ffd54f">노랑</span>=리밋/진입 · 점선=그리드 −1/−2 · <span style="color:#ff5555">빨강</span>=SL청산 · 세로 노란점선=돌파봉</div>
<script>
const D=__DATA__;let tf='10m',ix=0;
function mk(host,opts,cur,cb){const h=document.getElementById(host);h.innerHTML='';opts.forEach(o=>{const b=document.createElement('button');b.className='btn'+(o[0]===cur()?' on':'');b.textContent=o[1];b.onclick=()=>{cb(o[0]);render()};h.appendChild(b)})}
function render(){
 mk('tfsel',[['5m','5분'],['10m','10분']],()=>tf,v=>{tf=v;ix=0;});
 const ch=D[tf];if(ix>=ch.length)ix=0;
 mk('ixsel',ch.map((c,i)=>[i,''+(i+1)]),()=>ix,v=>ix=v);
 const c=ch[ix];
 let g=c.gf.map(f=>`<tr><th>그리드 ${f.k}차 체결</th><td>${f.dt} @ ${f.px}</td></tr>`).join('');
 document.getElementById('tbl').innerHTML=
  `<tr><th>방향 / KTR</th><td>${c.dir} / ${c.ktr}</td></tr>
   <tr><th>돌파봉(리밋 산출)</th><td>${c.brk_dt}</td></tr>
   <tr><th>리밋(진입가)=반대밴드</th><td>${c.limit}</td></tr>
   <tr><th>리밋 체결</th><td>${c.fill_dt} @ ${c.limit}</td></tr>
   ${g}
   <tr><th>SL 청산</th><td>${c.ex_dt} @ ${c.ex_px}</td></tr>
   <tr><th>손익(KTR-lot)</th><td class=${c.pnl>=0?'good':'bad'}>${c.pnl>=0?'+':''}${c.pnl}</td></tr>`;
 draw(c);
}
function draw(c){
 const cv=document.getElementById('cv'),x=cv.getContext('2d'),W=cv.width,H=cv.height,padL=58,padR=10,padT=10,padB=20;
 x.clearRect(0,0,W,H);const B=c.bars,n=B.length;
 let lo=1e9,hi=-1e9;B.forEach(b=>{lo=Math.min(lo,b.l);hi=Math.max(hi,b.h);});
 c.E.forEach(v=>{lo=Math.min(lo,v);hi=Math.max(hi,v);});if(c.stopline){lo=Math.min(lo,c.stopline);hi=Math.max(hi,c.stopline);}
 const p=(hi-lo)*0.05;lo-=p;hi+=p;const PW=W-padL-padR,bw=PW/n;
 const X=i=>padL+bw*(i+0.5),Y=v=>padT+(H-padT-padB)*(1-(v-lo)/(hi-lo));
 x.font='10px sans-serif';
 for(let g=0;g<=4;g++){const v=lo+(hi-lo)*g/4,yy=Y(v);x.strokeStyle='#1b2740';x.beginPath();x.moveTo(padL,yy);x.lineTo(W-padR,yy);x.stroke();x.fillStyle='#566';x.fillText(v.toFixed(2),4,yy+3);}
 // BB2
 function line(key,col){x.strokeStyle=col;x.lineWidth=1;x.beginPath();let st=false;B.forEach((b,i)=>{const v=b[key];if(v==null){st=false;return;}const xx=X(i),yy=Y(v);st?x.lineTo(xx,yy):x.moveTo(xx,yy);st=true;});x.stroke();}
 line('b2u','#ff8a8a');line('b2l','#ff8a8a');
 // 그리드 -1/-2 점선
 x.setLineDash([3,3]);x.strokeStyle='#667';
 [1,2].forEach(k=>{const yy=Y(c.E[k]);x.beginPath();x.moveTo(padL,yy);x.lineTo(W-padR,yy);x.stroke();x.fillStyle='#889';x.fillText('-'+k+'KTR '+c.E[k],W-padR-90,yy-2);});
 x.setLineDash([]);
 // 리밋(진입) 라인
 const yl=Y(c.E[0]);x.strokeStyle='#ffd54f';x.lineWidth=1.3;x.beginPath();x.moveTo(padL,yl);x.lineTo(W-padR,yl);x.stroke();x.fillStyle='#ffd54f';x.fillText('리밋 '+c.E[0],W-padR-90,yl-2);
 // SL
 if(c.stopline){const ys=Y(c.stopline);x.strokeStyle='#ff5555';x.lineWidth=1.3;x.beginPath();x.moveTo(padL,ys);x.lineTo(W-padR,ys);x.stroke();x.fillStyle='#ff7777';x.fillText('SL '+c.stopline,W-padR-90,ys-2);}
 // 캔들
 B.forEach((b,i)=>{const up=b.c>=b.o,col=up?'#8fdc4e':'#ff4d4d';x.strokeStyle=col;x.fillStyle=col;const xc=X(i);
  x.lineWidth=1;x.beginPath();x.moveTo(xc,Y(b.h));x.lineTo(xc,Y(b.l));x.stroke();
  const yo=Y(b.o),yc=Y(b.c);x.fillRect(xc-bw*0.32,Math.min(yo,yc),bw*0.64,Math.max(1,Math.abs(yc-yo)));});
 // 돌파봉 세로선 + 체결/청산 마커
 const xb=X(c.bk);x.strokeStyle='#ffd54f';x.setLineDash([2,2]);x.lineWidth=1;x.beginPath();x.moveTo(xb,padT);x.lineTo(xb,H-padB);x.stroke();x.setLineDash([]);
 const xf=X(c.fk);x.fillStyle='#ffd54f';x.beginPath();x.arc(xf,Y(c.E[0]),4,0,7);x.fill();
 const xe=X(c.ek);x.strokeStyle='#ff5555';x.lineWidth=2;x.beginPath();x.moveTo(xe-4,Y(c.ex_px)-4);x.lineTo(xe+4,Y(c.ex_px)+4);x.moveTo(xe+4,Y(c.ex_px)-4);x.lineTo(xe-4,Y(c.ex_px)+4);x.stroke();
}
render();
</script></body></html>"""
with open("../result/v3_recent.html","w",encoding="utf-8") as f:
    f.write(HTML.replace("__DATA__",json.dumps(DATA,ensure_ascii=False)))
print("-> ../result/v3_recent.html")
