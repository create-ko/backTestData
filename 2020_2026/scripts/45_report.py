# -*- coding: utf-8 -*-
"""45 — 종합 보고서 생성(report.html). 지금까지 모든 분석 통합. 데이터는 확정 결과 하드코딩."""
import json

# 최종 성과 (순차+시간 08~24, 비용$0.30 라운드턴, 리스크2%) [39]
PERF={
 "2m": {"v1":{"n":11907,"R":-141.2,"cagr":-37.0,"mdd":96.7,"win":92.1},
        "v2":{"n":9118,"R":-49.6,"cagr":-15.7,"mdd":83.1,"win":92.7}},
 "5m": {"v1":{"n":5759,"R":31.2,"cagr":9.1,"mdd":38.7,"win":93.2},
        "v2":{"n":4070,"R":43.3,"cagr":13.7,"mdd":11.8,"win":93.5}},
 "10m":{"v1":{"n":3434,"R":57.1,"cagr":18.7,"mdd":14.9,"win":93.5},
        "v2":{"n":2439,"R":34.0,"cagr":10.7,"mdd":9.5,"win":93.5}},
}
YEARS=["2020","2021","2022","2023","2024","2025","2026"]
RET={ # 연 수익% [39]
 "2m":{"v1":[-26.9,-37.3,-51.0,-60.4,-56.1,12.0,16.2],"v2":[4.2,-23.8,-30.4,-53.1,-19.6,27.2,25.3]},
 "5m":{"v1":[27.8,12.7,-12.0,-8.8,-0.7,30.5,16.9],"v2":[15.3,17.5,8.3,5.2,18.8,24.1,0.5]},
 "10m":{"v1":[13.3,25.7,-3.6,23.4,29.7,28.5,7.5],"v2":[17.3,6.1,6.3,18.1,11.7,-1.2,11.9]},
}
CNT={
 "2m":{"v1":[1541,1985,1945,1689,2110,1929,708],"v2":[1225,1527,1497,1300,1590,1448,531]},
 "5m":{"v1":[769,1050,956,881,978,834,291],"v2":[588,742,730,376,733,670,231]},
 "10m":{"v1":[433,596,552,565,619,490,179],"v2":[310,409,374,402,435,378,131]},
}
BE={"2m":[0.15,0.20],"5m":[0.34,0.37],"10m":[0.50,0.54]}  # 손익분기$ [v1,v2]
HOLD={ # 보유 중앙h/평균h/95%h/최대일 [42]
 "2m":{"v1":[0.4,1.3,3.5,43.7],"v2":[0.4,1.5,4.1,25.9]},
 "5m":{"v1":[0.6,2.6,7.3,43.7],"v2":[0.7,3.6,8.9,151.2]},
 "10m":{"v1":[0.8,4.5,15.3,43.7],"v2":[1.2,4.6,14.0,45.6]},
}
DATA={"PERF":PERF,"YEARS":YEARS,"RET":RET,"CNT":CNT,"BE":BE,"HOLD":HOLD}

HTML="""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>
<title>XAUUSD 돌파+그리드 전략 종합 보고서</title>
<style>
*{box-sizing:border-box}
body{font-family:'Malgun Gothic','Segoe UI',sans-serif;background:#0f1320;color:#dfe6f0;margin:0;line-height:1.5}
.wrap{max-width:1040px;margin:0 auto;padding:24px}
h1{color:#4fc3f7;font-size:1.6em;margin:0 0 2px;text-align:center}
.date{text-align:center;color:#7e8aa0;font-size:.8em;margin-bottom:8px}
h2{color:#7fd4ff;font-size:1.18em;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid #25324d}
h3{color:#a9c4e0;font-size:1em;margin:18px 0 6px}
p,li{font-size:.88em;color:#c4cfde}
.lead{background:#15203a;border:1px solid #2a3e63;border-radius:10px;padding:16px 18px;margin:14px 0}
.lead b{color:#fff}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.kpi{flex:1;min-width:120px;background:#15203a;border:1px solid #28395c;border-radius:9px;padding:12px;text-align:center}
.kpi .v{font-size:1.35em;font-weight:bold;color:#fff}.kpi .l{font-size:.72em;color:#8aa;margin-top:3px}
table{width:100%;border-collapse:collapse;font-size:.82em;margin:8px 0 4px}
th,td{padding:6px 9px;text-align:right;border-bottom:1px solid #243150}
th{color:#9cc4e8;background:#16203a;position:sticky}
td:first-child,th:first-child{text-align:left}
.pos{color:#5fd97e}.neg{color:#ff6f6f}.warn{color:#ffcf5c}.mut{color:#7e8aa0}
.best{background:#16331f}.bad{background:#331616}
.tag{display:inline-block;padding:2px 8px;border-radius:5px;font-size:.72em;font-weight:bold;margin-left:6px}
.tag.go{background:#1d5e33;color:#bdf5cf}.tag.no{background:#5e1d1d;color:#f5bdbd}.tag.mid{background:#5e511d;color:#f5e7bd}
.ctl{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.btn{padding:6px 13px;border:1px solid #345;background:transparent;color:#9cf;border-radius:6px;cursor:pointer;font-size:.8em}
.btn.on{background:#4fc3f7;color:#0f1320;font-weight:bold}
canvas{background:#121a2e;border-radius:8px;width:100%;margin-top:8px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:720px){.two{grid-template-columns:1fr}}
ul{margin:6px 0;padding-left:20px}
.note{font-size:.78em;color:#8493a8;font-style:italic}
code{background:#1a2540;padding:1px 5px;border-radius:4px;color:#bcd3f0;font-size:.92em}
</style></head><body><div class=wrap>

<h1>XAUUSD 돌파 + 그리드 전략 종합 보고서</h1>
<div class=date>【1차 완료 · 골드 단독】 데이터: Dukascopy MID 2020-01-01 ~ 2026-06-16 (6.5년) · 2m/5m/10m · 비용 $0.30 라운드턴 가정 · 리스크 2%/트레이드</div>

<div class=lead>
<b>핵심 결론.</b> BB 돌파 진입 + KTR 그리드(물타기) + 1.5KTR 익절 전략을 6.5년 전수 검증.
실거래 룰(한 번에 1개 그리드 · 08~24시 진입 · 체결비용 반영)을 적용하면
<b>10분봉이 유일하게 견고</b>하며, <b>전략1(v1·즉시진입)이 CAGR +18.7% / MDD 14.9%로 최고</b>.
2분봉은 비용으로 사망, 5분봉은 비용 여유가 적음. 꼬리필터는 불필요(유해), 리스크는 2~3% 권장.
</div>

<div class=kpis>
 <div class=kpi><div class="v pos">+18.7%</div><div class=l>10m v1 연복리(net)</div></div>
 <div class=kpi><div class="v">14.9%</div><div class=l>최대 낙폭(MDD)</div></div>
 <div class=kpi><div class="v">93.5%</div><div class=l>승률</div></div>
 <div class=kpi><div class="v">1.26</div><div class=l>MAR(수익/낙폭)</div></div>
 <div class=kpi><div class="v">~1.7</div><div class=l>거래/일</div></div>
</div>

<h2>1. 확정 전략 규칙</h2>
<table>
<tr><th>항목</th><th>규칙</th><th>근거</th></tr>
<tr><td>신호</td><td>BB1(종가 SMA20±2σ) 돌파 + BB2(시가 SMA4±4σ)</td><td>모표준편차(÷N)</td></tr>
<tr><td>진입 — 전략1(v1)</td><td>돌파 다음 봉 시가 즉시 진입</td><td class=mut>실거래 룰서 v1 우위</td></tr>
<tr><td>진입 — 전략2(v2)</td><td>돌파 후 BB2 반대밴드 터치 풀백 시 진입</td><td class=mut>MDD 낮은 보수형</td></tr>
<tr><td>그리드</td><td>돌파가 기준 0 / −1 / −2 / −3 / −4 / −4.5 ×KTR</td><td>6차 풀그리드 최적</td></tr>
<tr><td>랏(후방)</td><td><b>1 · 1 · 2 · 2 · 3 · 4</b> (총 13단위)</td><td>생존·증거금</td></tr>
<tr><td>익절(TP)</td><td>가장 깊은 체결 + <b>1.5 ×KTR</b> (전 포지션 일괄)</td><td>1.5가 효율 정점</td></tr>
<tr><td>6차 처리</td><td>바닥 +1.0KTR 반등 시 탈출, 아니면 −5KTR 풀스톱</td><td>손실 축소</td></tr>
<tr><td>리스크</td><td>풀스톱 = 자본의 <b>2~3%</b></td><td>10%는 낙폭 붕괴</td></tr>
<tr><td>운용</td><td>한 번에 그리드 1개(순차) · KST <b>08:00~24:00 진입</b></td><td>겹침제거·새벽컷</td></tr>
<tr><td>꼬리필터</td><td><b>미적용</b> (모든 돌파 진입)</td><td>필터가 수익 훼손</td></tr>
<tr><td>전제</td><td>브로커 라운드턴 비용 <b>$0.40 이하</b></td><td>10m 손익분기 $0.54</td></tr>
</table>

<h2>2. 분봉별 최종 성과 <span class=note>(순차+시간필터·비용$0.30·리스크2%)</span></h2>
<table id=perf></table>
<p class=note>net R = 누적 R(풀스톱=−1R 정규화). 복리%는 순차라 실현 가능. 2m는 비용으로 적자, 5m v1은 MDD 과다.</p>

<h2>3. 연도별 수익률</h2>
<div class=ctl id=tfsel></div>
<div class=ctl id=versel></div>
<canvas id=cv width=980 height=300></canvas>
<table id=yt></table>

<h2>4. 파라미터 근거 (왜 이 값인가)</h2>
<div class=two>
<div>
<h3>익절 TP: 1.5KTR</h3>
<table><tr><th>TP</th><th>10m v2 기대</th><th>MDD</th></tr>
<tr class=best><td>1.5</td><td class=pos>최적</td><td>최저</td></tr>
<tr><td>1.8</td><td class=warn>2025 함정</td><td>↑(붕괴)</td></tr>
<tr><td>2.0</td><td>동률</td><td>↑↑</td></tr></table>
<p class=note>1.8은 추세장(2025)에서 엣지 0·MDD 28%·파산50%의 비단조 함정.</p>
</div>
<div>
<h3>랏 사다리: 후방 1·1·2·2·3·4</h3>
<table><tr><th>차수 청산</th><th>후방</th><th>강후방 1·1·2·3·5·8</th></tr>
<tr><td>1차</td><td class=pos>+1.5</td><td class=pos>+1.5</td></tr>
<tr><td>3차</td><td class=pos>+3.0</td><td class=pos>+3.0</td></tr>
<tr><td>5차</td><td class=pos>+0.5</td><td class=pos>+4.0</td></tr>
<tr><td>6차 반등</td><td class=neg>−4.5</td><td>0.0(본전)</td></tr>
<tr><td>6차 풀스톱</td><td class=neg>−24</td><td class=neg>−30</td></tr></table>
<p class=note>후방=생존·증거금(13단위), 강후방=평년효율(20단위)이나 추세장 꼬리위험·증거금 큼. 전방가중은 전 지표 열등(금지).</p>
</div>
</div>
<div class=two>
<div>
<h3>최대 체결: 6차</h3>
<table><tr><th>cap</th><th>10m v2 기대R</th><th>MDD</th></tr>
<tr><td>3차</td><td>+0.049</td><td class=neg>21.3%</td></tr>
<tr><td>4차</td><td>+0.041</td><td>15.1%</td></tr>
<tr class=best><td>6차</td><td>+0.029</td><td class=pos>8.7%</td></tr></table>
<p class=note>얕게 끊으면 트레이드당 R↑이나 손절 잦아 MDD 폭발. 깊을수록 위험조정 우위.</p>
</div>
<div>
<h3>꼬리필터: 미적용</h3>
<table><tr><th>필터</th><th>10m v1 CAGR</th></tr>
<tr class=best><td>없음</td><td class=pos>+18.7%</td></tr>
<tr><td>≤0.3</td><td>+16.3%</td></tr>
<tr><td>≤0.2</td><td>+10.1%</td></tr>
<tr><td>≤0.1</td><td>+8.2%</td></tr></table>
<p class=note>per-signal 반등률은 저꼬리가 좋아 보이나, 전략 전체론 거래량 손실로 수익 훼손. 그리드가 약한 돌파를 이미 구제.</p>
</div>
</div>

<h2>5. 비용·리스크 민감도</h2>
<div class=two>
<div>
<h3>손익분기 스프레드(라운드턴$)</h3>
<table><tr><th>TF</th><th>v1</th><th>v2</th><th>판정</th></tr>
<tr class=bad><td>2m</td><td>$0.15</td><td>$0.20</td><td class=neg>불가</td></tr>
<tr><td>5m</td><td>$0.34</td><td>$0.37</td><td class=warn>ECN만</td></tr>
<tr class=best><td>10m</td><td>$0.50</td><td>$0.54</td><td class=pos>견고</td></tr></table>
<p class=note>실비용이 손익분기보다 비싸면 적자. 10m만 리테일 비용대($0.3~0.4) 흡수.</p>
</div>
<div>
<h3>리스크%별 (10m v2)</h3>
<table><tr><th>리스크</th><th>MDD</th><th>≥50%낙폭 확률</th></tr>
<tr class=best><td>2%</td><td class=pos>14.8%</td><td>0%</td></tr>
<tr><td>5%</td><td class=warn>34.8%</td><td>8.3%</td></tr>
<tr class=bad><td>10%</td><td class=neg>61.1%</td><td class=neg>90.3%</td></tr></table>
<p class=note>리스크%는 '풀그리드 손절 = 자본 몇%'. 10%면 연속손절 복리로 90%가 −50%↑ 낙폭. 2~3% 권장.</p>
</div>
</div>

<h2>6. 운용 가이드</h2>
<ul>
<li><b>거래 시간(KST 08~24)</b>: v1은 엣지가 하루 종일 분포(아시아44%/런던34%/미장초22%) → 시간 선택 자유. v2는 런던·저녁(16~24) 집중(74%). 새벽 00~08시는 저질이라 제외(수익 오히려 개선).</li>
<li><b>저녁만 가능 시(직장인)</b>: 18~24시 6시간만 거래해도 v1 엣지의 ~52% 확보(CAGR ~9~10%·MDD↓). 매 거래 다 잡을 필요 없음 — 일부만 잡으면 수익은 비례축소·낙폭도 감소.</li>
<li><b>빈도</b>: 시장일의 ~72%가 ≥1건, ~28%는 무거래(정상). 평균 ~1.7건/일.</li>
<li><b>필요 자본</b>: 수익률은 자본크기 무관(%기반). 하한은 랏 최소단위 — 변동성 큰 시기까지 ~$1만~1.5만. 순차라 동시보유 1개 → 증거금 부담 작음. 큰 자본은 절대수익액만 키움.</li>
<li><b>보유시간</b>: 95%가 15시간 내 청산(대부분 당일). 자본 묶임 적음.</li>
</ul>
<table id=holdt></table>

<h2>7. 주의 · 미해결</h2>
<ul>
<li class=warn><b>정체(stuck) 그리드</b>: 드물게 그리드가 횡보장에 갇혀 수주~수개월 열림(최대 26~151일). 자본 묶임 + 순차라 그동안 신규진입 0. <b>최대 보유시간 손절(time-stop) 도입 검토 필요.</b> (데이터 공백 아님 — 갭 최대 3.2일 정상휴장 확인됨)</li>
<li class=mut><b>필터 검증완료 (전부 무용)</b>: 꼬리필터·2h추세필터·골든/데드크로스 모두 테스트 → net R 오히려 감소. 돌파는 반전 이벤트라 MA추세가 후행하고, 그리드가 역추세 진입을 되돌림으로 구제하기 때문. <b>이 전략엔 진입 필터를 더하지 말 것.</b></li>
<li class=warn><b>약한 해 (미해결)</b>: 추세장에서 엣지 얇아짐(10m v1은 2022 −3.6%가 유일 적자해, v2는 2025 −1.2%). 필터로는 방어 안 됨 — 시간 손절/다른 접근 필요.</li>
<li class=mut><b>비용 가정</b>: $0.30 라운드턴은 낙관적일 수 있음. 실제 브로커 비용 확인 필수($0.40 초과 시 10m도 위태).</li>
<li class=mut><b>복리% 신뢰</b>: 순차 룰이라 겹침 없음 → %는 실현 가능. 단 2m/5m은 비용·MDD 문제로 비추천.</li>
</ul>

<h2>요약 한 장</h2>
<div class=lead>
<b>10분봉 · 전략1(v1, 즉시진입) · 후방 1·1·2·2·3·4 · TP 1.5KTR · 6차 · 반등탈출 · 리스크 2~3% · 08~24시 진입 · 1개씩 순차 · 비용 $0.40↓ 브로커 · 꼬리필터 없음.</b><br>
→ 6.5년 net +57R, 연복리 +18.7%, MDD 14.9%, 승률 93.5%, 2022 빼고 전년 흑자.<br>
보수형 원하면 v2(+10.7%·MDD 9.5%). 필터(꼬리·추세·크로스)는 검증 결과 불필요. 남은 후보: 시간 손절(정체 그리드 방어). <b>2차</b>: FX 3쌍 + 골드 2010~19로 아웃오브샘플 검증.
</div>

<div class=note style="margin-top:30px;text-align:center">생성: 분봉별 전수 백테스트 / 본 보고서는 과거 데이터 기반이며 미래 수익을 보장하지 않습니다.</div>

<script>
const D=__DATA__;
let tf='10m',ver='v1';
// 성과표
(function(){let h='<tr><th>분봉·전략</th><th>진입수</th><th>net R</th><th>연복리</th><th>MDD</th><th>승률</th><th>판정</th></tr>';
 const order=[['10m','v1'],['10m','v2'],['5m','v2'],['5m','v1'],['2m','v2'],['2m','v1']];
 order.forEach(([t,v])=>{const p=D.PERF[t][v];const ok=p.cagr>12&&p.mdd<20;const mid=p.cagr>0&&p.mdd<25;
  const tag=ok?'<span class="tag go">견고</span>':(p.cagr>0?'<span class="tag mid">주의</span>':'<span class="tag no">부적합</span>');
  const cls=ok?'best':(p.cagr<0?'bad':'');
  h+=`<tr class=${cls}><td>${t} ${v}</td><td>${p.n.toLocaleString()}</td><td class=${p.R>=0?'pos':'neg'}>${p.R>=0?'+':''}${p.R}</td><td class=${p.cagr>=0?'pos':'neg'}>${p.cagr>=0?'+':''}${p.cagr}%</td><td>${p.mdd}%</td><td>${p.win}%</td><td>${tag}</td></tr>`;});
 document.getElementById('perf').innerHTML=h;})();
// 보유표
(function(){let h='<tr><th>분봉·전략</th><th>보유 중앙</th><th>평균</th><th>95%</th><th>최대(정체)</th></tr>';
 [['10m','v1'],['10m','v2'],['5m','v1'],['5m','v2'],['2m','v1'],['2m','v2']].forEach(([t,v])=>{const x=D.HOLD[t][v];
  h+=`<tr><td>${t} ${v}</td><td>${x[0]}h</td><td>${x[1]}h</td><td>${x[2]}h</td><td class=warn>${x[3]}일</td></tr>`;});
 document.getElementById('holdt').innerHTML=h;})();
// 연도별
function mkbtn(host,opts,cur,cb){const h=document.getElementById(host);h.innerHTML='';opts.forEach(o=>{const b=document.createElement('button');b.className='btn'+(o[0]===cur()?' on':'');b.textContent=o[1];b.onclick=()=>{cb(o[0]);ry()};h.appendChild(b)})}
function ry(){
 mkbtn('tfsel',[['2m','2분'],['5m','5분'],['10m','10분']],()=>tf,v=>tf=v);
 mkbtn('versel',[['v1','전략1 v1(즉시)'],['v2','전략2 v2(풀백)']],()=>ver,v=>ver=v);
 const ret=D.RET[tf][ver],cnt=D.CNT[tf][ver];
 // chart
 const cv=document.getElementById('cv'),x=cv.getContext('2d'),W=cv.width,H=cv.height,pad=40;
 x.clearRect(0,0,W,H);
 const mx=Math.max(...ret,5),mn=Math.min(...ret,-5);
 const bw=(W-pad-20)/ret.length;
 const Y=v=>H-30-(H-50)*((v-mn)/(mx-mn));
 x.strokeStyle='#3a5';x.beginPath();x.moveTo(pad,Y(0));x.lineTo(W-10,Y(0));x.stroke();
 ret.forEach((v,i)=>{const xx=pad+bw*i+6,bh=Y(0)-Y(v);
  x.fillStyle=v>=0?'#3fae5e':'#d65151';
  x.fillRect(xx,Math.min(Y(0),Y(v)),bw-12,Math.abs(bh));
  x.fillStyle='#cdd8e8';x.font='11px sans-serif';x.fillText((v>=0?'+':'')+v+'%',xx,Y(v)+(v>=0?-4:13));
  x.fillStyle='#8493a8';x.fillText(D.YEARS[i],xx,H-10);});
 // table
 let tot=cnt.reduce((a,b)=>a+b,0);
 let h='<tr><th>연도</th><th>건수</th><th>수익%</th></tr>';
 D.YEARS.forEach((y,i)=>{h+=`<tr><td>${y}</td><td>${cnt[i]}</td><td class=${ret[i]>=0?'pos':'neg'}>${ret[i]>=0?'+':''}${ret[i]}%</td></tr>`;});
 h+=`<tr><td><b>합계</b></td><td><b>${tot.toLocaleString()}</b></td><td class=${D.PERF[tf][ver].cagr>=0?'pos':'neg'}><b>CAGR ${D.PERF[tf][ver].cagr>=0?'+':''}${D.PERF[tf][ver].cagr}%</b></td></tr>`;
 document.getElementById('yt').innerHTML=h;
}
ry();
</script>
</div></body></html>"""
with open("report.html","w",encoding="utf-8") as f:
    f.write(HTML.replace("__DATA__",json.dumps(DATA,ensure_ascii=False)))
print("→ report.html 생성 완료")
