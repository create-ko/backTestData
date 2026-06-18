# -*- coding: utf-8 -*-
"""47 — 실패 거래 멀티-TF 캔들 뷰어(fail_charts.html).
전략 분봉(2m/5m/10m 각각의 v1 풀스톱 25·26) × 차트 분봉(2m/5m/10m/1h/2h 토글).
지표: BB20/2(흰), BB4/4(빨강), SMA20(노랑), SMA120(하늘). 캔들 상승=연두/하락=빨강.
진입/그리드/스톱선. 1h·2h는 10m 리샘플. '전략 분봉'과 '차트 분봉'을 분리해 안 헷갈리게."""
import csv, math, json
MULT=[0,1,2,3,4,4.5]; STOPM=5.0; TP=1.5; B6X=1.0; START_H=8

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); t=t//1000 if t>1e11 else t
            idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def resample(b10,period):
    out=[]; cur=None
    for t,o,h,l,c in b10:
        g=(t//period)*period
        if cur is None or cur[0]!=g:
            if cur: out.append(tuple(cur))
            cur=[g,o,h,l,c]
        else: cur[2]=max(cur[2],h); cur[3]=min(cur[3],l); cur[4]=c
    if cur: out.append(tuple(cur))
    return out
def calib(tf):
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def khour(e,off): return ((e//3600)+off)%24
def bbcalc(bars,length,m,si):
    n=len(bars); up=[None]*n; lo=[None]*n; s=ss=0.0
    for i in range(n):
        v=bars[i][si]; s+=v; ss+=v*v
        if i>=length: rm=bars[i-length][si]; s-=rm; ss-=rm*rm
        if i>=length-1:
            mean=s/length; var=ss/length-mean*mean
            if var<0: var=0.0
            d=m*math.sqrt(var); up[i]=mean+d; lo[i]=mean-d
    return up,lo
def sma(bars,n,si):
    out=[None]*len(bars); s=0.0
    for i in range(len(bars)):
        s+=bars[i][si]
        if i>=n: s-=bars[i-n][si]
        if i>=n-1: out[i]=s/n
    return out
def sim_stop(bars, eb, anchor, direction, base):
    n=len(bars)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*STOPM
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; mfe=0;mae=0
    for i in range(eb,n):
        t,o,h,l,c=bars[i]
        if direction=="LONG": mfe=max(mfe,(h-anchor)/base); mae=max(mae,(anchor-l)/base)
        else: mfe=max(mfe,(anchor-l)/base); mae=max(mae,(h-anchor)/base)
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return "STOP",mfe,mae,i
            if h>=tp: return "WIN",mfe,mae,i
        else:
            if fc>=6 and h>=stop: return "STOP",mfe,mae,i
            if l<=tp: return "WIN",mfe,mae,i
    return "OPEN",mfe,mae,n-1
def nearest_idx(bars,ep):
    lo,hi=0,len(bars)-1
    while lo<hi:
        m=(lo+hi)//2
        if bars[m][0]<ep: lo=m+1
        else: hi=m
    return lo
def r1(v): return round(v,1) if v is not None else None

print("차트용 분봉 로딩...")
disp={}
disp["2m"],_=load("xauusd_2m_2010-01-01_2026-06-16.csv")
disp["5m"],_=load("xauusd_5m_2010-01-01_2026-06-16.csv")
disp["10m"],i10=load("xauusd_10m_2010-01-01_2026-06-16.csv")
disp["1h"]=resample(disp["10m"],3600)
disp["2h"]=resample(disp["10m"],7200)
off=calib("10m")
print("차트 분봉별 지표 1회 계산...")
IND={}
for tf in ["2m","5m","10m","1h","2h"]:
    bb1u,bb1l=bbcalc(disp[tf],20,2.0,4)
    bb2u,bb2l=bbcalc(disp[tf],4,4.0,1)
    IND[tf]=(bb1u,bb1l,bb2u,bb2l,sma(disp[tf],20,4),sma(disp[tf],120,4))
    print(f"  {tf} 지표 완료")

WIN={"2m":(45,32),"5m":(45,32),"10m":(50,38),"1h":(70,45),"2h":(55,38)}
def window(ctf,ep):
    bars=disp[ctf]; ei=nearest_idx(bars,ep); lead,trail=WIN[ctf]
    s0=max(0,ei-lead); s1=min(len(bars),ei+trail)
    bb1u,bb1l,bb2u,bb2l,s20,s120=IND[ctf]
    cs=[];b1u=[];b1l=[];b2u=[];b2l=[];m20=[];m120=[];eidx=0
    for j in range(s0,s1):
        t,o,h,l,c=bars[j]
        cs.append([t,r1(o),r1(h),r1(l),r1(c)])
        b1u.append(r1(bb1u[j]));b1l.append(r1(bb1l[j]))
        b2u.append(r1(bb2u[j]));b2l.append(r1(bb2l[j]))
        m20.append(r1(s20[j]));m120.append(r1(s120[j]))
        if j==ei: eidx=len(cs)-1
    return {"c":cs,"b1u":b1u,"b1l":b1l,"b2u":b2u,"b2l":b2l,"s20":m20,"s120":m120,"ei":eidx}

# 전략 분봉별 v1 풀스톱
STRATS={}
for stf in ["2m","5m","10m"]:
    print(f"전략 {stf} 실패 추출...")
    sbars,sidx=load(f"xauusd_{stf}_2010-01-01_2026-06-16.csv") if stf not in ("2m","5m","10m") else (disp[stf], (i10 if stf=="10m" else None))
    # idx 필요: 2m/5m는 별도 idx 생성
    if stf=="10m": sidx=i10
    else:
        sidx={}
        for ii,bb in enumerate(disp[stf]): sidx[bb[0]]=ii
    sbars=disp[stf]
    soff=calib(stf)
    sigs=[]
    with open(f"signals_{stf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=sidx.get(int(s[2]))
            if bi is None or bi+1>=len(sbars): continue
            k=float(s[8])
            if k>0: sigs.append((bi,float(s[7]),s[4],k,s[1]))
    sigs.sort(key=lambda x:x[0])
    flist=[]; busy=-1
    for bi,a,d,k,dt in sigs:
        if bi<=busy: continue
        eb=bi+1
        if khour(sbars[eb][0],soff)<START_H: continue
        kind,mfe,mae,exi=sim_stop(sbars,eb,a,d,k); busy=exi
        if kind=="STOP" and dt[:4] in ("2025","2026"):
            ep=sbars[eb][0]
            F={"dt":dt,"dir":d,"ktr":round(k,2),"anchor":r1(a),
               "stop":r1(a-k*STOPM if d=="LONG" else a+k*STOPM),
               "mfe":round(mfe,2),"mae":round(mae,2),"tf":{}}
            for ctf in ["2m","5m","10m","1h","2h"]:
                F["tf"][ctf]=window(ctf,ep)
            flist.append(F)
    STRATS[stf]=flist
    print(f"  {stf}: {len(flist)}건")

DATA={"strats":STRATS,"off":off}
html=r"""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8><title>실패거래 멀티TF 차트</title>
<style>
body{font-family:'Malgun Gothic',sans-serif;background:#0e1220;color:#dfe6f0;margin:0;padding:12px}
h1{color:#4fc3f7;font-size:1.1em;margin:2px 0 8px;text-align:center}
.bar{display:flex;gap:7px;justify-content:center;flex-wrap:wrap;margin:7px 0;align-items:center}
.lab{color:#7e8aa0;font-size:.78em;margin-right:2px}
.btn{padding:5px 11px;border:1px solid #345;background:transparent;color:#9cf;border-radius:6px;cursor:pointer;font-size:.8em}
.btn.on{background:#4fc3f7;color:#0e1220;font-weight:bold}
.btn.strat.on{background:#ffb347;color:#0e1220;border-color:#ffb347}
select{background:#16203a;color:#dfe6f0;border:1px solid #345;border-radius:6px;padding:5px;font-size:.8em;max-width:360px}
.info{text-align:center;font-size:.84em;color:#c4cfde;margin:6px 0}
.info b{color:#fff}.red{color:#ff6f6f}.grn{color:#8fdc4e}
canvas{background:#0c1426;border-radius:8px;width:100%;display:block;margin-top:6px}
.lg{text-align:center;font-size:.7em;color:#8493a8;margin-top:4px}
.sw{display:inline-block;width:14px;height:0;border-top:2px solid;margin:0 3px 0 9px;vertical-align:middle}
</style></head><body>
<h1>실패 거래 멀티-TF 캔들 뷰어 (v1 풀스톱 · 2025·2026)</h1>
<div class=bar><span class=lab>전략 분봉:</span><span id=stratbar></span></div>
<div class=bar>
 <button class=btn id=prev>◀</button>
 <select id=sel></select>
 <button class=btn id=next>▶</button>
</div>
<div class=bar><span class=lab>차트 분봉:</span><span id=tfbar></span></div>
<div class=info id=info></div>
<canvas id=cv width=1180 height=470></canvas>
<div class=lg>
 <span class=sw style="border-color:#ffffff"></span>BB 20/2(흰)
 <span class=sw style="border-color:#ff3b3b"></span>BB 4/4(빨강)
 <span class=sw style="border-color:#ffd24a"></span>SMA20
 <span class=sw style="border-color:#29b6f6"></span>SMA120
 <span class=sw style="border-color:#ff5555"></span>진입가
 <span class=sw style="border-color:#888"></span>그리드
 <span class=sw style="border-color:#ff2222;border-top-style:dashed"></span>손절
 <span class=sw style="border-color:#ff66cc;border-top-style:dashed"></span>진입봉
 · 상승=연두/하락=빨강
</div>
<script>
const D=__DATA__, off=D.off;
let stf='10m', fi=0, ctf='2h';
const TFS=['2m','5m','10m','1h','2h'];
const sel=document.getElementById('sel');
function kdt(ep){const d=new Date((ep+off*3600)*1000);return d.toISOString().slice(0,16).replace('T',' ');}
function fillSel(){sel.innerHTML='';D.strats[stf].forEach((f,i)=>{const o=document.createElement('option');o.value=i;o.text=`${i+1}. ${f.dt} ${f.dir} (KTR ${f.ktr}, MFE ${f.mfe})`;sel.appendChild(o);});}
function mkStrat(){const h=document.getElementById('stratbar');h.innerHTML='';[['2m','2분'],['5m','5분'],['10m','10분']].forEach(([t,l])=>{const b=document.createElement('button');b.className='btn strat'+(t===stf?' on':'');b.textContent=`${l} (${D.strats[t].length})`;b.onclick=()=>{stf=t;fi=0;fillSel();render()};h.appendChild(b)});}
function mkTF(){const h=document.getElementById('tfbar');h.innerHTML='';TFS.forEach(t=>{const b=document.createElement('button');b.className='btn'+(t===ctf?' on':'');b.textContent=t;b.onclick=()=>{ctf=t;render()};h.appendChild(b)});}
function render(){
 mkStrat();mkTF();sel.value=fi;
 const F=D.strats[stf][fi], T=F.tf[ctf], cs=T.c;
 document.getElementById('info').innerHTML=`<b>[${stf} 전략 #${fi+1}/${D.strats[stf].length}]</b> ${F.dt} · <b class=${F.dir==='LONG'?'grn':'red'}>${F.dir}</b> · KTR ${F.ktr} · MFE <b>${F.mfe}</b> / MAE <b>${F.mae}</b> · <span class=red>풀스톱</span> · 차트[${ctf}]`;
 const cv=document.getElementById('cv'),x=cv.getContext('2d'),W=cv.width,H=cv.height;
 x.clearRect(0,0,W,H);const padL=58,padR=12,padT=12,padB=22;
 let mn=1e9,mx=-1e9;
 cs.forEach(c=>{mn=Math.min(mn,c[3]);mx=Math.max(mx,c[2]);});
 [F.anchor,F.stop].forEach(v=>{mn=Math.min(mn,v);mx=Math.max(mx,v);});
 const pd=(mx-mn)*0.05;mn-=pd;mx+=pd;
 const n=cs.length,cw=(W-padL-padR)/n;
 const X=i=>padL+cw*(i+0.5), Y=v=>padT+(H-padT-padB)*(1-(v-mn)/(mx-mn));
 x.font='10px sans-serif';
 for(let g=0;g<=5;g++){const v=mn+(mx-mn)*g/5,yy=Y(v);x.strokeStyle='#18233c';x.beginPath();x.moveTo(padL,yy);x.lineTo(W-padR,yy);x.stroke();x.fillStyle='#6b7a90';x.fillText(v.toFixed(1),4,yy+3);}
 function bbline(arr,col,w){x.strokeStyle=col;x.lineWidth=w||1;x.beginPath();let st=false;arr.forEach((v,i)=>{if(v==null){st=false;return;}const xx=X(i),yy=Y(v);if(!st){x.moveTo(xx,yy);st=true;}else x.lineTo(xx,yy);});x.stroke();}
 bbline(T.s120,'#29b6f6',1.4);bbline(T.s20,'#ffd24a',1.4);
 bbline(T.b1u,'#ffffff');bbline(T.b1l,'#ffffff');
 bbline(T.b2u,'#ff3b3b');bbline(T.b2l,'#ff3b3b');
 function hline(v,col,dash){x.strokeStyle=col;x.lineWidth=1;x.setLineDash(dash||[]);x.beginPath();x.moveTo(padL,Y(v));x.lineTo(W-padR,Y(v));x.stroke();x.setLineDash([]);}
 const sgn=F.dir==='LONG'?-1:1;
 for(let g=1;g<6;g++){hline(F.anchor+sgn*F.ktr*[0,1,2,3,4,4.5][g],'#555');}
 hline(F.anchor,'#ff5555');hline(F.stop,'#ff2222',[5,4]);
 x.strokeStyle='#ff66cc';x.lineWidth=1;x.setLineDash([4,3]);x.beginPath();x.moveTo(X(T.ei),padT);x.lineTo(X(T.ei),H-padB);x.stroke();x.setLineDash([]);
 cs.forEach((c,i)=>{const[t,o,h,l,cl]=c;const up=cl>=o;x.strokeStyle=up?'#8fdc4e':'#ff4d4d';x.fillStyle=up?'#8fdc4e':'#ff4d4d';
  x.beginPath();x.moveTo(X(i),Y(h));x.lineTo(X(i),Y(l));x.stroke();
  const y1=Y(o),y2=Y(cl);x.fillRect(X(i)-cw*0.35,Math.min(y1,y2),cw*0.7,Math.max(1,Math.abs(y2-y1)));});
 x.fillStyle='#6b7a90';x.fillText(kdt(cs[0][0]),padL,H-7);x.fillText(kdt(cs[cs.length-1][0]),W-padR-108,H-7);
}
document.getElementById('prev').onclick=()=>{fi=(fi-1+D.strats[stf].length)%D.strats[stf].length;render()};
document.getElementById('next').onclick=()=>{fi=(fi+1)%D.strats[stf].length;render()};
sel.onchange=()=>{fi=+sel.value;render()};
fillSel();render();
</script></body></html>"""
with open("fail_charts.html","w",encoding="utf-8") as f:
    f.write(html.replace("__DATA__",json.dumps(DATA,ensure_ascii=False)))
import os
print(f"→ fail_charts.html ({os.path.getsize('fail_charts.html')/1e6:.1f}MB)")
