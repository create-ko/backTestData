# -*- coding: utf-8 -*-
"""38 — 순차(non-overlapping) 룰 재계산. 한 번에 그리드 1개만. 종료 전까지 새 돌파 무시, 종료 후 새 돌파에 재진입.
확정설정(후방 1·1·2·2·3·4/TP1.5/6차/반등탈출). 분봉별·v1/v2·비용$0.30·리스크2%.
겹침 없음 → 복리 수익률% 실현가능. 출력: 진입수(vs 겹침), 연도별 net R·수익%·MDD, 전체 CAGR."""
import csv, math, json
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))
SPREAD=0.30; RISK=0.02; YRS=6.46
YEARS=["2020","2021","2022","2023","2024","2025","2026"]
OVERLAP_CNT={"2m":{"v1":31303,"v2":22673},"5m":{"v1":13016,"v2":9310},"10m":{"v1":6873,"v2":4853}}

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
    """(exit_i, maxF, kind)."""
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
            if fc>=6 and l<=stop: return i,maxF,"STOP"
            if h>=tp: return i,maxF,("B6" if fc==6 else "TPs")
        else:
            if fc>=6 and h>=stop: return i,maxF,"STOP"
            if l<=tp: return i,maxF,("B6" if fc==6 else "TPs")
    return n-1,maxF,"OPEN"
def pnl_tps(k): exitlv=MULT[k-1]-TP; return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6():   exitlv=MULT[5]-B6X; return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(): return sum(L[i]*(MULT[i]-STOPM) for i in range(6))
def trade_R(maxF,kind):
    if kind=="STOP": return pnl_stop()/STOP_R, SUM_L
    if kind=="B6":   return pnl_b6()/STOP_R, SUM_L
    return pnl_tps(maxF)/STOP_R, sum(L[:maxF])

# 순차 진입 리스트 (busy gate)
def seq_v1(tf,bars,idx):
    sigs=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: sigs.append((bi,float(s[7]),s[4],k,s[1][:4]))
    sigs.sort(key=lambda x:x[0])
    out=[]; busy=-1
    for bi,a,d,k,yr in sigs:
        if bi<=busy: continue
        ex,mf,kind=sim(bars,bi+1,a,d,k)
        if kind in ("TPs","B6","STOP"): out.append((mf,kind,k,yr,bi,ex)); busy=ex
    return out
def seq_v2(tf,bars,idx):
    u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    out=[]; pending=None; busy=-1
    for i in range(len(bars)):
        if i<=busy: pending=None; continue   # 보유중: 무시
        if i in brk: pending=(i,brk[i]); continue   # 새 돌파가 기준 갱신
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                if i+1<len(bars):
                    k=float(ps[8])
                    if k>0:
                        ex,mf,kind=sim(bars,i+1,bars[i+1][1],pdir,k)
                        if kind in ("TPs","B6","STOP"): out.append((mf,kind,k,ps[1][:4],pi,ex)); busy=ex
                        pending=None
    return out
def maxdd(eq):
    peak=eq[0]; m=0.0
    for v in eq:
        if v>peak: peak=v
        d=(peak-v)/peak
        if d>m: m=d
    return 100*m

DATA={}
print(f"# 순차(non-overlapping) / 후방 {'·'.join(map(str,L))} / TP1.5 / 6차 / 리스크2% / 비용${SPREAD}\n")
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    DATA[tf]={}
    JOBS={"v1":seq_v1(tf,bars,idx),"v2":seq_v2(tf,bars,idx)}
    for ver in ["v1","v2"]:
        tr=JOBS[ver]; n=len(tr)
        # net R 시퀀스 (시간순: 이미 순차)
        netR=[]; yrs=[]
        wins=0
        for mf,kind,k,yr,bi,ex in tr:
            gR,lots=trade_R(mf,kind)
            nR=gR-lots*(SPREAD/k)/STOP_R
            netR.append(nR); yrs.append(yr)
            if gR>0: wins+=1
        eq=[1.0]
        for r in netR: eq.append(eq[-1]*(1+RISK*r))
        cum=[0.0]
        for r in netR: cum.append(cum[-1]+r)
        # 연도별
        rows=[]
        iy={}
        for j,yr in enumerate(yrs): iy.setdefault(yr,[]).append(j+1)
        for yr in YEARS:
            js=iy.get(yr,[])
            if not js: rows.append((yr,0,0,0,0)); continue
            j0,j1=js[0]-1,js[-1]
            rN=cum[j1]-cum[j0]; ret=100*(eq[j1]/eq[j0]-1); md=maxdd(eq[j0:j1+1])
            rows.append((yr,len(js),round(rN,1),round(ret,1),round(md,1)))
        totR=cum[-1]; totret=100*(eq[-1]-1)
        cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
        mdd=maxdd(eq)
        ov=OVERLAP_CNT[tf][ver]
        print(f"{'='*86}\n=== {tf} {ver}  순차 {n}건 (겹침방식 {ov}건 → {100*n/ov:.0f}%만 진입, 승률 {100*wins/n:.1f}%) ===")
        print(f"{'연도':>6}{'건수':>6}{'net R':>9}{'수익%':>9}{'MDD%':>8}")
        for yr,c,rN,ret,md in rows:
            if c==0: print(f"{yr:>6}{0:>6}"); continue
            print(f"{yr:>6}{c:>6}{rN:>+9.1f}{ret:>+8.1f}%{md:>7.1f}%")
        print(f"{'전체':>6}{n:>6}{totR:>+9.1f}  복리 net {totret:+.0f}% / CAGR {cagr:+.1f}% / 최대MDD {mdd:.1f}%\n")
        DATA[tf][ver]={"n":n,"ov":ov,"winrate":round(100*wins/n,1),"rows":rows,
                       "totR":round(totR,1),"totret":round(totret,0),"cagr":round(cagr,1),"mdd":round(mdd,1)}

with open("sequential_returns.json","w",encoding="utf-8") as f: json.dump(DATA,f,ensure_ascii=False)
print("→ sequential_returns.json 저장")
