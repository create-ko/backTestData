# -*- coding: utf-8 -*-
"""63 - v3를 1분봉 경로로 재해소 (look-ahead 버그 수정).
신호·밴드·KTR은 TF(5/10분)에서 산출 -> 진입(리밋)·그리드·트레일SL·청산은 전부 1분봉을 시간순으로 밟아 해소.
트레일 SL은 '직전 1분봉까지의 peak'로 정한 SL을 현재 1분봉 저가에 판정(같은봉 미래참조 제거), 체결봉 당일청산 금지.
N=1.0 M=1.0 slip 0.3 그리드 0/-1/-2KTR 랏1/2/3 base=KTR. 1R=10KTR-lot, 2% 복리.
data/에서 실행(1m CSV 큼, 로딩 수십초). 콘솔 ASCII만. 출력: ../result/v3_recent.html 갱신 + 콘솔 집계."""
import csv, math, time, bisect, json

N=1.0; M=1.0; SLIP=0.3; KSTEP=[0,1,2]; LOTS=[1,2,3]; M1SCAN=20000
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

print("1분봉 로딩...(수십초)")
T1=[]; O1=[]; H1=[]; L1=[]
with open("xauusd_1m_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
    rd=csv.reader(fp); next(rd)
    for r in rd:
        T1.append(int(float(r[0]))); O1.append(float(r[1])); H1.append(float(r[2])); L1.append(float(r[3]))
print(f"1m {len(T1)}봉")

def i1(epoch): return bisect.bisect_left(T1,epoch)

def resolve(j0, limit, d, ktr):
    """1m 인덱스 j0부터 그리드+트레일SL 해소. 반환 (exit_j, exit_px, pnl, gridfills[(k,j,px)], slfinal, maxk)."""
    LONG=(d=="LONG"); n=len(T1)
    E=[limit-KSTEP[k]*ktr if LONG else limit+KSTEP[k]*ktr for k in range(3)]
    filled=[True,False,False]; gf=[(0,j0,limit)]; maxk=0
    peak=limit   # 체결가로 시작(봉 고가 아님)
    end=min(n,j0+M1SCAN); slf=None
    for m in range(j0,end):
        h=H1[m]; l=L1[m]
        for k in range(1,3):
            if not filled[k] and ((LONG and l<=E[k]) or ((not LONG) and h>=E[k])):
                filled[k]=True; maxk=k; gf.append((k,m,E[k]))
        deepest=E[maxk]
        sl=max(deepest-M*ktr,peak-N*ktr) if LONG else min(deepest+M*ktr,peak+N*ktr)
        if m>j0 and ((LONG and l<=sl) or ((not LONG) and h>=sl)):
            ex=sl-SLIP if LONG else sl+SLIP
            pnl=sum(LOTS[k]*((ex-(E[k]+SLIP)) if LONG else ((E[k]-SLIP)-ex)) for k in range(maxk+1))/ktr
            return m,round(ex,3),round(pnl,2),gf,round(sl,3),maxk
        peak=max(peak,h) if LONG else min(peak,l)
    # 미청산
    c=L1[end-1] if not LONG else H1[end-1]
    return end-1,None,0.0,gf,None,maxk

def maxdd(eq):
    pk=eq[0]; m=0.0
    for v in eq:
        if v>pk: pk=v
        dd=(pk-v)/pk
        if dd>m: m=dd
    return 100*m

DATA={}
for tf in ["5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); tfsec=int(tf[:-1])*60
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
    trades=[]  # (fill_j, exit_j, R, dir, ktr, limit, bi, gf, exit_px, slf, maxk)
    for s in range(len(sig)):
        bi,d,ktr=sig[s]
        lim=l2[bi] if d=="LONG" else u2[bi]
        if lim is None: continue
        t_act=bars[bi][0]+tfsec   # 돌파봉 마감(=리밋 활성)
        t_nb=bars[sig[s+1][0]][0] if s+1<len(sig) else T1[-1]+1   # 다음 돌파 = 리밋 만료
        a=i1(t_act); b=i1(t_nb)
        fj=None
        for j in range(a,min(b,len(T1))):
            if (d=="LONG" and L1[j]<=lim) or (d=="SHORT" and H1[j]>=lim): fj=j; break
        if fj is None: continue
        ej,epx,pnl,gf,slf,maxk=resolve(fj,lim,d,ktr)
        trades.append((fj,ej,pnl/RNORM,d,ktr,lim,bi,gf,epx,slf,maxk))
    # 순차 복리
    trades.sort(); eq=[1.0]; cum=0.0; wins=0; busy=-1; nseq=0
    for fj,ej,R,*_ in trades:
        if fj<=busy: continue
        nseq+=1; cum+=R; eq.append(eq[-1]*(1+0.02*R)); busy=ej
        if R>0: wins+=1
    cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
    print(f"=== {tf} [1m해소] 체결 {len(trades)} -> 순차 {nseq} | 승률 {100*wins/nseq if nseq else 0:.1f}% | 누적R {cum:+.1f} | CAGR {cagr:+.1f}% | MDD {maxdd(eq):.1f}% ===")
    # 최근 10트레이드 차트용
    charts=[]
    for fj,ej,R,d,ktr,lim,bi,gf,epx,slf,maxk in trades[-10:]:
        lo=max(0,bi-12); hi=min(len(bars),bi+160)
        # 차트는 TF 캔들. 1m 체결/청산 시각을 포함하는 TF봉 인덱스로 매핑
        def tfk(epoch):
            j=bisect.bisect_right([b[0] for b in bars],epoch)-1
            return max(lo,min(hi-1,j))-lo
        win=[]
        for i in range(lo,hi):
            t,o,h,l,c=bars[i]
            win.append({"o":round(o,3),"h":round(h,3),"l":round(l,3),"c":round(c,3),
                        "b2u":round(u2[i],3) if u2[i] else None,"b2l":round(l2[i],3) if l2[i] else None})
        E=[round(lim-KSTEP[k]*ktr if d=="LONG" else lim+KSTEP[k]*ktr,3) for k in range(3)]
        charts.append({"dir":d,"ktr":round(ktr,3),"brk_dt":kst(bars[bi][0]),"fill_dt":kst(T1[fj]),
                       "limit":round(lim,3),"E":E,"stopline":slf,"ex_dt":kst(T1[ej]),"ex_px":epx,
                       "pnl":round(R*RNORM,2),"bk":bi-lo,"fk":tfk(T1[fj]),"ek":tfk(T1[ej]),
                       "gf":[{"k":k,"dt":kst(T1[j]),"px":round(px,3)} for k,j,px in gf],"bars":win})
    DATA[tf]=charts

# v3_recent.html 갱신(1m 해소판) — 58과 동일 뷰어, 데이터만 교체
TMPL=open("../result/v3_recent.html",encoding="utf-8").read()
import re
new=re.sub(r'const D=\{.*\};let tf', 'const D='+json.dumps(DATA,ensure_ascii=False)+';let tf', TMPL, count=1, flags=re.S)
new=new.replace("최근 10트레이드 (TradingView 대조)","최근 10트레이드 [1분봉 해소] (TradingView 대조)")
open("../result/v3_recent.html","w",encoding="utf-8").write(new)
print("-> ../result/v3_recent.html 갱신(1m 해소)")
