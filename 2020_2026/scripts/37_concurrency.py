# -*- coding: utf-8 -*-
"""37 — 동시 보유 그리드 개수(겹침) + 보유시간. 증거금/자본 요구량의 실제 결정요인.
확정설정. 각 트레이드 [진입봉, 청산봉] → 타임라인 겹침으로 평균/최대 동시보유 산출.
동시보유 N개면 한순간 총리스크 ≈ N×(트레이드당 리스크%), 총노출 ≈ N×13단위."""
import csv, math
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0; SUM_L=sum(L)
TF_MIN={"2m":2,"5m":5,"10m":10}

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
    """(청산봉 index, kind) 반환."""
    n=len(bars)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*STOPM
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1
    for i in range(start_i,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr = TP if fc<6 else B6X
        tp = deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return i,"STOP"
            if h>=tp: return i,"TP"
        else:
            if fc>=6 and h>=stop: return i,"STOP"
            if l<=tp: return i,"TP"
    return n-1,"OPEN"
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

for tf in ["10m","5m","2m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv")
    JOBS={"v1":v1_jobs(tf,bars,idx),"v2":v2_jobs(tf,bars,idx)}
    mins=TF_MIN[tf]
    print(f"\n{'='*78}\n=== {tf} ===")
    for ver in ["v1","v2"]:
        intervals=[]
        for si,a,d,k in JOBS[ver]:
            ex,kind=sim(bars,si,a,d,k)
            intervals.append((si,ex))
        # 보유시간
        holds=[(ex-si+1) for si,ex in intervals]
        holds.sort()
        avg_hold=sum(holds)/len(holds)
        med_hold=holds[len(holds)//2]
        p95_hold=holds[int(len(holds)*0.95)]
        # 겹침(동시보유): 이벤트 스윕
        ev=[]
        for si,ex in intervals: ev.append((si,1)); ev.append((ex+1,-1))
        ev.sort()
        cur=0; peak=0
        # 시간가중 평균: 각 바 구간에서 동시보유수
        # 누적: sum(cur * (next_t - t))
        area=0.0; prevt=ev[0][0]; samples=[]
        for t,delta in ev:
            if t>prevt:
                area+=cur*(t-prevt); samples.append((prevt,t,cur)); prevt=t
            cur+=delta
            if cur>peak: peak=cur
        span=ev[-1][0]-ev[0][0]
        avg_conc=area/span if span>0 else 0
        # 동시보유 분포(시간가중 근사): 각 구간 길이로 가중한 cur의 분위수
        seg=sorted(((c,(b-aa)) for aa,b,c in samples))
        tot=sum(w for _,w in seg); acc=0; p50c=p95c=0
        for c,w in seg:
            acc+=w
            if p50c==0 and acc>=tot*0.5: p50c=c
            if acc>=tot*0.95: p95c=c; break
        print(f" [{ver}] {len(intervals)}건")
        print(f"   보유시간(봉): 중앙 {med_hold} / 평균 {avg_hold:.1f} / 95% {p95_hold}  (= 평균 {avg_hold*mins:.0f}분 = {avg_hold*mins/60:.1f}h)")
        print(f"   동시보유 그리드: 평균 {avg_conc:.1f} / 중앙 {p50c} / 95% {p95c} / 최대 {peak}")
        print(f"   -> 95% 상황 한순간 총리스크 ~ {p95c}x(트레이드리스크%),  총노출 ~ {p95c}x{SUM_L}={p95c*SUM_L}단위")
