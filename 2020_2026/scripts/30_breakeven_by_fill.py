# -*- coding: utf-8 -*-
"""30 — TP=1.5에서 '몇 차 체결되든 본전이상 가능한가' 체결차수별 손익(랏·KTR 단위) 표.
그리드 [0,1,2,3,4,4.5] / 1~5차 TP=깊은체결+1.5 / 6차: 반등탈출(바닥+1.0) or 풀스톱(-5).
손익(LONG) = Σ Li*(진입깊이i - 청산깊이).  >=0 이면 본전이상."""
import sys
MULT=[0,1,2,3,4,4.5]; TP=float(sys.argv[1]) if len(sys.argv)>1 else 1.5; B6X=1.0; STOPM=5.0

LADDERS={
 "등량 1·1·1·1·1·1":   [1,1,1,1,1,1],
 "후방 1·1·2·2·3·4":   [1,1,2,2,3,4],
 "강후방 1·1·2·3·5·8":  [1,1,2,3,5,8],
 "급후방 1·2·3·4·5·6":  [1,2,3,4,5,6],
 "전방 4·3·2·2·1·1":   [4,3,2,2,1,1],
}

def pnl_tps(L,k):
    exitlv=MULT[k-1]-TP
    return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6(L):
    exitlv=MULT[5]-B6X
    return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(L):
    return sum(L[i]*(MULT[i]-STOPM) for i in range(6))

hdr=f"{'사다리':<20}" + "".join(f"{'%d차'%k:>7}" for k in range(1,6)) + f"{'6차반등':>9}{'6차풀스톱':>10}"
print(hdr)
print("-"*len(hdr))
for name,L in LADDERS.items():
    row=f"{name:<20}"
    for k in range(1,6):
        v=pnl_tps(L,k); row+=f"{v:>+7.1f}"
    row+=f"{pnl_b6(L):>+9.1f}{pnl_stop(L):>+10.1f}"
    print(row)

print("\n[해석] 값 >=0 = 본전이상. 1~5차는 TP(깊은체결+1.5) 청산, 6차는 반등탈출 or 풀스톱.")
print("총투입랏(6차 완전체결 시):")
for name,L in LADDERS.items():
    print(f"  {name:<20} 총 {sum(L)}단위")
