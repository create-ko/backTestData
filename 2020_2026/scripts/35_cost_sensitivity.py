# -*- coding: utf-8 -*-
"""35 — 비용 민감도. 확정설정(후방·TP1.5·6차)에서 스프레드(라운드턴$)를 쓸어 net R 변화 + 손익분기 비용.
net R = gross_R - S * K,  K = Σ(체결랏수/KTR$)/|풀스톱|  (비용에 선형).
손익분기 S* = gross_R / K. 분봉×v1/v2. + net R vs 스프레드 HTML 라인차트."""
import csv, math, json
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))  # 24
SPREADS=[0.10,0.20,0.30,0.50,0.70,1.00]
RISK=0.02; YRS=6.46

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
def sim(bars, start_i, anchor, direction, base):
    n=len(bars)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*STOPM
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(start_i,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr = TP if fc<6 else B6X
        tp = deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,("B6" if fc==6 else "TPs")
        else:
            if fc>=6 and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,("B6" if fc==6 else "TPs")
    return maxF,"OPEN"
def pnl_tps(k): exitlv=MULT[k-1]-TP; return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6():   exitlv=MULT[5]-B6X; return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(): return sum(L[i]*(MULT[i]-STOPM) for i in range(6))
def trade(maxF,kind):
    if kind=="STOP": pnl=pnl_stop(); lots=SUM_L
    elif kind=="B6": pnl=pnl_b6();   lots=SUM_L
    else:            pnl=pnl_tps(maxF); lots=sum(L[:maxF])
    return pnl/STOP_R, lots
def v1_jobs(tf,bars,idx):
    out=[]
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: out.append((bi+1,float(s[7]),s[4],k))
    out.sort(key=lambda x:x[0]); return out
def v2_jobs(tf,bars,idx):
    u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    out=[]; pending=None
    for i in range(len(bars)):
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                if i+1<len(bars):
                    k=float(ps[8])
                    if k>0: out.append((i+1,bars[i+1][1],pdir,k)); pending=None
    out.sort(key=lambda x:x[0]); return out
def maxdd_pct(eq):
    peak=eq[0]; mdd=0.0
    for v in eq:
        if v>peak: peak=v
        d=(peak-v)/peak
        if d>mdd: mdd=d
    return 100*mdd

DATA={}
print(f"# 확정설정 후방 {'·'.join(map(str,L))}/TP1.5/6차 - 비용(라운드턴$) 민감도\n")
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv")
    JOBS={"v1":v1_jobs(tf,bars,idx),"v2":v2_jobs(tf,bars,idx)}
    DATA[tf]={}
    print(f"{'='*88}\n=== {tf} ===")
    print(f"{'버전':>4}{'건수':>7}{'grossR':>9}{'손익분기$':>10} | "+ "".join(f"{'$'+format(s,'.2f'):>9}" for s in SPREADS))
    for ver in ["v1","v2"]:
        seq=[]  # (gross_R, lots/KTR)
        for si,a,d,k in JOBS[ver]:
            mf,kind=sim(bars,si,a,d,k)
            if kind not in ("TPs","B6","STOP"): continue
            gR,lots=trade(mf,kind)
            seq.append((gR, lots/k))
        n=len(seq)
        gross=sum(g for g,_ in seq)
        Kc=sum(lk for _,lk in seq)/STOP_R   # 비용계수: net=gross-S*Kc
        be=gross/Kc if Kc>0 else 0
        netRs=[gross-s*Kc for s in SPREADS]
        # 각 S에서 net CAGR/MDD (선형 net R이지만 곡선은 재계산)
        netinfo={}
        for s in SPREADS:
            eq=[1.0]
            for g,lk in seq:
                nr=g - s*(lk)/STOP_R
                eq.append(eq[-1]*(1+RISK*nr))
            cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
            netinfo[s]=(eq[-1], cagr, maxdd_pct(eq))
        row=f"{ver:>4}{n:>7}{gross:>+9.0f}{be:>9.2f} | " + "".join(f"{nr:>+9.0f}" for nr in netRs)
        print(row)
        DATA[tf][ver]={"n":n,"gross":round(gross,1),"be":round(be,2),"Kc":round(Kc,2),
                       "spreads":SPREADS,"netR":[round(x,1) for x in netRs],
                       "cagr":[round(netinfo[s][1],1) for s in SPREADS],
                       "mdd":[round(netinfo[s][2],1) for s in SPREADS]}
    # 손익분기 한눈
    print(f"  → 손익분기 스프레드: v1 ${DATA[tf]['v1']['be']:.2f} / v2 ${DATA[tf]['v2']['be']:.2f}  (이보다 비싸면 적자)")
    print()

# HTML 라인차트: net R vs 스프레드
HTML="""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8><title>비용 민감도</title>
<style>
body{font-family:'Malgun Gothic',sans-serif;background:#12121f;color:#e0e0e0;margin:0;padding:20px}
h1{color:#4fc3f7;text-align:center;font-size:1.2em}.sub{text-align:center;color:#8aa;font-size:.78em;margin-bottom:16px}
.wrap{max-width:860px;margin:0 auto}canvas{background:#15151f;border-radius:8px;width:100%}
.lg{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin:10px 0;font-size:.8em}
.lg span{display:inline-flex;align-items:center;gap:5px}.sw{width:16px;height:3px;display:inline-block}
table{width:100%;border-collapse:collapse;font-size:.78em;margin-top:16px}
th,td{padding:5px 7px;text-align:right;border-bottom:1px solid #263}th{color:#9cf;background:#1a1a2c}
td:first-child,th:first-child{text-align:left}.pos{color:#5fd97e}.neg{color:#ff6b6b}
</style></head><body><div class=wrap>
<h1>비용 민감도 — net 누적 R vs 스프레드</h1>
<div class=sub>확정설정(후방·TP1.5·6차). 0선 위=흑자. 손익분기 스프레드보다 비싸면 적자.</div>
<canvas id=cv width=820 height=400></canvas>
<div class=lg id=lg></div>
<table id=tbl></table>
</div><script>
const DATA=__DATA__;
const SP=[0.10,0.20,0.30,0.50,0.70,1.00];
const COL={'2m-v1':'#ff6b6b','2m-v2':'#ff9e6b','5m-v1':'#ffd54f','5m-v2':'#c5e15f','10m-v1':'#4fc3f7','10m-v2':'#5fd97e'};
function draw(){
 const cv=document.getElementById('cv'),x=cv.getContext('2d');const W=cv.width,H=cv.height,pad=52;
 let all=[];for(const tf in DATA)for(const v in DATA[tf])all=all.concat(DATA[tf][v].netR);
 const mn=Math.min(...all,0),mx=Math.max(...all);
 const X=s=>pad+(W-pad-12)*((s-0.1)/(1.0-0.1));
 const Y=v=>H-pad-(H-pad-20)*((v-mn)/(mx-mn));
 x.strokeStyle='#3a5';x.lineWidth=1.5;x.beginPath();x.moveTo(pad,Y(0));x.lineTo(W-12,Y(0));x.stroke();
 x.fillStyle='#678';x.font='10px sans-serif';
 for(let g=0;g<=5;g++){const v=mn+(mx-mn)*g/5,yy=Y(v);x.strokeStyle='#1e2a3a';x.beginPath();x.moveTo(pad,yy);x.lineTo(W-12,yy);x.stroke();x.fillText(v.toFixed(0)+'R',8,yy+3);}
 SP.forEach(s=>{x.fillStyle='#789';x.fillText('$'+s.toFixed(2),X(s)-12,H-pad+16);});
 for(const tf in DATA)for(const v in DATA[tf]){const d=DATA[tf][v],key=tf+'-'+v;
  x.strokeStyle=COL[key];x.lineWidth=2.4;x.beginPath();
  d.netR.forEach((r,i)=>{const xx=X(SP[i]),yy=Y(r);i?x.lineTo(xx,yy):x.moveTo(xx,yy)});x.stroke();
  d.netR.forEach((r,i)=>{x.fillStyle=COL[key];x.beginPath();x.arc(X(SP[i]),Y(r),3,0,7);x.fill();});}
 x.fillStyle='#789';x.fillText('스프레드(라운드턴 $/랏) →',W-200,H-8);
}
let lg='';for(const tf in DATA)for(const v in DATA[tf]){const key=tf+'-'+v;lg+=`<span><span class=sw style="background:${COL[key]}"></span>${key} (손익분기 $${DATA[tf][v].be})</span>`;}
document.getElementById('lg').innerHTML=lg;
let h='<tr><th>TF·버전</th><th>손익분기$</th>'+SP.map(s=>'<th>$'+s.toFixed(2)+'</th>').join('')+'</tr>';
for(const tf in DATA)for(const v in DATA[tf]){const d=DATA[tf][v];
 h+=`<tr><td>${tf} ${v}</td><td>$${d.be}</td>`+d.netR.map(r=>`<td class=${r>=0?'pos':'neg'}>${r>=0?'+':''}${r}R</td>`).join('')+'</tr>';}
document.getElementById('tbl').innerHTML=h;
draw();
</script></body></html>"""
with open("cost_sensitivity.html","w",encoding="utf-8") as f: f.write(HTML.replace("__DATA__",json.dumps(DATA)))
print("→ cost_sensitivity.html")
