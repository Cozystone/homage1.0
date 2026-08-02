# -*- coding: utf-8 -*-
"""ATANOR pitch deck (2026.07) — 16:9 dark slides, one message per slide.

 v2 DNA: ( )··· .
Apple × Palantir — , , .
"""
import os
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as _canvas

ASSETS=r"C:\0.ASKIM ALL-VIN\ATANOR-live-selfhood-scheduler"
OUTDIR=r"C:\0.ASKIM ALL-VIN\27., ATANOR DEMO"
LOGO=os.path.join(ASSETS,"assets","atanor_logo.png")
pdfmetrics.registerFont(TTFont("M",r"C:\Windows\Fonts\malgun.ttf"))
pdfmetrics.registerFont(TTFont("MB",r"C:\Windows\Fonts\malgunbd.ttf"))

W,H=338.667*mm,190.5*mm          # 16:9
BG=colors.HexColor("#0a0a0a"); WHITE=colors.white
DIM=colors.HexColor("#cfcfcf"); GREY=colors.HexColor("#8a8a8a"); FAINT=colors.HexColor("#5a5a5a")
LINE=colors.HexColor("#383838"); ACCENT=colors.HexColor("#e8e8e8")
MX=22*mm                          # side margin

out=os.path.join(OUTDIR,"ATANOR_피치덱_v2.pdf")
c=_canvas.Canvas(out,pagesize=(W,H))
c.setTitle("ATANOR 피치덱 2026.07"); c.setAuthor("김안석")
_page=[0]

def bg():
    c.setFillColor(BG); c.rect(0,0,W,H,fill=1,stroke=0)

def chrome(num_label):
    """top-left logo, top-right section number, bottom hairline + page"""
    if os.path.exists(LOGO):
        img=ImageReader(LOGO); iw,ih=img.getSize(); th=6.5*mm; tw=th*(iw/ih)
        c.drawImage(img,MX,H-14*mm,width=tw,height=th,mask='auto')
    c.setFont("MB",11); c.setFillColor(FAINT); c.drawRightString(W-MX,H-12.5*mm,num_label)
    c.setStrokeColor(LINE); c.setLineWidth(0.5); c.line(MX,12*mm,W-MX,12*mm)
    c.setFont("M",8.5); c.setFillColor(FAINT)
    c.drawRightString(W-MX,7.5*mm,"%02d"%_page[0])
    c.drawString(MX,7.5*mm,"ATANOR · 2026.07 · 수치는 자체 실측 (재현 스크립트 부록)")

def newpage():
    c.showPage(); _page[0]+=1

def title_sl():
    _page[0]+=1; bg()
    cx=W/2
    if os.path.exists(LOGO):
        img=ImageReader(LOGO); iw,ih=img.getSize(); tw=92*mm; th=tw*(ih/iw)
        c.drawImage(img,cx-tw/2,H/2+2*mm,width=tw,height=th,mask='auto')
    c.setFont("M",14); c.setFillColor(DIM)
    c.drawCentredString(cx,H/2-10*mm,"그래프 네이티브 로컬 AI — 프로그램 · 브라우저 · OS")
    c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(cx-28*mm,H/2-17*mm,cx+28*mm,H/2-17*mm)
    c.setFont("MB",13.5); c.setFillColor(WHITE)
    c.drawCentredString(cx,H/2-27*mm,"“환각하지 않고, GPU 없이, 출처를 증명하며 답하는 AI”")
    c.setFont("M",10); c.setFillColor(GREY)
    c.drawCentredString(cx,24*mm,"피치덱 · 2026.07 — 대표 김안석 · 넥스트챌린지스쿨")
    newpage()

def head(kicker,big,sub=None,y=None):
    """slide headline block"""
    y = y if y is not None else H-34*mm
    c.setFont("MB",12); c.setFillColor(GREY); c.drawString(MX,y+9*mm,kicker)
    c.setFont("MB",26); c.setFillColor(WHITE); c.drawString(MX,y-1*mm,big)
    if sub:
        c.setFont("M",12.5); c.setFillColor(DIM); c.drawString(MX,y-9.5*mm,sub)

def bullets(items,x,y0,wchars=None,lh=8.6*mm,fs=12.5,cdim=DIM):
    y=y0
    for t in items:
        c.setFillColor(GREY); c.setFont("MB",fs); c.drawString(x,y,"·")
        c.setFillColor(cdim); c.setFont("M",fs); c.drawString(x+5*mm,y,t)
        y-=lh
    return y

def bigno_grid(cells,cols=3,y_top=H-64*mm,cell_h=44*mm):
    """cells = [(number, label, note)]"""
    gw=(W-2*MX)/cols
    for i,(num,label,note) in enumerate(cells):
        col=i%cols; row=i//cols
        x=MX+col*gw; y=y_top-row*cell_h
        c.setStrokeColor(LINE); c.setLineWidth(0.5); c.line(x,y,x+gw-8*mm,y)
        c.setFont("MB",30); c.setFillColor(WHITE); c.drawString(x,y-13*mm,num)
        c.setFont("MB",11.5); c.setFillColor(DIM); c.drawString(x,y-21*mm,label)
        c.setFont("M",9.5); c.setFillColor(GREY); c.drawString(x,y-27.5*mm,note)


title_sl()


bg(); chrome("01 — 문제")
head("문제","우리는 AI를 소유하지 못하고, 빌려 쓴다",
     "중앙 클라우드 LLM 구조에는 갚을 수 없는 네 가지 청구서가 따라온다")
bigno_grid([("환각","출처를 증명 못 하는 답","의료·법률·금융에 치명적"),
            ("유출","내 기억이 남의 서버로","데이터 주권의 상실"),
            ("GPU","질문마다 수백 W","개인이 평생 못 돌리는 비용")],3,H-72*mm)
bigno_grid([("망각","대화가 끝나면 잊는다","자라나는 AI 구조의 부재")],3,H-124*mm)
c.setFont("MB",13); c.setFillColor(WHITE)
c.drawString(MX,26*mm,"이건 ‘더 큰 모델’이 아니라, ‘다른 구조’로 풀리는 문제다.")
newpage()


bg(); chrome("02 — 해법")
head("해법","뼈와 살 — 그리고 정직",
     "지식(뼈)은 그래프에, 말(살)은 검증된 문장에서. 사실과 표현이 분리되어 오염되지 않는다")
y=bullets([
 "답한다, 그러나 지어내지 않는다 — 근거가 없으면 ‘모른다’가 정답",
 "모든 답에 추론 증명서(근거 개념 · 도출 경로 · 보증) 부착 → 감사 가능",
 "후보 ↔ 검증 분리 — 새 지식은 게이트(출처·중복·모순·품질)를 통과해야 승격",
 "아이가 다섯 살까지 듣는 말로 언어를 깨치듯 — 순도 높은 15만 문장 식단으로 목소리를 기른다",
 "개인 기억은 기기 밖으로 절대 나가지 않는다 (로컬-first)",
],MX,H-72*mm,lh=10*mm,fs=13)
c.setFont("MB",13); c.setFillColor(WHITE)
c.drawString(MX,26*mm,"“진실이 커버리지보다 먼저다.”")
newpage()


bg(); chrome("03 — 제품")
head("제품 · 2026.07","구상이 아니라, 스스로 배우고 스스로 지키며 돈다",
     "사람이 자리를 비워도 — 스스로를 지키며 달린다")
bigno_grid([("24h","자율 학습","위키·웹 검증 파이프 · 시간당 ~1,500문장"),
            ("15분","품질 파수꾼 주기","회귀 감지 → 학습 자동 동결 → 자동 복구 (실증)"),
            ("8/10","프런티어 추론","은유 해석 · 반사실 · 유추 · 모순 감지")],3,H-70*mm)
y=bullets([
 "갭 자동 시딩 — 모르는 개념을 만나면 스스로 학습 대기열에 올린다",
 "살아있는 구조 — 재시작에도 이어지는 연속 자아 · 5-호르몬 동역학 · 밤의 의회(스스로 학습 주제 제안)",
 "얼굴과 계기판 — 파티클 아바타 ‘아토’ · 로컬 채팅(/chat) · 실시간 OPS 대시보드(폰 지원)",
],MX,H-122*mm,lh=9*mm,fs=12)
c.setFont("MB",13); c.setFillColor(WHITE)
c.drawString(MX,26*mm,"목표는 챗봇이 아니라 — 프로그램 안에 사는 정직한 생명체.")
newpage()


bg(); chrome("04 — 측정된 사실")
head("측정된 사실","마케팅이 아니라, 코드로 재현되는 숫자",
     "65문항 완성 게이트 배터리 · 봉인 홀드아웃 · 커밋 단위 재현")
bigno_grid([("완성","배터리 판정 (65문항)","P0 23/23 · P1 31/32 · p50 ~2초"),
            ("92%","봉인 홀드아웃 QA","날조(근거 없는 단정) 0건"),
            ("94%","정직성 배터리","모르는 걸 아는 척하지 않는가")],3,H-70*mm)
bigno_grid([("2,600만","지식 그래프 트리플","적재 96만 행/s · 터보 3.0M 행/s"),
            ("0 GPU","답변 시 모델 추론","~0.001 Wh/질문 · 설치 ~11 MB"),
            ("0.25초","전 그래프 VRAM 미러","606MB · 64차원 관계 임베딩 자체 훈련")],3,H-124*mm)
c.setFont("M",9.5); c.setFillColor(GREY)
c.drawString(MX,26*mm,"정직한 한계: 커버리지는 LLM보다 좁고 장문 창작은 아직 얕다(식단 축적 중) — 숨긴 결함이 아니라 설계상 트레이드오프.")
newpage()


bg(); chrome("05 — 3박자")
head("장기 비전","하나의 그래프 뇌가, 세 겹의 몸을 입는다",
     "LLM은 클라우드에서 아래로 — ATANOR는 기기에서 위로")
gw=(W-2*MX)/3
labels=[("① 프로그램","지금 · 완성 게이트 통과","로컬 엔진+웹앱 — 65문항 배터리 ‘완성’ 판정"),
        ("② 브라우저","진행 · 확장 v0.8.3","AI가 스스로 서핑하며 배우는 인지 서핑 → AI 브라우저"),
        ("③ OS","첫 부팅 완료","Rust 자체 컴포지터(M1) — ATANOR Linux 부팅 실증")]
for i,(t,st,d) in enumerate(labels):
    x=MX+i*gw
    c.setStrokeColor(LINE); c.setLineWidth(0.7); c.rect(x,H-118*mm,gw-8*mm,44*mm,stroke=1,fill=0)
    c.setFont("MB",16); c.setFillColor(WHITE); c.drawString(x+6*mm,H-86*mm,t)
    c.setFont("MB",10.5); c.setFillColor(DIM); c.drawString(x+6*mm,H-94*mm,st)
    c.setFont("M",9.5); c.setFillColor(GREY)
    # naive two-line wrap
    if len(d)>26:
        c.drawString(x+6*mm,H-101*mm,d[:26]); c.drawString(x+6*mm,H-106*mm,d[26:])
    else:
        c.drawString(x+6*mm,H-101*mm,d)
y=bullets([
 "각 층이 같은 뇌를 공유 — 배울수록 셋이 함께 똑똑해진다",
 "개인 데이터가 앱→브라우저→OS 어디서도 밖으로 새지 않는 유일한 스택 — 구조적 해자",
],MX,H-132*mm,lh=9*mm,fs=12.5)
newpage()


bg(); chrome("06 — 시장")
head("시장","‘틀리면 안 되고, 나가면 안 되고, 싸야 하는’ 곳",
     "가장 똑똑한 모델 경쟁이 아니라 — 신뢰 세그먼트를 정조준")
bigno_grid([("$11.8B","엣지/온디바이스 AI · 2025","→ $56.8B (2030) · CAGR 36.9%"),
            ("온프레미스","데이터 반출 불가 조직","엔터프라이즈 AI의 구조적 수요축"),
            ("규제","EU AI Act — 감사가능성","‘출처를 증명하는 AI’가 규제 대응 자산")],3,H-70*mm)
y=bullets([
 "초기: 개발자·연구자 (자기 문서·코드를 장기 기억으로) → 소규모 팀 온프레미스",
 "확장: 금융·의료·법률·공공 — 환각과 유출이 허용되지 않는 산업",
],MX,H-122*mm,lh=9*mm,fs=12.5)
newpage()


bg(); chrome("07 — 비즈니스 모델")
head("비즈니스 모델","COGS가 0에 수렴하는 AI",
     "추론에 GPU가 들지 않는다 — 가격·마진·엣지 배포 전부의 구조적 우위")
rows=[("개인 구독","월 9,900–29,000원","로컬 그래프 관리 · 백그라운드 학습"),
      ("Pro","월 39,000–99,000원","개발자·연구자 — 문서/코드 인덱싱 · 프로젝트 브레인"),
      ("온프레미스","구축 + 월유지 + 시트","팀/기업 — 데이터 반출 없는 사내 지식 AI"),
      ("카트리지 마켓","수수료 / 구독","도메인 그래프(법률·의료·창업) 장터"),
      ("브라우저→OS","무료 퍼널 → 라이선스","3박자 완성 시 기기·OS 라이선스 (장기)")]
y=H-66*mm
for name,price,desc in rows:
    c.setStrokeColor(LINE); c.setLineWidth(0.4); c.line(MX,y+4.5*mm,W-MX,y+4.5*mm)
    c.setFont("MB",12.5); c.setFillColor(WHITE); c.drawString(MX,y,name)
    c.setFont("MB",11.5); c.setFillColor(DIM); c.drawString(MX+62*mm,y,price)
    c.setFont("M",11); c.setFillColor(GREY); c.drawString(MX+128*mm,y,desc)
    y-=11.5*mm
c.setFont("MB",12.5); c.setFillColor(WHITE)
c.drawString(MX,26*mm,"초기 검증: Pro + 온프레미스 → 카트리지 마켓 → 3박자 스택.")
newpage()


bg(); chrome("08 — 경쟁")
head("경쟁","방향이 반대다",
     "그들은 클라우드 모델을 아래로 내린다 — 우리는 로컬 그래프 뇌를 위로 올린다")
rows=[("ChatGPT · Claude","범용 추론의 정점","로컬 지식 소유 없음 · 검증 그래프 아님"),
      ("Perplexity","검색+출처 답변","검색 응답일 뿐 — 지식이 쌓이지 않는다"),
      ("로컬 LLM (Llama 등)","오프라인 구동","환각 여전 · 수 GB 가중치 — ATANOR는 0"),
      ("AI 브라우저 (Arc·Comet)","브라우징 보조","클라우드 LLM을 얹음 — 우리는 로컬 뇌가 브라우저를 쓴다")]
y=H-66*mm
for name,st,diff in rows:
    c.setStrokeColor(LINE); c.setLineWidth(0.4); c.line(MX,y+4.5*mm,W-MX,y+4.5*mm)
    c.setFont("MB",12.5); c.setFillColor(WHITE); c.drawString(MX,y,name)
    c.setFont("M",11); c.setFillColor(DIM); c.drawString(MX+72*mm,y,st)
    c.setFont("M",11); c.setFillColor(GREY); c.drawString(MX+136*mm,y,diff)
    y-=12*mm
c.setFont("MB",12.5); c.setFillColor(WHITE)
c.drawString(MX,26*mm,"해자 = 정직성 + 경량성 + 프라이버시 + 3박자 수직통합의 결합.")
newpage()


bg(); chrome("09 — 로드맵")
head("로드맵","식단 완주 → 베타 → 온프레미스 → OS")
cols=[("단기 0–6개월",["문장 식단 15만 완주 (수일 내) → 유창성 개화","클로즈드 베타 + 사전예약","공개 벤치마크 · 에너지 백서"]),
      ("중기 6–18개월",["온프레미스 패키지 + 도메인 카트리지","브라우저 확장 정식 배포 (스토어)","샤딩 스케일 + Atlas Network v1"]),
      ("장기 18개월+",["ATANOR OS — 디바이스 연속성","모든 기기에서 같은 뇌, 같은 자아","‘믿을 수 있는 답’의 표준"])]
gw=(W-2*MX)/3
for i,(t,items) in enumerate(cols):
    x=MX+i*gw
    c.setFont("MB",13.5); c.setFillColor(WHITE); c.drawString(x,H-64*mm,t)
    c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(x,H-68*mm,x+gw-10*mm,H-68*mm)
    yy=H-78*mm
    for it in items:
        c.setFillColor(GREY); c.setFont("MB",11); c.drawString(x,yy,"·")
        c.setFillColor(DIM); c.setFont("M",10.5)
        if len(it)>24:
            c.drawString(x+4*mm,yy,it[:24]); c.drawString(x+4*mm,yy-5*mm,it[24:]); yy-=14*mm
        else:
            c.drawString(x+4*mm,yy,it); yy-=9*mm
newpage()


bg(); chrome("10 — 팀")
head("팀","김안석 — 단독 창업자",
     "넥스트챌린지스쿨 (서울시교육청 인가 · 국내 첫 창업 특화 대안고) — Google·Intel·Thales 협력")
y=bullets([
 "시나브로 (문학인 SNS) — 학생창업유망팀 U300+ 도약트랙 최종선발",
 "WETHUS (학생 창업 플랫폼) — ‘모두의 창업’ 1차 심사 통과",
 "BELIFE (개인 인텔리전스) — 생각·감정·가치관 구조화 실험",
],MX,H-70*mm,lh=10*mm,fs=13)
c.setFont("M",12); c.setFillColor(DIM)
c.drawString(MX,H-108*mm,"일관된 한 줄기: ‘사람의 생각을 구조화하고 연결하는 플랫폼’ — 그 끝에서 만난 질문,")
c.setFont("MB",14); c.setFillColor(WHITE)
c.drawString(MX,H-117*mm,"“이 사람들의 생각과 기억은, 결국 누구의 것인가.”")
c.setFont("M",11.5); c.setFillColor(GREY)
c.drawString(MX,26*mm,"고등학생이지만 — 아이디어가 아니라 측정 가능한 사실까지 만들어내는 실행력.")
newpage()


bg()
cx=W/2
if os.path.exists(LOGO):
    img=ImageReader(LOGO); iw,ih=img.getSize(); tw=54*mm; th=tw*(ih/iw)
    c.drawImage(img,cx-tw/2,H/2+16*mm,width=tw,height=th,mask='auto')
c.setFont("MB",22); c.setFillColor(WHITE)
c.drawCentredString(cx,H/2-2*mm,"답한다, 그러나 지어내지 않는다.")
c.setFont("M",12); c.setFillColor(DIM)
c.drawCentredString(cx,H/2-13*mm,"AI를 빌리는 시대에서, 소유하는 시대로 — 프로그램 · 브라우저 · OS")
c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(cx-28*mm,H/2-21*mm,cx+28*mm,H/2-21*mm)
c.setFont("M",10.5); c.setFillColor(GREY)
c.drawCentredString(cx,H/2-31*mm,"김안석 · github.com/Cozystone/ATANOR · 2026.07")
c.setFont("M",9); c.setFillColor(FAINT)
c.drawCentredString(cx,18*mm,"본 덱의 모든 수치는 자체 실측이며 커밋 단위로 재현됩니다.")
c.showPage()

c.save()
print("WROTE",out)
