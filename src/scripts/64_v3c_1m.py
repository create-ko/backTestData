# -*- coding: utf-8 -*-
"""64 - v3 (c)출구: 이익권에서만 트레일. 1분봉 경로 해소.
그리드 0/-1/-2(랏1/2/3) 보유 -> '가장깊은체결 +1.5KTR' 도달 시 트레일 무장
-> 무장 후 SL=max(평단, 고점-N*KTR) (본전 아래로 안 내려감) / 무장 전 SL=하드(가장깊은체결-M*KTR).
즉 손실 구간선 트레일 안 함. M=1.0, N 스윕 0.5/1.0/1.5, slip 0.3, base=KTR.
1R=10KTR-lot, 2% 복리. 봉내 미래참조 제거(직전 1m peak로 판정 후 peak 갱신).
data/에서 실행. 콘솔 ASCII. 출력: ../result/v3_recent.html 갱신(N=1.0판)."""
import csv, math, time, bisect, json

SLIP=0.3; KSTEP=[0,1,2]; LOTS=[1,2,3]; M=1.0; NS=[0.5,1.0,1.5]; TP=1.5; M1SCAN=20000
RNORM=sum(LOTS[i]*((KSTEP[-1]+M)-KSTEP[i]) for i in range(3))  # 10

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
def calib(tf):
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def khour(e,off): e=e//1000 if e>1e11 else e; return ((e//3600)+off)%24   # 규칙4: 진입(체결) KST 08~24만

print("1분봉 로딩...")
T1=[]; H1=[]; L1=[]
with open("xauusd_1m_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
    rd=csv.reader(fp); next(rd)
    for r in rd:
        T1.append(int(float(r[0]))); H1.append(float(r[2])); L1.append(float(r[3]))
print(f"1m {len(T1)}봉")
def i1(e): return bisect.bisect_left(T1,e)

def resolve(j0,limit,d,ktr,N,want_detail=False):
    LONG=(d=="LONG"); n=len(T1)
    E=[limit-KSTEP[k]*ktr if LONG else limit+KSTEP[k]*ktr for k in range(3)]
    filled=[True,False,False]; maxk=0; gf=[(0,j0,limit)]
    peak=limit; armed=False
    end=min(n,j0+M1SCAN)
    for m in range(j0,end):
        h=H1[m]; l=L1[m]
        for k in range(1,3):
            if not filled[k] and ((LONG and l<=E[k]) or ((not LONG) and h>=E[k])):
                filled[k]=True; maxk=k; gf.append((k,m,E[k])); peak=E[k]; armed=False   # 그리드 체결 시 peak/무장 리셋(평단 후 회복만 트레일)
        deepest=E[maxk]
        num=sum(LOTS[k]*((E[k]+SLIP) if LONG else (E[k]-SLIP)) for k in range(maxk+1)); den=sum(LOTS[:maxk+1]); avg=num/den
        hard=deepest-M*ktr if LONG else deepest+M*ktr
        if armed: sl=max(avg,peak-N*ktr) if LONG else min(avg,peak+N*ktr)
        else:     sl=hard
        if m>j0 and ((LONG and l<=sl) or ((not LONG) and h>=sl)):
            ex=sl-SLIP if LONG else sl+SLIP
            pnl=sum(LOTS[k]*((ex-(E[k]+SLIP)) if LONG else ((E[k]-SLIP)-ex)) for k in range(maxk+1))/ktr
            r={"exj":m,"expx":round(ex,3),"pnl":round(pnl,2),"gf":gf,"sl":round(sl,3),"maxk":maxk,"E":E,"armed":armed}
            return r
        if LONG: peak=max(peak,h)
        else:    peak=min(peak,l)
        if (LONG and peak>=deepest+TP*ktr) or ((not LONG) and peak<=deepest-TP*ktr): armed=True
    return {"exj":end-1,"expx":None,"pnl":0.0,"gf":gf,"sl":None,"maxk":maxk,"E":E,"armed":armed}

def maxdd(eq):
    pk=eq[0]; m=0.0
    for v in eq:
        if v>pk: pk=v
        if (pk-v)/pk>m: m=(pk-v)/pk
    return 100*m

print(f"\n# v3 (c)출구 이익권트레일 | 그리드0/-1/-2 랏1/2/3 | arm=깊은체결+1.5 | 하드=깊은체결-{M} | slip{SLIP} | 1R={RNORM}\n")
RECENT={}
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); tfsec=int(tf[:-1])*60; off=calib(tf)
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
    span=(bars[-1][0]-bars[0][0]); span=span/1000 if span>1e11 else span; YRS=span/(365.25*86400)
    base=[]   # (fj, dir, ktr, lim, bi)
    for s in range(len(sig)):
        bi,d,ktr=sig[s]; lim=l2[bi] if d=="LONG" else u2[bi]
        if lim is None: continue
        a=i1(bars[bi][0]+tfsec); b=i1(bars[sig[s+1][0]][0] if s+1<len(sig) else T1[-1]+1)
        fj=None
        for j in range(a,min(b,len(T1))):
            if (d=="LONG" and L1[j]<=lim) or (d=="SHORT" and H1[j]>=lim): fj=j; break
        if fj is not None and khour(T1[fj],off)>=8: base.append((fj,d,ktr,lim,bi))
    print(f"=== {tf} (리밋체결 {len(base)}, 기간 {YRS:.1f}년) ===")
    print(f"{'N':>5}{'순차':>7}{'승률':>8}{'누적R':>9}{'CAGR':>9}{'MDD':>8}")
    for N in NS:
        rs=[(fj,resolve(fj,lim,d,ktr,N)) for (fj,d,ktr,lim,bi) in base]
        rows=sorted([(fj,r["exj"],r["pnl"]/RNORM) for fj,r in rs])
        eq=[1.0]; cum=0.0; wins=0; busy=-1; nseq=0
        for fj,ej,R in rows:
            if fj<=busy: continue
            nseq+=1; cum+=R; eq.append(eq[-1]*(1+0.02*R)); busy=ej
            if R>0: wins+=1
        cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
        print(f"{N:>5}{nseq:>7}{100*wins/nseq if nseq else 0:>7.1f}%{cum:>+9.1f}{cagr:>+8.1f}%{maxdd(eq):>7.1f}%")
    # 최근 10 (N=1.0) — v3_recent.html 갱신용
    charts=[]
    for fj,d,ktr,lim,bi in base[-10:]:
        r=resolve(fj,lim,d,ktr,1.0)
        lo=max(0,bi-12); hi=min(len(bars),bi+170)
        btimes=[b[0] for b in bars]
        def tfk(epoch): return max(lo,min(hi-1,bisect.bisect_right(btimes,epoch)-1))-lo
        win=[{"o":round(bars[i][1],3),"h":round(bars[i][2],3),"l":round(bars[i][3],3),"c":round(bars[i][4],3),
              "b2u":round(u2[i],3) if u2[i] else None,"b2l":round(l2[i],3) if l2[i] else None} for i in range(lo,hi)]
        charts.append({"dir":d,"ktr":round(ktr,3),"brk_dt":kst(bars[bi][0]),"fill_dt":kst(T1[fj]),
                       "limit":round(lim,3),"E":[round(e,3) for e in r["E"]],"stopline":r["sl"],
                       "ex_dt":kst(T1[r["exj"]]),"ex_px":r["expx"],"pnl":round(r["pnl"],2),
                       "bk":bi-lo,"fk":tfk(T1[fj]),"ek":tfk(T1[r["exj"]]),
                       "gf":[{"k":k,"dt":kst(T1[j]),"px":round(px,3)} for k,j,px in r["gf"]],"bars":win})
    RECENT[tf]=charts
    print()

TMPL=open("../result/v3_recent.html",encoding="utf-8").read()
import re
new=re.sub(r'const D=\{.*\};let tf','const D='+json.dumps(RECENT,ensure_ascii=False)+';let tf',TMPL,count=1,flags=re.S)
new=re.sub(r'<title>.*?</title>','<title>v3 (c)이익권트레일 최근10 [1m]</title>',new,count=1)
open("../result/v3_recent.html","w",encoding="utf-8").write(new)
print("-> ../result/v3_recent.html 갱신 (c출구·1m·N=1.0)")
