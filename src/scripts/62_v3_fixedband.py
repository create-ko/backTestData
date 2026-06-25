# -*- coding: utf-8 -*-
"""62 - v3 고정밴드 리밋 전략 검증.
진입: 돌파봉의 반대편 4/4밴드(고정 스냅샷)에 리밋. 매수돌파->하단밴드 매수 / 매도돌파->상단밴드 매도.
      리밋은 다음 돌파 나올 때까지 유효(다음 돌파 전 가격이 닿으면 체결).
체결 후: 그리드 3포지션(밴드 / -1KTR / -2KTR), 랏 1/2/3.
청산: KTR 트레일링 SL = max(가장깊은체결 - M*KTR, 고점 - N*KTR). 위로만 래칫. 고정 TP 없음.
비용: 슬리피지 0.3 불리(체결 +0.3 / 청산 -0.3, LONG 기준). KST 08~24 진입. base=KTR.
1R = 최악손실(3체결 즉시손절) = 10 KTR-lot. 2% 복리로 CAGR/MDD. N 스윕 0.5/1.0/1.5.
data/에서 실행. 콘솔 ASCII만(규칙3)."""
import csv, math, time

KTRSTEP=[0,1,2]; LOTS=[1,2,3]; SUM_L=sum(LOTS); M=1.0; NS=[0.5,1.0,1.5]
SLIP=0.3; RISK=0.02; MAXSCAN=3000
RNORM=sum(LOTS[i]*((KTRSTEP[-1]+M)-KTRSTEP[i]) for i in range(3))  # 최악손실 KTR-lot = 10

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
def calib(tf):
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def khour(e,off): e=e//1000 if e>1e11 else e; return ((e//3600)+off)%24
def kyear(e,off): e=e//1000 if e>1e11 else e; return time.strftime("%Y",time.gmtime(e+off*3600))

def trade(bars, fb, limit, d, ktr, N):
    """fb=체결봉. limit=진입가(밴드). 반환 (exit_bar, pnl_ktrlot)."""
    LONG=(d=="LONG"); n=len(bars)
    E=[limit-KTRSTEP[k]*ktr if LONG else limit+KTRSTEP[k]*ktr for k in range(3)]
    filled=[True,False,False]; maxk=0
    peak=bars[fb][2] if LONG else bars[fb][3]
    for i in range(fb,min(n,fb+MAXSCAN)):
        h=bars[i][2]; l=bars[i][3]
        for k in range(1,3):
            if not filled[k] and ((LONG and l<=E[k]) or ((not LONG) and h>=E[k])): filled[k]=True
        maxk=max(k for k in range(3) if filled[k])
        if LONG: peak=max(peak,h)
        else:    peak=min(peak,l)
        deepest=E[maxk]
        if LONG:
            sl=max(deepest-M*ktr, peak-N*ktr)
            if l<=sl:
                ex=sl-SLIP
                pnl=sum(LOTS[k]*((ex)-(E[k]+SLIP)) for k in range(maxk+1))/ktr
                return i,pnl
        else:
            sl=min(deepest+M*ktr, peak+N*ktr)
            if h>=sl:
                ex=sl+SLIP
                pnl=sum(LOTS[k]*((E[k]-SLIP)-(ex)) for k in range(maxk+1))/ktr
                return i,pnl
    # 미청산: 마지막가로 정리
    c=bars[min(n-1,fb+MAXSCAN-1)][4]
    if LONG: pnl=sum(LOTS[k]*(c-SLIP-(E[k]+SLIP)) for k in range(maxk+1))/ktr
    else:    pnl=sum(LOTS[k]*((E[k]-SLIP)-(c+SLIP)) for k in range(maxk+1))/ktr
    return min(n-1,fb+MAXSCAN-1),pnl

def maxdd(eq):
    peak=eq[0]; m=0.0
    for v in eq:
        if v>peak: peak=v
        dd=(peak-v)/peak
        if dd>m: m=dd
    return 100*m

print(f"# v3 고정밴드 리밋 | 그리드 0/-1/-2 랏1/2/3 | SL=max(deepest-{M}, peak-N)KTR | slip {SLIP} | 1R={RNORM}KTR-lot | 2% 복리\n")
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); off=calib(tf)
    opens=[b[1] for b in bars]; u2,l2=boll(opens,4,4.0)
    # 돌파 신호 목록 (bi, dir, ktr)
    sig=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None: continue
            k=float(s[8]) if s[8] else 0.0
            if k>0: sig.append((bi,s[4],k))
    sig.sort()
    span=(bars[-1][0]-bars[0][0]); span=span/1000 if span>1e11 else span; YRS=span/(365.25*86400)
    # 체결 가능한 진입(다음 돌파 전 리밋 터치) 목록 — N과 무관(체결 시점 동일)
    fills=[]   # (fb, limit, dir, ktr, year)
    for s in range(len(sig)):
        bi,d,ktr=sig[s]; nb=sig[s+1][0] if s+1<len(sig) else len(bars)
        lim=l2[bi] if d=="LONG" else u2[bi]
        if lim is None: continue
        for j in range(bi+1,min(nb,len(bars))):
            lo=bars[j][3]; hi=bars[j][2]
            if (d=="LONG" and lo<=lim) or (d=="SHORT" and hi>=lim):
                if khour(bars[j][0],off)>=8:
                    fills.append((j,lim,d,ktr,kyear(bars[j][0],off)))
                break
    print(f"=== {tf} (돌파 {len(sig)} -> 리밋체결 {len(fills)}, 체결률 {100*len(fills)/len(sig):.0f}%, 기간 {YRS:.1f}년) ===")
    print(f"{'N':>5}{'거래':>7}{'승률':>8}{'평균R':>9}{'누적R':>9}{'CAGR':>9}{'MDD':>8}")
    for N in NS:
        res=[trade(bars,fb,lim,d,ktr,N) for (fb,lim,d,ktr,yr) in fills]
        rows=sorted([(fills[i][0],res[i][0],res[i][1]/RNORM) for i in range(len(fills))])
        # 순차(겹침 제거) 복리
        eq=[1.0]; cum=0.0; wins=0; busy=-1; nseq=0
        for fb,ex,R in rows:
            if fb<=busy: continue
            nseq+=1; cum+=R; eq.append(eq[-1]*(1+RISK*R)); busy=ex
            if R>0: wins+=1
        cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
        print(f"{N:>5}{nseq:>7}{100*wins/nseq if nseq else 0:>7.1f}%{cum/nseq if nseq else 0:>+9.3f}{cum:>+9.1f}{cagr:>+8.1f}%{maxdd(eq):>7.1f}%")
    print()
