"""SEASON-DYNAMIC(2026-07-27) — 시즌 배너 계절어 동적화(A+B) + 메뉴 적응형 색 회귀 가드.

배경: tpl_13/tpl_41 이 '여름 신메뉴'·'민트색'·'쿨톤'으로 하드코딩돼 겨울에도 여름 배너가 나오던 문제.
계절어=[SEASON](월 자동 + 추가요청 오버라이드), 색=메뉴 적응형(하드코딩 제거).
"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services import template_generation as TG


def _current_kst_season() -> str:
    return TG._season_for_month(datetime.now(ZoneInfo("Asia/Seoul")).month)


class SeasonResolverTestCase(unittest.TestCase):
    def test_month_to_season_all_twelve(self) -> None:
        expected = {
            1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄", 6: "여름",
            7: "여름", 8: "여름", 9: "가을", 10: "가을", 11: "가을", 12: "겨울",
        }
        for month, season in expected.items():
            self.assertEqual(TG._season_for_month(month), season, f"month={month}")

    def test_override_korean_and_english(self) -> None:
        self.assertEqual(TG._resolve_season("가을 신상 감성"), "가을")
        self.assertEqual(TG._resolve_season("겨울 한정 강조"), "겨울")
        self.assertEqual(TG._resolve_season("봄 파스텔 느낌"), "봄")
        self.assertEqual(TG._resolve_season("winter vibe"), "겨울")
        self.assertEqual(TG._resolve_season("SPRING promo"), "봄")
        # 프론트 기본 플레이스홀더 예시 "시원한 여름 느낌" → 여름 오버라이드
        self.assertEqual(TG._resolve_season("시원한 여름 느낌 강조"), "여름")

    def test_no_override_falls_back_to_current_month(self) -> None:
        cur = _current_kst_season()
        self.assertEqual(TG._resolve_season(""), cur)
        self.assertEqual(TG._resolve_season(None), cur)
        self.assertEqual(TG._resolve_season("20대 타깃, 감성 강조"), cur)  # 계절어 없음


class BuildInstructionSeasonTestCase(unittest.TestCase):
    def test_tpl13_override_substituted_and_menu_adaptive_bg(self) -> None:
        instr, _grade, _size = TG.build_instruction("tpl_13_season_banner", "", "가을 신상")
        self.assertNotIn("[SEASON]", instr)               # 리터럴 잔존 금지
        self.assertIn("가을 신메뉴", instr)                # 오버라이드 반영
        self.assertNotIn("민트색", instr)                  # 하드코딩 색 제거
        self.assertIn("어울리는 부드러운 플랫 단색 배경", instr)  # 메뉴 적응형 색

    def test_tpl13_auto_season_no_literal_leak(self) -> None:
        instr, _g, _s = TG.build_instruction("tpl_13_season_banner", "냉면", "")
        self.assertNotIn("[SEASON]", instr)
        self.assertIn(f"{_current_kst_season()} 신메뉴", instr)

    def test_tpl41_override_and_no_summer_hardcode(self) -> None:
        instr, _g, _s = TG.build_instruction("tpl_41_season_limited", "냉면", "겨울")
        self.assertNotIn("[SEASON]", instr)
        self.assertIn("겨울 한정", instr)
        self.assertNotIn("쿨톤", instr)
        self.assertNotIn("여름 한정", instr)

    def test_non_season_template_unaffected(self) -> None:
        # [SEASON] 없는 일반 템플릿은 계절 치환과 무관 — 리터럴 [SEASON] 이 있을 리 없음
        instr, _g, _s = TG.build_instruction("tpl_45_diagonal_band", "크림 파스타", "")
        self.assertNotIn("[SEASON]", instr)


if __name__ == "__main__":
    unittest.main()
