# -*- coding: utf-8 -*-
"""66 - 39(순차+시간필터+비용+2%복리)를 (A)봉-OHLC vs (B)1분봉 해소로 나란히.
39와 모든 규칙 동일(후방랏 1·1·2·2·3·4 / TP1.5 / 6차 반등+1.0 / -5손절 / 비용$0.30 / 리스크2% /
KST08~24 진입 / 순차). 차이는 sim 해소 경로뿐:
  A = 39의 sim(): 한 봉서 저가로 그리드 채우고 같은 봉 고가로 TP 판정(같은봉 미래참조).
  B = sim1m(): 1분봉 시간순 해소(미래참조 제거). 미청산은 양쪽 모두 OPEN=무시(busy 미설정, 39와 동일).
1m 캡 120일(드문 OPEN 한정). data/에서 실행. 콘솔 ASCII만(규칙3)."""
import csv, math, time, bisect, json
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))
SPREAD=0.30; RISK=0.02; START_H=8; CAP1M=120*86400

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def calib_offset(tf):
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def khour(epoch,off): e=epoch//1000 if epoch>1e11 else epoch; return ((e//3600)+off)%24
def kyear(epoch,off): e=epoch//1000 if epoch>1e11 else epoch; return time.strftime("%Y",time.gmtime(e+off*3600))
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
def derive_years():
    ys=set()
    with open("signals_10m_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd: ys.add(s[1][:4])
    return sorted(ys)
YEARS=derive_years()

# ---- 해소 A: 봉-OHLC (39 sim과 동일) ----
def simA(bars,start_i,anchor,direction,base):
    n=len(bars)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*STOPM
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(start_i,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); deepest=E[max(k for k in range(6) if filled[k])]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return bars[i][0],maxF,"STOP"
            if h>=tp: return bars[i][0],maxF,("B6" if fc==6 else "TPs")
        else:
            if fc>=6 and h>=stop: return bars[i][0],maxF,"STOP"
            if l<=tp: return bars[i][0],maxF,("B6" if fc==6 else "TPs")
    return bars[n-1][0],maxF,"OPEN"

# ---- 해소 B: 1분봉 시간순 ----
def simB(T1,H1,L1,entry_epoch,anchor,direction,base):
    j0=bisect.bisect_left(T1,entry_epoch); n=len(T1)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*STOPM
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for m in range(j0,n):
        if T1[m]-T1[j0]>CAP1M: return T1[m],maxF,"OPEN"
        h=H1[m]; l=L1[m]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); deepest=E[max(k for k in range(6) if filled[k])]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return T1[m],maxF,"STOP"
            if h>=tp: return T1[m],maxF,("B6" if fc==6 else "TPs")
        else:
            if fc>=6 and h>=stop: return T1[m],maxF,"STOP"
            if l<=tp: return T1[m],maxF,("B6" if fc==6 else "TPs")
    return T1[n-1],maxF,"OPEN"

def pnl_tps(k): exitlv=MULT[k-1]-TP; return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6():   exitlv=MULT[5]-B6X; return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(): return sum(L[i]*(MULT[i]-STOPM) for i in range(6))
def trade_R(maxF,kind):
    if kind=="STOP": return pnl_stop()/STOP_R, SUM_L
    if kind=="B6":   return pnl_b6()/STOP_R, SUM_L
    return pnl_tps(maxF)/STOP_R, sum(L[:maxF])
def maxdd(eq):
    peak=eq[0]; m=0.0
    for v in eq:
        if v>peak: peak=v
        d=(peak-v)/peak
        if d>m: m=d
    return 100*m

def entries_v1(tf,bars,idx,off):
    sigs=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: sigs.append((bi,float(s[7]),s[4],k))
    sigs.sort(key=lambda x:x[0])
    ents=[]   # (brk_epoch, eb_idx, entry_epoch, anchor, dir, ktr)
    for bi,a,d,k in sigs:
        eb=bi+1
        if khour(bars[eb][0],off)<START_H: continue
        ents.append((bars[bi][0],eb,bars[eb][0],a,d,k))
    return ents
def entries_v2(tf,bars,idx,off):
    u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    ents=[]; pending=None
    for i in range(len(bars)):
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                eb=i+1
                if eb<len(bars):
                    k=float(ps[8])
                    if k>0 and khour(bars[eb][0],off)>=START_H:
                        ents.append((bars[pi][0],eb,bars[eb][0],bars[eb][1],pdir,k))
                    pending=None
    return ents

def run(ents,bars,resolver,off,YRS):
    """순차(겹침 제거)+비용+2%복리. resolver(eb,entry_epoch,anchor,dir,base)->(exit_epoch,maxF,kind)."""
    ents=sorted(ents,key=lambda e:e[0])
    netR=[]; yrs=[]; wins=0; busy=-1; n=0
    for brk_ep,eb,ent_ep,a,d,k in ents:
        if brk_ep<=busy: continue
        ex_ep,mf,kind=resolver(eb,ent_ep,a,d,k)
        if kind not in ("TPs","B6","STOP"): continue   # OPEN=무시(busy 미설정)
        gR,lots=trade_R(mf,kind); nR=gR-lots*(SPREAD/k)/STOP_R
        netR.append(nR); yrs.append(kyear(ent_ep,off)); n+=1; busy=ex_ep
        if gR>0: wins+=1
    eq=[1.0]
    for r in netR: eq.append(eq[-1]*(1+RISK*r))
    cum=[0.0]
    for r in netR: cum.append(cum[-1]+r)
    iy={}
    for j,yr in enumerate(yrs): iy.setdefault(yr,[]).append(j+1)
    rows=[]
    for yr in YEARS:
        js=iy.get(yr,[])
        if not js: continue
        j0,j1=js[0]-1,js[-1]
        rows.append((yr,len(js),round(cum[j1]-cum[j0],1),round(100*(eq[j1]/eq[j0]-1),1),round(maxdd(eq[j0:j1+1]),1)))
    cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
    return {"n":n,"winrate":round(100*wins/n,1) if n else 0,"totR":round(cum[-1],1),
            "totret":round(100*(eq[-1]-1),0),"cagr":round(cagr,1),"mdd":round(maxdd(eq),1),"rows":rows}

print("1분봉 로딩...")
T1=[]; H1=[]; L1=[]
with open("xauusd_1m_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
    rd=csv.reader(fp); next(rd)
    for r in rd:
        T1.append(int(float(r[0]))); H1.append(float(r[2])); L1.append(float(r[3]))
print(f"1m {len(T1)}봉\n")

print(f"# 39 재검증: (A)봉-OHLC vs (B)1분봉 | 후방랏/TP1.5/6차/비용${SPREAD}/리스크2%/KST08~24/순차\n")
OUT={}
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); off=calib_offset(tf)
    span=(bars[-1][0]-bars[0][0]); span=span/1000 if span>1e11 else span; YRS=span/(365.25*86400)
    OUT[tf]={}
    for ver,ent_fn in [("v1",entries_v1),("v2",entries_v2)]:
        ents=ent_fn(tf,bars,idx,off)
        rA=run(ents,bars,lambda eb,ep,a,d,k: simA(bars,eb,a,d,k),off,YRS)
        rB=run(ents,bars,lambda eb,ep,a,d,k: simB(T1,H1,L1,ep,a,d,k),off,YRS)
        OUT[tf][ver]={"A":rA,"B":rB}
        print(f"=== {tf} {ver} [{YRS:.2f}년] ===")
        print(f"  {'해소':>6} {'진입':>6} {'승률':>7} {'netR':>8} {'CAGR':>8} {'MDD':>7}")
        for tag,r in [("A-bar",rA),("B-1m",rB)]:
            print(f"  {tag:>6} {r['n']:>6} {r['winrate']:>6.1f}% {r['totR']:>+8.1f} {r['cagr']:>+7.1f}% {r['mdd']:>6.1f}%")
        print()
with open("seq_hours_1m_compare.json","w",encoding="utf-8") as f: json.dump(OUT,f,ensure_ascii=False)
print("-> seq_hours_1m_compare.json")
