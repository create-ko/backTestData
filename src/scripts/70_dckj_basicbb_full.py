# -*- coding: utf-8 -*-
"""70 - 69(2026)의 전 기간(2010~2026)판. 방향=10m 20MA + 타점=기본더블비 + KTR그리드(물타기).
TP=10m 20MA 회귀, 풀스톱 -5*ATR10, 후방랏 1·1·2·2·3·4. 우위표(68 bias) 일치/반대 통제.
연도별 분해로 2014~2019(약세·횡보)에서 그리드 풀스톱 폭발/방향우위 유지 여부 확인.
data/에서 실행(전체 1m 로드, 수십초~수분). 콘솔 ASCII만(규칙3)."""
import csv, math, time, bisect

WARM_CUT=0   # 전 기간
SPREAD=0.30; RISK=0.02; START_H=8
TPx=1.5; SLx=1.5
W={"더":3,"지":3,"추":2,"캔":1,"이":1,"격":1,"깨":1}
ZK=3.0; DW_WIN=300; DW_BINK=0.25; TOL_K=0.4

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
def kyear(e): return time.strftime("%Y",time.gmtime(e+9*3600))
def khour(e): return ((e//3600)+9)%24   # KST (골드 신호 offset과 동일하게 +9 근사)

print("1분봉 로딩(전 기간)...")
T1=[];O1=[];H1=[];L1=[];C1=[]
with open("xauusd_1m_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
    rd=csv.reader(fp); next(rd)
    for r in rd:
        t=int(float(r[0])); t=t//1000 if t>1e11 else t
        if t<WARM_CUT: continue
        T1.append(t); O1.append(float(r[1])); H1.append(float(r[2])); L1.append(float(r[3])); C1.append(float(r[4]))
print(f"1m {len(T1)}봉 ({kyear(T1[0])}~)")

def resample(period):
    PT=[];PO=[];PH=[];PL=[];PC=[]; cur=None
    for i in range(len(T1)):
        b=(T1[i]//period)*period
        if b!=cur:
            cur=b; PT.append(b);PO.append(O1[i]);PH.append(H1[i]);PL.append(L1[i]);PC.append(C1[i])
        else:
            if H1[i]>PH[-1]:PH[-1]=H1[i]
            if L1[i]<PL[-1]:PL[-1]=L1[i]
            PC[-1]=C1[i]
    return PT,PO,PH,PL,PC

print("1H/4H/10m 리샘플 + bias 산출...")
HT,HO,HH,HL,HC=resample(3600); n=len(HT)
bbu,bbl=boll(HC,20,2.0); ma20=sma(HC,20); ma120=sma(HC,120)
atr=[None]*n; tr=[0.0]*n
for i in range(1,n): tr[i]=max(HH[i]-HL[i],abs(HH[i]-HC[i-1]),abs(HL[i]-HC[i-1]))
s=0.0
for i in range(1,n):
    s+=tr[i]
    if i>14: s-=tr[i-14]
    if i>=14: atr[i]=s/14
# 일 구조레벨
KOFF=9*3600
pdh=[None]*n;pdl=[None]*n;pdc=[None]*n;dopen=[None]*n;fhh=[None]*n;fhl=[None]*n
cur_day=None; ph=pl=pc=None; ch=cl=co=None
for i in range(n):
    d=(HT[i]+KOFF)//86400
    if d!=cur_day:
        if cur_day is not None: ph,pl,pc=ch,cl,HC[i-1]
        cur_day=d; ch=HH[i];cl=HL[i];co=HO[i]
    else:
        if HH[i]>ch:ch=HH[i]
        if HL[i]<cl:cl=HL[i]
    pdh[i]=ph;pdl[i]=pl;pdc[i]=pc;dopen[i]=co;fhh[i]=co and ch;fhl[i]=co and cl
# ZigZag
piv=[]; trend=1; cur_hi=HH[0];cur_hi_i=0;cur_lo=HL[0];cur_lo_i=0
for i in range(1,n):
    th=ZK*(atr[i] or (HH[i]-HL[i]) or 1.0)
    if trend>=0:
        if HH[i]>=cur_hi:cur_hi=HH[i];cur_hi_i=i
        if cur_hi-HL[i]>=th: piv.append((i,cur_hi_i,cur_hi,-1));trend=-1;cur_lo=HL[i];cur_lo_i=i;continue
    if trend<=0:
        if HL[i]<=cur_lo:cur_lo=HL[i];cur_lo_i=i
        if HH[i]-cur_lo>=th: piv.append((i,cur_lo_i,cur_lo,1));trend=1;cur_hi=HH[i];cur_hi_i=i
pconf=[p[0] for p in piv]
osc=[None]*n
for i in range(n):
    if ma20[i] and atr[i]: osc[i]=(HC[i]-ma20[i])/atr[i]
DW_REFRESH=24; dw_idx=[];dw_lv=[]
for i in range(0,n,DW_REFRESH):
    lo=max(0,i-DW_WIN); binw=DW_BINK*(atr[i] or 1.0); cnt={}
    for j in range(lo,i):
        a=int(HL[j]/binw);b=int(HH[j]/binw)
        for bb in range(a,b+1): cnt[bb]=cnt.get(bb,0)+1
    if cnt:
        mx=max(cnt.values()); lv=[(bb+0.5)*binw for bb,ct in cnt.items() if ct>=0.6*mx]
    else: lv=[]
    dw_idx.append(i);dw_lv.append(lv)
def dwell_levels(i):
    si=bisect.bisect_right(dw_idx,i)-1
    return dw_lv[si] if si>=0 else []
def divergence(i):
    hi=bisect.bisect_right(pconf,i); highs=[];lows=[]
    for t in range(hi-1,-1,-1):
        ci,pidx,pr,kind=piv[t]
        if kind==-1 and len(highs)<2 and osc[pidx] is not None: highs.append((pr,osc[pidx]))
        if kind==1 and len(lows)<2 and osc[pidx] is not None: lows.append((pr,osc[pidx]))
        if len(highs)>=2 and len(lows)>=2: break
    v=0
    if len(highs)==2 and highs[0][0]>highs[1][0] and highs[0][1]<highs[1][1]: v-=1
    if len(lows)==2 and lows[0][0]<lows[1][0] and lows[0][1]>lows[1][1]: v+=1
    return v
def zigzag_levels(i):
    hi=bisect.bisect_right(pconf,i); return [piv[t][2] for t in range(hi-1,max(-1,hi-7),-1)]
def last_swing(i):
    hi=bisect.bisect_right(pconf,i)
    if hi<2: return None
    return piv[hi-2][2],piv[hi-1][2],piv[hi-1][3]

bias=[0]*n; strg=[0]*n
for i in range(n):
    if i<120 or bbu[i] is None or ma120[i] is None or atr[i] is None: continue
    c=HC[i];up=bbu[i];lo=bbl[i];mean=(up+lo)/2;half=(up-lo)/2 or 1e-9; tol=TOL_K*atr[i]
    deo=W["더"] if c<=lo else (-W["더"] if c>=up else (1 if c<=mean-0.5*half else (-1 if c>=mean+0.5*half else 0)))
    o,h,l=HO[i],HH[i],HL[i];body=abs(c-o);rng=(h-l) or 1e-9;uw=h-max(o,c);lw=min(o,c)-l
    can=0 if body<=0.1*rng else (W["캔"] if (lw>=2*body and uw<=0.8*body) else (-W["캔"] if (uw>=2*body and lw<=0.8*body) else 0))
    ev=W["이"] if ma20[i]>ma120[i] else (-W["이"] if ma20[i]<ma120[i] else 0)
    sw=last_swing(i); chu=0
    if sw:
        pp,pl_,kind=sw; leg=abs(pl_-pp) or 1e-9
        if kind==-1:
            ret=(pl_-c)/leg; chu=W["추"] if (c<pl_ and ret<=0.5) else (1 if ret<=0.66 else 0)
        else:
            ret=(c-pl_)/leg; chu=-W["추"] if (c>pl_ and ret<=0.5) else (-1 if ret<=0.66 else 0)
    levels=[x for x in [pdh[i],pdl[i],pdc[i],dopen[i],fhh[i],fhl[i]] if x]+zigzag_levels(i)+dwell_levels(i)
    sup=res=False
    for lv in levels:
        if abs(c-lv)<=tol:
            if c>=lv: sup=True
            else: res=True
    ji=W["지"] if (sup and not res) else (-W["지"] if (res and not sup) else 0)
    dv=divergence(i)
    if dv==0 and osc[i] is not None: dv=1 if osc[i]<=-2 else (-1 if osc[i]>=2 else 0)
    gk=W["격"]*(1 if dv>0 else (-1 if dv<0 else 0))
    shc=[pdh[i]];slc=[pdl[i]]
    if sw:
        if sw[2]==-1: shc.append(sw[1])
        else: slc.append(sw[1])
    sh=max([x for x in shc if x],default=None);sl=min([x for x in slc if x],default=None)
    kk=W["깨"] if (sh and c>sh) else (-W["깨"] if (sl and c<sl) else 0)
    net=deo+can+ev+chu+ji+gk+kk
    bias[i]=1 if net>0 else (-1 if net<0 else 0); strg[i]=abs(net)
hclose=[t+3600 for t in HT]
def bias_at(epoch):
    k=bisect.bisect_right(hclose,epoch)-1
    return (bias[k],strg[k]) if k>=0 else (0,0)

# ---- 10분봉 기본더블비 타점 (방향=10m 20이평 기울기) ----
print("10m 기본더블비 타점 산출(2026)...")
MT,MO,MH,ML,MC=resample(600); m=len(MT)
b2u,b2l=boll(MO,4,4.0)            # 4/4 시가 밴드
mma20=sma(MC,20)                  # 10m 20이평(종가) = 방향 + TP타깃
matr=[None]*m; mtr=[0.0]*m
for i in range(1,m): mtr[i]=max(MH[i]-ML[i],abs(MH[i]-MC[i-1]),abs(ML[i]-MC[i-1]))
ss=0.0
for i in range(1,m):
    ss+=mtr[i]
    if i>14: ss-=mtr[i-14]
    if i>=14: matr[i]=ss/14
mclose=[t+600 for t in MT]
def i1(e): return bisect.bisect_left(T1,e)
# 그리드 설정 (base=10m ATR14): 0/-1/-2/-3/-4/-4.5, 후방랏 1·1·2·2·3·4, 풀스톱 -5, TP=20MA 회귀
GMULT=[0,1,2,3,4,4.5]; GL=[1,1,2,2,3,4]; GSTOP=5.0; GCAP=40000
STOP_R=abs(sum(GL[i]*(GMULT[i]-GSTOP) for i in range(6)))
def resolve_grid(ee,e,d,base):
    """1분봉 그리드 해소. 그리드 물타기 + TP=10m 20MA 회귀 + 풀스톱 -5*base. net R(STOP_R단위) 반환."""
    j0=i1(ee)
    if d==1: E=[e-base*M for M in GMULT]; stop=e-GSTOP*base
    else:    E=[e+base*M for M in GMULT]; stop=e+GSTOP*base
    filled=[True,False,False,False,False,False]; maxk=0
    for j in range(j0,min(len(T1),j0+GCAP)):
        t=T1[j];h=H1[j];l=L1[j]
        for k in range(1,6):
            if not filled[k] and ((d==1 and l<=E[k]) or (d==-1 and h>=E[k])): filled[k]=True; maxk=max(maxk,k)
        fc=sum(filled)
        mk=bisect.bisect_right(mclose,t)-1
        ma=mma20[mk] if (mk>=0 and mma20[mk] is not None) else None
        # 풀스톱(6차)
        if fc>=6 and ((d==1 and l<=stop) or (d==-1 and h>=stop)):
            ex=stop
            gross=sum(GL[k]*((ex-E[k]) if d==1 else (E[k]-ex)) for k in range(maxk+1))/base
            cost=sum(GL[:maxk+1])*(SPREAD/base)
            return t,(gross-cost)/STOP_R
        # TP = 20MA 회귀(전 포지션 일괄)
        if ma and ((d==1 and h>=ma) or (d==-1 and l<=ma)):
            ex=ma
            gross=sum(GL[k]*((ex-E[k]) if d==1 else (E[k]-ex)) for k in range(maxk+1))/base
            cost=sum(GL[:maxk+1])*(SPREAD/base)
            return t,(gross-cost)/STOP_R
    # 타임아웃: 마지막가 정리
    ex=C1[min(len(T1)-1,j0+GCAP-1)]
    gross=sum(GL[k]*((ex-E[k]) if d==1 else (E[k]-ex)) for k in range(maxk+1))/base
    return T1[min(len(T1)-1,j0+GCAP-1)],(gross-sum(GL[:maxk+1])*(SPREAD/base))/STOP_R
# 후보 타점: 2026, 10m 20MA 방향으로 4/4 터치
cand=[]   # (entry_epoch, e, dir, base, bias, strg)
for i in range(m):
    if matr[i] is None or b2l[i] is None or i<23 or mma20[i] is None or mma20[i-3] is None: continue
    if khour(MT[i])<START_H: continue
    slope=mma20[i]-mma20[i-3]; ee=MT[i]+600; e=MC[i]; bdir,bs=bias_at(MT[i])
    if slope>0 and ML[i]<=b2l[i] and mma20[i]>e:        # 상승추세 + 하단 눌림 = 매수
        cand.append((ee,e,1,matr[i],bdir,bs))
    elif slope<0 and MH[i]>=b2u[i] and mma20[i]<e:      # 하락추세 + 상단 되오름 = 매도
        cand.append((ee,e,-1,matr[i],bdir,bs))
YEARS=sorted({kyear(c[0]) for c in cand})
span=(T1[-1]-T1[0])/(365.25*86400)
print(f"기본더블비 후보(전 기간, 10m 20MA 방향+4/4터치, KST08~): {len(cand)}건 [{span:.1f}년]\n")

def run(filt):
    eq=[1.0];cum=0.0;wins=0;busy=-1;nn=0; byY={}
    for ee,e,d,base,bdir,bs in cand:
        if not filt(d,bdir,bs): continue
        if ee<=busy: continue
        r=resolve_grid(ee,e,d,base)
        if r is None: continue
        exep,R=r; cum+=R; eq.append(eq[-1]*(1+RISK*R)); busy=exep; nn+=1; wins+=(R>0)
        a=byY.setdefault(kyear(ee),[0.0,0]); a[0]+=R; a[1]+=1
    def mdd(E):
        pk=E[0];mx=0.0
        for v in E:
            if v>pk:pk=v
            if (pk-v)/pk>mx:mx=(pk-v)/pk
        return 100*mx
    cagr=100*((eq[-1]**(1/span))-1) if eq[-1]>0 else -100
    return {"n":nn,"wr":(100*wins/nn if nn else 0),"cum":cum,"ret":100*(eq[-1]-1),"cagr":cagr,"mdd":mdd(eq),"byY":byY}

print(f"# 10m 기본더블비 + KTR그리드(base=ATR10) | TP=20MA / 그리드0~-4.5 랏1·1·2·2·3·4 / 풀스톱-5 | 2010~2026 | 비용${SPREAD}/2%/KST08~24\n")
print(f"{'필터':>18}{'진입':>7}{'승률':>7}{'누적R':>8}{'CAGR':>8}{'MDD':>7}")
defs=[("순수 기본더블비",lambda d,b,s:True),
      ("+우위표 일치",lambda d,b,s:d==b),
      ("+우위표 반대(통제)",lambda d,b,s:d==-b),
      ("+우위표 일치 s>=3",lambda d,b,s:d==b and s>=3),
      ("+우위표 일치 s>=5",lambda d,b,s:d==b and s>=5)]
R={}
for lab,f in defs:
    r=run(f); R[lab]=r
    print(f"{lab:>18}{r['n']:>7}{r['wr']:>6.1f}%{r['cum']:>+8.1f}{r['cagr']:>+7.1f}%{r['mdd']:>6.1f}%")
# 연도별 net R (순수 / 일치 / 반대)
print(f"\n-- 연도별 net R (순수 / 일치 / 반대, 괄호=건수) --")
for y in YEARS:
    p=R["순수 기본더블비"]["byY"].get(y,[0,0]); g=R["+우위표 일치"]["byY"].get(y,[0,0]); a=R["+우위표 반대(통제)"]["byY"].get(y,[0,0])
    print(f"  {y}: 순수 {p[0]:+6.1f}({p[1]:>3})  일치 {g[0]:+6.1f}({g[1]:>3})  반대 {a[0]:+6.1f}({a[1]:>3})")
