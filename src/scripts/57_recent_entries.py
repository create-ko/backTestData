# -*- coding: utf-8 -*-
"""57 - 5분/10분 가장 최근 10개 돌파 진입을 캔들 차트로(HTML).
한 그림에 캔들 + BB1(종가20/2) + BB2(시가4/4) + SMA120 + 진입(돌파 다음봉 시가) 마커
+ 그리드 레벨(0/-1/-2/-3/-4/-4.5 KTR) + 손절(-5). v1/v2/v3 진입 위치가 다 보임.
data/에서 실행. 콘솔 ASCII만(규칙3). 출력: ../result/recent_entries.html"""
import csv, math, json, time

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
def sma(src,length):
    n=len(src); out=[None]*n; s=0.0
    for i in range(n):
        s+=src[i]
        if i>=length: s-=src[i-length]
        if i>=length-1: out[i]=s/length
    return out
def kst(e): e=e//1000 if e>1e11 else e; return time.strftime("%Y-%m-%d %H:%M",time.gmtime(e+9*3600))

BEFORE=20; AFTER=55
DATA={}
for tf in ["5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    closes=[b[4] for b in bars]; opens=[b[1] for b in bars]
    b1u,b1l=boll(closes,20,2.0); b2u,b2l=boll(opens,4,4.0); s120=sma(closes,120)
    # 최근 10개 돌파 신호
    sigs=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8]) if s[8] else 0.0
            if k>0: sigs.append((bi,s[4],float(s[7]),k))
    sigs=sigs[-10:]
    charts=[]
    for bi,d,anchor,ktr in sigs:
        a=bars[bi+1][1]   # 진입가=다음봉 시가
        lo=max(0,bi-BEFORE); hi=min(len(bars),bi+AFTER)
        win=[]
        for i in range(lo,hi):
            t,o,h,l,c=bars[i]
            win.append({"o":round(o,3),"h":round(h,3),"l":round(l,3),"c":round(c,3),
                        "b1u":round(b1u[i],3) if b1u[i] else None,"b1l":round(b1l[i],3) if b1l[i] else None,
                        "b2u":round(b2u[i],3) if b2u[i] else None,"b2l":round(b2l[i],3) if b2l[i] else None,
                        "s120":round(s120[i],3) if s120[i] else None})
        # 그리드 레벨(진입가=다음봉 시가 기준): LONG 아래로, SHORT 위로
        levels=[round(a-k*ktr if d=="LONG" else a+k*ktr,3) for k in [0,1,2,3,4,4.5]]
        stop=round(a-5*ktr if d=="LONG" else a+5*ktr,3)
        charts.append({"dt":kst(bars[bi+1][0]),"dir":d,"ktr":round(ktr,3),"entry":round(a,3),
                       "bk":bi-lo,"ek":bi+1-lo,"levels":levels,"stop":stop,"bars":win})
    DATA[tf]=charts
    print(f"{tf}: 최근 진입 {len(charts)}개 (마지막 {charts[-1]['dt'] if charts else '-'})")

HTML="""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>최근 10개 진입 차트 (5분/10분)</title>
<style>
*{box-sizing:border-box}body{font-family:'Malgun Gothic','Segoe UI',sans-serif;background:#0f1320;color:#dfe6f0;margin:0;padding:16px}
h1{color:#4fc3f7;font-size:1.25em;text-align:center;margin:0 0 8px}
.ctl{display:flex;gap:5px;flex-wrap:wrap;justify-content:center;margin:6px 0}
.btn{padding:5px 11px;border:1px solid #345;background:transparent;color:#9cf;border-radius:6px;cursor:pointer;font-size:.82em}
.btn.on{background:#4fc3f7;color:#0f1320;font-weight:bold}
.info{text-align:center;font-size:.85em;color:#bcd;margin:6px 0}
canvas{background:#121a2e;border-radius:8px;width:100%;max-width:1000px;display:block;margin:0 auto}
.lg{text-align:center;font-size:.72em;color:#8aa;margin-top:6px}
.lg b{color:#dfe6f0}
</style></head><body>
<h1>최근 10개 진입 — 캔들 + 밴드 + 그리드</h1>
<div class=ctl id=tfsel></div>
<div class=ctl id=ixsel></div>
<div class=info id=info></div>
<canvas id=cv width=1000 height=440></canvas>
<div class=lg>캔들: <b style="color:#8fdc4e">양</b>/<b style="color:#ff4d4d">음</b> · 흰선=BB1(20/2) · <span style="color:#ff8a8a">붉은선</span>=BB2(4/4 진입신호밴드) · <span style="color:#7fd4ff">하늘</span>=SMA120 · 점선=그리드(0/−1/−2/−3/−4/−4.5KTR) · <span style="color:#ff5555">굵은선</span>=손절(−5) · 화살표=진입(다음봉 시가)</div>
<script>
const D=__DATA__;let tf='10m',ix=0;
function mk(host,opts,cur,cb){const h=document.getElementById(host);h.innerHTML='';opts.forEach(o=>{const b=document.createElement('button');b.className='btn'+(o[0]===cur()?' on':'');b.textContent=o[1];b.onclick=()=>{cb(o[0]);render()};h.appendChild(b)})}
function render(){
 mk('tfsel',[['5m','5분'],['10m','10분']],()=>tf,v=>{tf=v;ix=0;});
 const ch=D[tf]; if(ix>=ch.length)ix=0;
 mk('ixsel',ch.map((c,i)=>[i,(i+1)+'']),()=>ix,v=>ix=v);
 const c=ch[ix];
 document.getElementById('info').innerHTML=`[${tf}] #${ix+1}/${ch.length} · <b>${c.dt}</b> · ${c.dir=='LONG'?'<span style=color:#8fdc4e>매수</span>':'<span style=color:#ff4d4d>매도</span>'} · 진입 ${c.entry} · KTR ${c.ktr}`;
 draw(c);
}
function draw(c){
 const cv=document.getElementById('cv'),x=cv.getContext('2d'),W=cv.width,H=cv.height,padL=58,padR=10,padT=12,padB=22;
 x.clearRect(0,0,W,H);
 const B=c.bars,n=B.length;
 let lo=1e9,hi=-1e9;
 B.forEach(b=>{lo=Math.min(lo,b.l);hi=Math.max(hi,b.h);});
 c.levels.forEach(v=>{lo=Math.min(lo,v);hi=Math.max(hi,v);}); lo=Math.min(lo,c.stop);hi=Math.max(hi,c.stop);
 const pad=(hi-lo)*0.04;lo-=pad;hi+=pad;
 const PW=W-padL-padR, bw=PW/n;
 const X=i=>padL+bw*(i+0.5), Y=p=>padT+(H-padT-padB)*(1-(p-lo)/(hi-lo));
 // y축 라벨
 x.fillStyle='#566';x.font='10px sans-serif';
 for(let g=0;g<=4;g++){const p=lo+(hi-lo)*g/4,yy=Y(p);x.strokeStyle='#1b2740';x.beginPath();x.moveTo(padL,yy);x.lineTo(W-padR,yy);x.stroke();x.fillStyle='#566';x.fillText(p.toFixed(2),4,yy+3);}
 // 그리드 레벨(점선)
 x.setLineDash([3,3]);x.strokeStyle='#557';
 c.levels.forEach((v,k)=>{const yy=Y(v);x.beginPath();x.moveTo(padL,yy);x.lineTo(W-padR,yy);x.stroke();x.fillStyle='#778';x.fillText((k==5?'-4.5':'-'+k)+'KTR',W-padR-46,yy-2);});
 x.setLineDash([]);
 // 손절선
 const ys=Y(c.stop);x.strokeStyle='#ff5555';x.lineWidth=1.4;x.beginPath();x.moveTo(padL,ys);x.lineTo(W-padR,ys);x.stroke();x.fillStyle='#ff7777';x.fillText('-5 손절',W-padR-46,ys-2);
 // 밴드 라인
 function line(key,col,w){x.strokeStyle=col;x.lineWidth=w;x.beginPath();let st=false;B.forEach((b,i)=>{const v=b[key];if(v==null){st=false;return;}const xx=X(i),yy=Y(v);if(st)x.lineTo(xx,yy);else x.moveTo(xx,yy);st=true;});x.stroke();}
 line('b1u','#cdd6e6',1);line('b1l','#cdd6e6',1);line('b2u','#ff8a8a',1);line('b2l','#ff8a8a',1);line('s120','#7fd4ff',1.3);
 // 캔들
 B.forEach((b,i)=>{const up=b.c>=b.o,col=up?'#8fdc4e':'#ff4d4d';x.strokeStyle=col;x.fillStyle=col;
  const xc=X(i);x.lineWidth=1;x.beginPath();x.moveTo(xc,Y(b.h));x.lineTo(xc,Y(b.l));x.stroke();
  const yo=Y(b.o),yc=Y(b.c),bh=Math.max(1,Math.abs(yc-yo));x.fillRect(xc-bw*0.32,Math.min(yo,yc),bw*0.64,bh);});
 // 돌파봉 강조 + 진입 화살표
 const xb=X(c.bk);x.strokeStyle='#ffd54f';x.lineWidth=1;x.setLineDash([2,2]);x.beginPath();x.moveTo(xb,padT);x.lineTo(xb,H-padB);x.stroke();x.setLineDash([]);
 const xe=X(c.ek),ye=Y(c.entry);x.fillStyle='#ffd54f';
 x.beginPath();if(c.dir=='LONG'){x.moveTo(xe,ye+14);x.lineTo(xe-5,ye+24);x.lineTo(xe+5,ye+24);}else{x.moveTo(xe,ye-14);x.lineTo(xe-5,ye-24);x.lineTo(xe+5,ye-24);}x.fill();
 x.strokeStyle='#ffd54f';x.lineWidth=1;x.beginPath();x.arc(xe,ye,3,0,7);x.stroke();
}
render();
</script></body></html>"""
with open("../result/recent_entries.html","w",encoding="utf-8") as f:
    f.write(HTML.replace("__DATA__",json.dumps(DATA,ensure_ascii=False)))
print("-> ../result/recent_entries.html")
