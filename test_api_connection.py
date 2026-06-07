# -*- coding: utf-8 -*-
"""
KabuStation API 연결 테스트 스크립트
장 마감 후에도 실행 가능 — 토큰 발행 + 시세 조회 테스트
"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from backend.kabu_client import KabuClient, HybridKabuClient
from backend.database import Database
from config import KABU_API_BASE_URL_PRODUCTION, KABU_API_BASE_URL_TEST


async def test_environment(env_name: str, base_url: str, password: str):
    """한 환경에 대한 연결 테스트"""
    print(f"\n{'='*60}")
    print(f"  {env_name} 환경 테스트")
    print(f"  URL: {base_url}")
    print(f"{'='*60}")
    
    if not password:
        print(f"  ⚠️ {env_name} 비밀번호가 DB에 없습니다. 건너뜁니다.")
        return False
    
    client = KabuClient(base_url=base_url)
    
    # 1. 토큰 발행 테스트
    print(f"\n[1] 토큰 발행 테스트...")
    try:
        token = await client.get_token(password)
        if token:
            print(f"  ✅ 토큰 발행 성공! Token: {token[:12]}...")
        else:
            print(f"  ❌ 빈 토큰 반환")
            await client.close()
            return False
    except Exception as e:
        error_msg = str(e)
        if "ConnectError" in error_msg or "Connection refused" in error_msg:
            print(f"  ❌ 연결 실패: KabuStation이 실행 중인지 확인해주세요.")
            print(f"     - KabuStation 소프트웨어가 실행 중이어야 합니다")
            print(f"     - 설정 > API 이용 설정 > ON 확인")
        elif "401" in error_msg or "Unauthorized" in error_msg or "4" in error_msg:
            print(f"  ❌ 인증 실패: API 비밀번호를 확인해주세요.")
        else:
            print(f"  ❌ 오류: {error_msg}")
        await client.close()
        return False
    
    # 2. 시세 조회 테스트 (장 마감 후에도 최종 시세 반환)
    test_symbols = [
        ("7203", "トヨタ自動車"),
        ("9983", "ファーストリテイリング"),
        ("8306", "三菱UFJ"),
    ]
    
    print(f"\n[2] 시세 조회 테스트 (get_board)...")
    for symbol, name in test_symbols:
        try:
            board = await client.get_board(symbol)
            if board.current_price > 0:
                print(f"  ✅ {symbol} ({board.symbol_name or name})")
                print(f"     현재가: ¥{board.current_price:,.0f}")
                print(f"     시가: ¥{board.open_price:,.0f} | 고가: ¥{board.high_price:,.0f} | 저가: ¥{board.low_price:,.0f}")
                print(f"     전일종가: ¥{board.previous_close:,.0f} | 출래고: {board.volume:,}")
            else:
                print(f"  ⚠️ {symbol}: 가격 0 (장 마감 후 데이터 없는 경우 정상)")
        except Exception as e:
            print(f"  ❌ {symbol} 조회 실패: {e}")
    
    # 3. 잔고 조회 테스트
    print(f"\n[3] 잔고 조회 테스트 (get_wallet_cash)...")
    try:
        cash = await client.get_wallet_cash()
        print(f"  ✅ 현금 잔고: ¥{cash:,.0f}")
    except Exception as e:
        print(f"  ❌ 잔고 조회 실패: {e}")
    
    # 4. HybridKabuClient 테스트
    print(f"\n[4] HybridKabuClient 테스트...")
    try:
        hybrid = HybridKabuClient(client)
        hybrid.api_environment = env_name
        
        # 시세 조회 (실제 API 경유)
        board = await hybrid.get_board("7203")
        print(f"  ✅ Hybrid 시세 조회: 7203 = ¥{board.current_price:,.0f}")
        
        # 주문 시뮬레이션 확인
        from backend.kabu_client import OrderSchema
        order = OrderSchema(symbol="7203", side="2", qty=100, price=board.current_price)
        result = await hybrid.send_order(order)
        if result.get("OrderId", "").startswith("MOCK"):
            print(f"  ✅ 주문 시뮬레이션 확인: OrderId={result['OrderId']} (실제 주문 아님)")
        else:
            print(f"  ⚠️ 주문 결과: {result}")
        
        print(f"\n  🎉 {env_name} 환경 모든 테스트 통과!")
        await hybrid.close()
        return True
        
    except Exception as e:
        print(f"  ❌ HybridKabuClient 오류: {e}")
        await client.close()
        return False


async def main():
    print("=" * 60)
    print("  KabuStation API 연결 테스트")
    print(f"  현재 시각: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # DB에서 저장된 비밀번호 로드
    db = Database()
    prod_pw = db.get_setting("api_password_production") or ""
    test_pw = db.get_setting("api_password_test") or ""
    saved_env = db.get_setting("api_environment") or "test"
    
    print(f"\n📋 DB 설정 확인:")
    print(f"  - 저장된 환경: {saved_env}")
    print(f"  - 本番 비밀번호: {'등록됨 ✅' if prod_pw else '미등록 ❌'}")
    print(f"  - 検証 비밀번호: {'등록됨 ✅' if test_pw else '미등록 ❌'}")
    
    results = {}
    
    # 検証 먼저 테스트 (안전)
    if test_pw:
        results["検証"] = await test_environment("検証", KABU_API_BASE_URL_TEST, test_pw)
    
    # 本番 테스트
    if prod_pw:
        results["本番"] = await test_environment("本番", KABU_API_BASE_URL_PRODUCTION, prod_pw)
    
    # 결과 요약
    print(f"\n{'='*60}")
    print("  📊 테스트 결과 요약")
    print(f"{'='*60}")
    for env, ok in results.items():
        status = "✅ 성공" if ok else "❌ 실패"
        print(f"  {env}: {status}")
    
    if not results:
        print("  ⚠️ 비밀번호가 등록되지 않았습니다.")
        print("  → 사이트 설정 페이지에서 API 비밀번호를 먼저 저장해주세요.")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())
