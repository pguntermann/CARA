"""Variation-tree insert and remove on an existing PGN game."""

from __future__ import annotations

import unittest

import chess
import chess.pgn

from app.services.pgn_variation_tree_service import (
    VariationTreeError,
    insert_san_prefix,
    parse_pv_token,
    remove_variation_at_path,
    same_placement_and_turn,
)
from app.utils.pgn_variation_path import (
    collect_variation_comment_paths,
    remap_path_after_sideline_remove,
    sideline_fork,
)


def _game_from_mainline(*sans: str) -> chess.pgn.Game:
    game = chess.pgn.Game()
    node = game
    board = game.board()
    for san in sans:
        move = board.parse_san(san)
        node = node.add_variation(move)
        board.push(move)
    return game


class TestParsePvToken(unittest.TestCase):
    def test_san_and_uci(self) -> None:
        board = chess.Board()
        self.assertEqual(parse_pv_token(board, "e4"), chess.Move.from_uci("e2e4"))
        self.assertEqual(parse_pv_token(board, "e2e4"), chess.Move.from_uci("e2e4"))
        self.assertIsNone(parse_pv_token(board, "xyz"))
        self.assertIsNone(parse_pv_token(board, "e5"))


class TestSamePlacementAndTurn(unittest.TestCase):
    def test_ignores_clocks(self) -> None:
        a = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
        b = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 40 60"
        self.assertTrue(same_placement_and_turn(a, b))

    def test_stm_matters(self) -> None:
        w = chess.Board().fen()
        b = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"
        self.assertFalse(same_placement_and_turn(w, b))


class TestInsertSanPrefix(unittest.TestCase):
    def test_adds_sideline_when_first_move_differs(self) -> None:
        game = _game_from_mainline("e4")
        result = insert_san_prefix(game, (), ["d4"])
        self.assertEqual(result.added, 1)
        self.assertEqual(result.followed, 0)
        self.assertEqual(len(game.variations), 2)
        self.assertEqual(game.variation(0).move, chess.Move.from_uci("e2e4"))
        self.assertEqual(game.variation(1).move, chess.Move.from_uci("d2d4"))

    def test_follows_existing_then_branches(self) -> None:
        game = _game_from_mainline("e4", "e5")
        result = insert_san_prefix(game, (), ["e4", "c5"])
        self.assertEqual(result.followed, 1)
        self.assertEqual(result.added, 1)
        e4 = game.variation(0)
        self.assertEqual(len(e4.variations), 2)
        self.assertEqual(e4.variation(0).move, chess.Move.from_uci("e7e5"))
        self.assertEqual(e4.variation(1).move, chess.Move.from_uci("c7c5"))

    def test_already_present_adds_nothing(self) -> None:
        game = _game_from_mainline("e4", "e5")
        result = insert_san_prefix(game, (), ["e4", "e5"])
        self.assertEqual(result.added, 0)
        self.assertEqual(result.followed, 2)
        self.assertEqual(len(game.variations), 1)
        self.assertEqual(len(game.variation(0).variations), 1)

    def test_extends_end_of_line(self) -> None:
        game = _game_from_mainline("e4")
        result = insert_san_prefix(game, (), ["e4", "e5"])
        self.assertEqual(result.added, 1)
        self.assertEqual(result.followed, 1)
        self.assertEqual(len(game.variation(0).variations), 1)

    def test_from_mid_path(self) -> None:
        game = _game_from_mainline("e4", "e5", "Nf3")
        result = insert_san_prefix(game, (0,), ["c5"])
        e4 = game.variation(0)
        self.assertEqual(result.added, 1)
        self.assertEqual(len(e4.variations), 2)
        self.assertEqual(e4.variation(1).move, chess.Move.from_uci("c7c5"))

    def test_illegal_token_raises(self) -> None:
        game = _game_from_mainline("e4")
        with self.assertRaises(VariationTreeError):
            insert_san_prefix(game, (), ["e4", "e4"])

    def test_empty_tokens_raise(self) -> None:
        game = chess.pgn.Game()
        with self.assertRaises(VariationTreeError):
            insert_san_prefix(game, (), [])

    def test_uci_tokens_insert_sideline(self) -> None:
        game = _game_from_mainline("e4")
        result = insert_san_prefix(game, (), ["d2d4"])
        self.assertEqual(result.added, 1)
        self.assertEqual(game.variation(1).move, chess.Move.from_uci("d2d4"))

    def test_invalid_path_raises(self) -> None:
        game = _game_from_mainline("e4")
        with self.assertRaises(VariationTreeError):
            insert_san_prefix(game, (1,), ["d4"])


class TestSidelineFork(unittest.TestCase):
    def test_mainline_is_none(self) -> None:
        self.assertIsNone(sideline_fork(()))
        self.assertIsNone(sideline_fork((0, 0, 0)))

    def test_innermost_non_zero(self) -> None:
        self.assertEqual(sideline_fork((0, 1)), ((0,), 1))
        self.assertEqual(sideline_fork((0, 1, 0, 0)), ((0,), 1))
        self.assertEqual(sideline_fork((0, 1, 0, 1)), ((0, 1, 0), 1))
        self.assertEqual(sideline_fork((1,)), ((), 1))


class TestCollectVariationCommentPaths(unittest.TestCase):
    def test_emits_sideline_comment_path(self) -> None:
        game = _game_from_mainline("e4", "e5")
        insert_san_prefix(game, (), ["e4", "c5"])
        game.variation(0).variation(1).comment = "sicilian"
        self.assertEqual(collect_variation_comment_paths(game), [(0, 1)])

    def test_skips_mainline_comments(self) -> None:
        game = _game_from_mainline("e4", "e5")
        game.variation(0).comment = "best"
        self.assertEqual(collect_variation_comment_paths(game), [])


class TestRemapPathAfterRemove(unittest.TestCase):
    def test_snaps_deleted_branch_to_fork(self) -> None:
        self.assertEqual(
            remap_path_after_sideline_remove((0, 1, 0), (0,), 1),
            (0,),
        )

    def test_shifts_later_sibling(self) -> None:
        self.assertEqual(
            remap_path_after_sideline_remove((0, 2, 0), (0,), 1),
            (0, 1, 0),
        )

    def test_leaves_earlier_sibling(self) -> None:
        self.assertEqual(
            remap_path_after_sideline_remove((0, 0), (0,), 1),
            (0, 0),
        )

    def test_unrelated_path_unchanged(self) -> None:
        self.assertEqual(
            remap_path_after_sideline_remove((0, 0, 1), (1,), 1),
            (0, 0, 1),
        )


class TestRemoveVariationAtPath(unittest.TestCase):
    def test_removes_whole_sideline_from_later_move(self) -> None:
        game = _game_from_mainline("e4", "e5")
        insert_san_prefix(game, (), ["e4", "c5", "Nf3"])
        result = remove_variation_at_path(game, (0, 1, 0))
        self.assertEqual(result.fork_path, (0,))
        self.assertEqual(result.removed_index, 1)
        e4 = game.variation(0)
        self.assertEqual(len(e4.variations), 1)
        self.assertEqual(e4.variation(0).move, chess.Move.from_uci("e7e5"))

    def test_nested_sideline_only(self) -> None:
        game = _game_from_mainline("e4", "e5")
        insert_san_prefix(game, (), ["e4", "c5", "Nf3"])
        insert_san_prefix(game, (0, 1), ["d4"])
        c5 = game.variation(0).variation(1)
        self.assertEqual(len(c5.variations), 2)
        result = remove_variation_at_path(game, (0, 1, 1))
        self.assertEqual(result.fork_path, (0, 1))
        self.assertEqual(result.removed_index, 1)
        self.assertEqual(len(c5.variations), 1)
        self.assertEqual(c5.variation(0).move, chess.Move.from_uci("g1f3"))

    def test_root_sideline(self) -> None:
        game = _game_from_mainline("e4")
        insert_san_prefix(game, (), ["d4"])
        remove_variation_at_path(game, (1,))
        self.assertEqual(len(game.variations), 1)
        self.assertEqual(game.variation(0).move, chess.Move.from_uci("e2e4"))

    def test_mainline_raises(self) -> None:
        game = _game_from_mainline("e4", "e5")
        with self.assertRaises(VariationTreeError):
            remove_variation_at_path(game, (0, 0))

    def test_invalid_path_raises(self) -> None:
        game = _game_from_mainline("e4")
        with self.assertRaises(VariationTreeError):
            remove_variation_at_path(game, (0, 1))


if __name__ == "__main__":
    unittest.main()
