"""Round-trip CARA classification against the shipped eco_base book."""

from __future__ import annotations

import unittest

from app.services.opening_service import OpeningService, parse_move_sans

from tests.opening_integrity.helpers import (
    SKIP_IN_CI,
    SKIP_REASON,
    collision_groups,
    display_tuple,
    iter_base_rows,
    load_tests_if_not_ci as load_tests,
    opening_service,
    replay_fen,
    rewrite_fen,
)


@unittest.skipIf(SKIP_IN_CI, SKIP_REASON)
class TestClassificationRoundtrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.svc = opening_service()
        cls.rows = iter_base_rows(cls.svc)
        cls.collisions = collision_groups(cls.svc, cls.rows)

    def test_book_has_named_base_rows(self) -> None:
        self.assertGreater(len(self.rows), 10000)

    def test_exact_stored_fen_returns_own_row(self) -> None:
        failures = []
        for row in self.rows:
            got = display_tuple(self.svc, row.fen)
            if got != (row.eco, row.name):
                failures.append((row.eco, row.name, got, row.src))
                if len(failures) >= 20:
                    break
        self.assertEqual(failures, [], msg=f"exact FEN mismatches: {failures}")

    def test_replaying_book_moves_returns_same_opening(self) -> None:
        """Playing a row's SAN should classify as that row (python-chess FEN)."""
        illegal = []
        mismatches = []
        for row in self.rows:
            replayed = replay_fen(row)
            if replayed is None:
                illegal.append((row.eco, row.name, row.moves, row.src))
                continue
            got = display_tuple(self.svc, replayed)
            if got != (row.eco, row.name):
                mismatches.append((row.eco, row.name, got, row.moves, row.src))
                if len(mismatches) >= 20:
                    break
        self.assertEqual(illegal, [], msg=f"illegal book move strings: {illegal[:10]}")
        self.assertEqual(mismatches, [], msg=f"replay mismatches: {mismatches}")

    def test_collision_exact_fens_keep_own_identity(self) -> None:
        """Clock/EP twins (e.g. A45 Chigorin vs D00 Veresov) keep their stored row."""
        self.assertGreater(len(self.collisions), 0)
        failures = []
        for group in self.collisions.values():
            labels = {(row.eco, row.name) for row in group}
            if len(labels) < 2:
                continue
            for row in group:
                got = display_tuple(self.svc, row.fen)
                if got != (row.eco, row.name):
                    failures.append((row.fen, row.eco, row.name, got))
        self.assertEqual(failures, [], msg=f"collision identity failures: {failures[:10]}")

    def test_book_key_winner_is_longest_line(self) -> None:
        """Placement+STM index keeps the longer canonical line (ties keep first)."""
        failures = []
        for key, group in self.collisions.items():
            winner = self.svc._classified_by_book_key.get(key)
            if not isinstance(winner, dict):
                failures.append((key, "missing winner"))
                continue
            win_depth = len(parse_move_sans(str(winner.get("moves") or "")))
            max_depth = max(len(parse_move_sans(row.moves)) for row in group)
            if win_depth != max_depth:
                failures.append(
                    (
                        key,
                        winner.get("eco"),
                        winner.get("name"),
                        win_depth,
                        max_depth,
                    )
                )
        self.assertEqual(failures, [], msg=f"book_key depth policy: {failures[:10]}")

    def test_book_key_lookup_uses_winner_when_clocks_differ(self) -> None:
        """A placement+STM FEN that is not an exact stored row follows book_key."""
        checked = 0
        failures = []
        for key, group in self.collisions.items():
            winner = self.svc._classified_by_book_key.get(key)
            if not isinstance(winner, dict):
                continue
            placement = key.split(" ", 1)[0]
            stm = key.split(" ", 1)[1] if " " in key else "w"
            probe = f"{placement} {stm} - - 1 3"
            if probe in (self.svc._eco_base or {}):
                continue
            if OpeningService.book_key(probe) != key:
                continue
            got = display_tuple(self.svc, probe)
            expected = (
                str(winner.get("eco") or "").strip(),
                str(winner.get("name") or "").strip(),
            )
            if got != expected:
                failures.append((probe, expected, got))
            checked += 1
            if checked >= 50:
                break
        self.assertGreater(checked, 0)
        self.assertEqual(failures, [], msg=f"clock-stripped lookups: {failures[:10]}")


@unittest.skipIf(SKIP_IN_CI, SKIP_REASON)
class TestClassificationKnownCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.svc = opening_service()

    def _fen_after(self, *sans: str) -> str:
        from app.services.opening_service import fen_after_sans

        fen = fen_after_sans(list(sans))
        assert fen is not None
        return fen

    def test_chigorin_clock0_is_a45_from_book(self) -> None:
        fen = "rnbqkb1r/ppp1pppp/5n2/3p4/3P4/2N5/PPP1PPPP/R1BQKBNR w KQkq - 0 3"
        got = display_tuple(self.svc, fen)
        self.assertEqual(got, ("A45", "Queen's Pawn Game: Chigorin Variation"))

    def test_veresov_clock2_is_d00_from_book(self) -> None:
        fen = "rnbqkb1r/ppp1pppp/5n2/3p4/3P4/2N5/PPP1PPPP/R1BQKBNR w KQkq - 2 3"
        got = display_tuple(self.svc, fen)
        self.assertEqual(got, ("D00", "Queen's Pawn: Veresov Attack"))

    def test_d02_chigorin_is_nf3_nc6_not_nc3(self) -> None:
        fen = self._fen_after("d4", "d5", "Nf3", "Nc6")
        got = display_tuple(self.svc, fen)
        self.assertIsNotNone(got)
        self.assertEqual(got[0], "D02")
        self.assertIn("Chigorin", got[1])

    def test_modern_line_not_vant_kruijs(self) -> None:
        fen = self._fen_after("d4", "g6", "Nf3", "Bg7", "e3", "d6")
        self.assertEqual(self.svc.get_opening_info(fen), (None, None))
        last = None
        from app.services.opening_service import fen_after_sans

        prefix: list[str] = []
        for san in ["d4", "g6", "Nf3", "Bg7", "e3", "d6"]:
            prefix.append(san)
            info = self.svc.get_opening_info(fen_after_sans(prefix) or "")
            if info[0]:
                last = info
        self.assertIsNotNone(last)
        self.assertEqual(last[0], "A40")
        self.assertIn("Modern", last[1] or "")
        self.assertNotIn("Kruijs", last[1] or "")

    def test_zukertort_transposes_to_four_knights(self) -> None:
        fen = self._fen_after("Nf3", "Nf6", "e4", "Nc6", "Nc3", "e5")
        got = display_tuple(self.svc, fen)
        self.assertEqual(got[0], "C47")
        self.assertIn("Four Knights", got[1] or "")

    def test_junk_clocks_still_classify_unique_position(self) -> None:
        """Exact FEN uses clocks; a long-game clock string must still book_key-hit."""
        fen = self._fen_after("e4", "e5", "Nf3", "Nc6", "Bc4")
        expected = display_tuple(self.svc, fen)
        self.assertEqual(expected, ("C50", "Italian Game"))
        junk = rewrite_fen(fen, clocks=("40", "60"))
        self.assertNotEqual(junk, fen)
        self.assertEqual(display_tuple(self.svc, junk), expected)

    def test_irrelevant_ep_square_does_not_change_label(self) -> None:
        fen = self._fen_after("e4", "e5", "Nf3", "Nc6", "Bc4")
        expected = display_tuple(self.svc, fen)
        self.assertEqual(fen.split()[3], "-")
        noisy = rewrite_fen(fen, ep="e3")
        self.assertEqual(display_tuple(self.svc, noisy), expected)

    def test_black_to_move_position_classifies(self) -> None:
        fen = self._fen_after("Nh3")
        self.assertEqual(fen.split()[1], "b")
        got = display_tuple(self.svc, fen)
        self.assertEqual(got, ("A00", "Amar Opening"))
        self.assertEqual(
            display_tuple(self.svc, rewrite_fen(fen, clocks=("40", "60"))),
            got,
        )

    def test_white_to_move_position_classifies(self) -> None:
        fen = self._fen_after("e4", "e5")
        self.assertEqual(fen.split()[1], "w")
        self.assertEqual(
            display_tuple(self.svc, fen),
            ("C20", "King's Pawn Game"),
        )

    def test_stm_is_part_of_the_book_key(self) -> None:
        fen = self._fen_after("e4", "e5", "Nf3", "Nc6", "Bc4")
        self.assertEqual(fen.split()[1], "b")
        self.assertIsNotNone(display_tuple(self.svc, fen))
        self.assertIsNone(display_tuple(self.svc, rewrite_fen(fen, stm="w")))

    def test_castling_rights_are_noise_on_book_key(self) -> None:
        fen = self._fen_after("e4", "e5", "Nf3", "Nc6", "Bc4")
        expected = display_tuple(self.svc, fen)
        self.assertIn("K", fen.split()[2])
        self.assertEqual(
            display_tuple(self.svc, rewrite_fen(fen, castling="-")),
            expected,
        )

    def test_position_after_white_castles_still_classifies(self) -> None:
        fen = self._fen_after(
            "e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O"
        )
        self.assertEqual(fen.split()[2], "kq")
        got = display_tuple(self.svc, fen)
        self.assertEqual(got[0], "C78")
        self.assertIn("Ruy Lopez", got[1] or "")

    def test_lookup_miss_is_none_not_an_exception(self) -> None:
        probes = (
            "",
            "not a fen",
            "8/8/8/8/8/8/8/8 w - - 0 1",
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        )
        for fen in probes:
            with self.subTest(fen=fen):
                self.assertIsNone(self.svc.lookup_opening(fen))
                self.assertEqual(self.svc.get_opening_info(fen), (None, None))


if __name__ == "__main__":
    unittest.main()
