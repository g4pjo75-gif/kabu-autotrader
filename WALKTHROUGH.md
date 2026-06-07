# Antigravity 프로젝트 설정 완료

## 요약

명세서 3개(backend_spec.md, frontend_spec.md, project_structure.md)를 기반으로 프로젝트 구조를 생성했습니다.

---

## 생성된 파일 구조

```
antigravity/
├── main.py                  # 앱 엔트리포인트 (NiceGUI)
├── config.py                # 전역 설정 (포트, 기본값)
├── requirements.txt         # 의존성 목록
│
├── backend/
│   ├── __init__.py
│   ├── kabu_client.py       # API 래퍼 + MockKabuClient ✨
│   ├── universe.py          # 대상 종목 선택 (Nikkei225, Ranking, CSV)
│   ├── notifier.py          # Telegram 알림
│   ├── database.py          # SQLite 핸들러
│   └── scheduler.py         # APScheduler 설정
│
├── strategies/
│   ├── __init__.py
│   ├── base.py              # BaseStrategy 추상 클래스
│   ├── extraction.py        # 9개 종목 추출 전략
│   └── execution.py         # 6개 주문 실행 전략
│
├── frontend/
│   ├── __init__.py
│   ├── layout.py            # 사이드바, 헤더, 다크 테마
│   └── pages/
│       ├── __init__.py
│       ├── settings.py      # 연결 & Telegram 설정
│       ├── extraction.py    # 종목 추출 UI
│       ├── trading.py       # 자동매매 제어 UI
│       └── dashboard.py     # 모니터링 대시보드
│
└── data/
    └── nikkei225.csv        # Nikkei 225 종목 샘플
```

---

## MockKabuClient 포함

`backend/kabu_client.py`에 다음이 포함되어 있습니다:

| 클래스 | 설명 |
|--------|------|
| `BaseKabuClient` | 추상 베이스 클래스 |
| `KabuClient` | 실제 kabu Station API 연결 |
| `MockKabuClient` | **API 없이 테스트 가능** ✨ |

MockKabuClient는:
- 10개 주요 종목의 가격 데이터 시뮬레이션
- 랜덤 가격 변동 (±2%)
- 주문 실행 시뮬레이션
- 잔고/포지션 추적

---

## 전략 클래스

### Extraction (종목 필터링) - 9개
| 클래스명 | 설명 |
|----------|------|
| `SMAGoldenDeadCross` | SMA 골든/데드 크로스 |
| `StockSMAEMACross` | SMA/EMA 정렬 |
| `StockMACDShift` | MACD 히스토그램 반전 |
| `StockRSIStochastic` | RSI & 스토캐스틱 과매도 |
| `TurtleBreakoutFilter` | 20/55일 고가/저가 돌파 |
| `TurtleLiquidityFilter` | 최소 거래량 필터 |
| `TurtleVolatilityFilter` | ATR 변동성 필터 |
| `BollingerBands` | 밴드 스퀴즈/확장 |
| `CandlePatterns` | 도지, 해머, 장악형 패턴 |

### Execution (주문 로직) - 6개
| 클래스명 | 설명 |
|----------|------|
| `StockSplitFunds` | 자금 1/N 분할 |
| `BasicLossCutManager` | -X% 손절 |
| `TurtlePyramidNewOrder` | 피라미딩 추가 주문 |
| `TrackingPriceModifyBuy` | 미체결시 가격 추적 수정 |
| `TurtleSafetyCancel` | N초 후 미체결 취소 |
| `PriceRangeCanceller` | 가격 괴리시 취소 |

---

## 실행 방법

```bash
# 1. 의존성 설치
cd antigravity
pip install -r requirements.txt

# 2. 앱 실행
python main.py
```

브라우저에서 `http://localhost:8080` 접속

> 기본적으로 **시뮬레이션 모드**가 활성화되어 있어 kabu Station API 없이도 UI와 로직을 테스트할 수 있습니다.

---

## 🕹️ 실전 데이터 기반 모의 투자 (Paper Trading) 가이드

다음 주 월요일(주식 시장 개장일)부터 다음 순서대로 테스트를 진행하세요.

### 1. 사전 준비
- **서버 실행**: `antigravity` 폴더에서 `python main.py` 실행
- **접속**: 브라우저로 `http://localhost:8080` 이동
- **자산 확인**: `대시보드` 메뉴에서 **총 자산 ¥5,000,000** 확인

### 2. 종목 발굴 (09:00 이후 권장)
1. `종목 발굴` 메뉴로 이동
2. **[분석 시작]** 버튼 클릭
   - `yfinance`를 통해 Nikkei 225 종목의 최신 데이터를 분석합니다.
   - 진행률 막대가 100%가 될 때까지 기다립니다.
3. 분석 완료 후 유망 종목 리스트 확인
4. 원하는 종목의 **(+)** 버튼을 눌러 `자동 매매 등록`

### 3. 자동 매매 시작
1. `자동 매매` 메뉴로 이동
2. `대상 종목` 리스트에 방금 추가한 종목들이 있는지 확인
3. **매매 로직 설정** (우측 패널)
   - `매수 로직`: 예) 자금 분할 (StockSplitFunds)
   - `매도 로직`: 예) 기본 손절 (BasicLossCutManager)
   - **Tip**: 각 로직 제목 옆의 **(?)** 버튼을 눌러 상세 설명을 확인하세요.
4. 상단의 **[시작]** 버튼 클릭
   - 상태가 **"자동 매매 가동 중"**으로 변경됩니다.
   - 5초 주기로 매매 로직이 실행되며, **실제 시장 가격**을 기반으로 매수/매도 판단을 합니다.

### 4. 모니터링 및 결과 확인
- `대시보드` 메뉴로 이동
- **체결 내역**: 매매가 체결되면 실시간으로 내역이 기록됩니다.
- **자산 변동**: 평가 손익에 따라 총 자산이 변동되는 것을 확인하세요.
- **일자별 조회**: 날짜 선택기를 이용해 지난 내역을 조회할 수 있습니다.

### 주의사항
- **지연 시세**: `yfinance` 데이터는 실시간보다 약 15~20분 지연될 수 있습니다.
- **모의 투자**: 실제 돈이 들어가지 않는 가상 매매입니다.
- **재시작 시 데이터**: 매매 내역은 DB에 저장되어 유지되지만, 모의 잔고는 서버 재시작 시 초기화될 수 있습니다 (현재 설정 기준).

---

## 다음 단계
1. 실행 후 브라우저 접속
2. 위 가이드에 따라 모의 투자 진행
3. 수익률 및 로직 검증 후 실전 투자 전환 고려
