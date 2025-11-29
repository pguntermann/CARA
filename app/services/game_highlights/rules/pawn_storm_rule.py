"""Rule for detecting pawn storms."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen, is_kingside_file, is_queenside_file, are_adjacent_files
from app.services.game_highlights.constants import PAWN_STORM_WINDOW


class PawnStormRule(HighlightRule):
    """Detects coordinated pawn advances on a flank (pawn storms)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for pawn storm highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Only detect in middlegame
        if not (context.opening_end < move_num < context.middlegame_end):
            return highlights
        
        pawn_storm_created = context.shared_state.get('pawn_storm_created', set())
        
        # Check white's pawn move
        if move.white_move and len(move.white_move) >= 2 and move.white_move[0].islower():
            board_after = parse_fen(move.fen_white)
            if board_after and context.move_index > 0 and context.prev_move and context.prev_move.fen_black:
                board_before = parse_fen(context.prev_move.fen_black)
                
                if board_before:
                    white_pawns_before = list(board_before.pieces(chess.PAWN, chess.WHITE))
                    white_pawns_after = list(board_after.pieces(chess.PAWN, chess.WHITE))
                    
                    moved_pawn_square = None
                    for sq in white_pawns_after:
                        if sq not in white_pawns_before:
                            moved_pawn_square = sq
                            break
                    
                    if moved_pawn_square:
                        dest_file = chess.square_file(moved_pawn_square)
                        dest_rank = chess.square_rank(moved_pawn_square)
                        
                        # Find the source square of the moved pawn
                        source_square = None
                        for sq in white_pawns_before:
                            if sq not in white_pawns_after:
                                source_square = sq
                                break
                        
                        # Check if this is a capture (pawn changed files)
                        is_capture = False
                        source_rank = None
                        if source_square is not None:
                            source_file = chess.square_file(source_square)
                            source_rank = chess.square_rank(source_square)
                            if source_file != dest_file:
                                is_capture = True
                        
                        # Pawn storms are about forward advances, not captures
                        # A capture that changes files is tactical, not part of a storm
                        # Check if this is actually a forward advance
                        is_advance = False
                        if source_rank is not None:
                            # For white, advancing means moving to higher rank (0-7, where 7 is 8th rank)
                            is_advance = (dest_rank > source_rank)
                        
                        if is_capture:
                            # Skip captures - they're not part of a pawn storm
                            pass
                        elif not is_advance:
                            # Skip backward moves - they're not part of a pawn storm
                            pass
                        else:
                            side = None
                            if is_kingside_file(dest_file):
                                side = "kingside"
                            elif is_queenside_file(dest_file):
                                side = "queenside"
                            
                            if side:
                                recent_pawn_files = []
                                # Check previous moves in window (exclude current move to avoid double-counting)
                                for j in range(max(0, context.move_index - PAWN_STORM_WINDOW + 1), context.move_index):
                                    check_move = context.moves[j]
                                    if check_move.white_move and len(check_move.white_move) >= 2 and check_move.white_move[0].islower():
                                        if check_move.fen_white and j > 0:
                                            check_board_after = parse_fen(check_move.fen_white)
                                            check_prev_move = context.moves[j - 1]
                                            check_board_before = parse_fen(check_prev_move.fen_black) if check_prev_move.fen_black else None
                                            
                                            if check_board_after and check_board_before:
                                                check_pawns_before = list(check_board_before.pieces(chess.PAWN, chess.WHITE))
                                                check_pawns_after = list(check_board_after.pieces(chess.PAWN, chess.WHITE))
                                                
                                                # Find moved pawn and check if it's a capture
                                                check_moved_pawn = None
                                                check_source_sq = None
                                                for pawn_sq in check_pawns_after:
                                                    if pawn_sq not in check_pawns_before:
                                                        check_moved_pawn = pawn_sq
                                                        break
                                                for pawn_sq in check_pawns_before:
                                                    if pawn_sq not in check_pawns_after:
                                                        check_source_sq = pawn_sq
                                                        break
                                                
                                                # Only count non-capture pawn moves (advances)
                                                if check_moved_pawn is not None and check_source_sq is not None:
                                                    check_source_file = chess.square_file(check_source_sq)
                                                    check_dest_file = chess.square_file(check_moved_pawn)
                                                    check_source_rank = chess.square_rank(check_source_sq)
                                                    check_dest_rank = chess.square_rank(check_moved_pawn)
                                                    check_is_capture = (check_source_file != check_dest_file)
                                                    
                                                    # For white, advancing means moving to higher rank (0-7, where 7 is 8th rank)
                                                    check_is_advance = (check_dest_rank > check_source_rank)
                                                    
                                                    if not check_is_capture and check_is_advance:
                                                        pawn_file = check_dest_file
                                                        if ((side == "kingside" and is_kingside_file(pawn_file)) or
                                                            (side == "queenside" and is_queenside_file(pawn_file))):
                                                            recent_pawn_files.append((check_move.move_number, pawn_file))
                                
                                recent_pawn_files.append((move_num, dest_file))
                            
                            # Check for at least 2 different files (adjacent pawns)
                            files_involved = sorted(set(f for _, f in recent_pawn_files))
                            if len(files_involved) >= 2:
                                for i_file in range(len(files_involved) - 1):
                                    file1 = files_involved[i_file]
                                    file2 = files_involved[i_file + 1]
                                    if are_adjacent_files(file1, file2):
                                        file1_moves = [m for m in recent_pawn_files if m[1] == file1]
                                        file2_moves = [m for m in recent_pawn_files if m[1] == file2]
                                        
                                        if file1_moves and file2_moves:
                                            # Check if the pawns are on similar ranks (coordinated advance)
                                            # Get the current board to check pawn positions
                                            board_after = parse_fen(move.fen_white) if move.fen_white else None
                                            is_coordinated = False
                                            if board_after:
                                                # Find pawns on these files
                                                file1_pawns = [sq for sq in board_after.pieces(chess.PAWN, chess.WHITE) 
                                                               if chess.square_file(sq) == file1]
                                                file2_pawns = [sq for sq in board_after.pieces(chess.PAWN, chess.WHITE) 
                                                               if chess.square_file(sq) == file2]
                                                
                                                # Check if pawns are on similar ranks (within 1 rank for true coordination)
                                                # A pawn storm requires tightly coordinated advances, not just adjacent files
                                                if file1_pawns and file2_pawns:
                                                    file1_ranks = [chess.square_rank(sq) for sq in file1_pawns]
                                                    file2_ranks = [chess.square_rank(sq) for sq in file2_pawns]
                                                    min_rank_diff = min(abs(r1 - r2) for r1 in file1_ranks for r2 in file2_ranks)
                                                    # Require pawns to be on the same rank or adjacent ranks (within 1 rank)
                                                    is_coordinated = (min_rank_diff <= 1)
                                            
                                            if is_coordinated:
                                                # Verify storm is advancing toward opponent: require at least one pawn on rank >=5 (white) or <=2 (black)
                                                # For white, rank >=5 means pawn is in opponent's half (ranks 0-7, where 7 is 8th rank)
                                                # For black, rank <=2 means pawn is in opponent's half
                                                max_rank = max(file1_ranks + file2_ranks) if file1_ranks and file2_ranks else 0
                                                is_advancing_toward_opponent = max_rank >= 5  # White advancing toward black
                                                
                                                if is_advancing_toward_opponent:
                                                    # Attribute the storm to the current move (the one that completes the pattern)
                                                    # not the first move, since a single pawn advance is not a storm
                                                    storm_key = (True, side, move_num)
                                                    
                                                    if storm_key not in pawn_storm_created:
                                                        side_name = "kingside" if side == "kingside" else "queenside"
                                                        highlights.append(GameHighlight(
                                                            move_number=move_num,
                                                            is_white=True,
                                                            move_notation=f"{move_num}. {move.white_move}",
                                                            description=f"White initiated a pawn storm on the {side_name}",
                                                            priority=22,
                                                            rule_type="pawn_storm"
                                                        ))
                                                        pawn_storm_created.add(storm_key)
                                                    break
        
        # Similar for black
        if move.black_move and len(move.black_move) >= 2 and move.black_move[0].islower():
            board_after = parse_fen(move.fen_black)
            if board_after and move.fen_white:
                board_before = parse_fen(move.fen_white)
                
                if board_before:
                    black_pawns_before = list(board_before.pieces(chess.PAWN, chess.BLACK))
                    black_pawns_after = list(board_after.pieces(chess.PAWN, chess.BLACK))
                    
                    moved_pawn_square = None
                    for sq in black_pawns_after:
                        if sq not in black_pawns_before:
                            moved_pawn_square = sq
                            break
                    
                    if moved_pawn_square:
                        dest_file = chess.square_file(moved_pawn_square)
                        dest_rank = chess.square_rank(moved_pawn_square)
                        
                        # Find the source square of the moved pawn
                        source_square = None
                        for sq in black_pawns_before:
                            if sq not in black_pawns_after:
                                source_square = sq
                                break
                        
                        # Check if this is a capture (pawn changed files)
                        is_capture = False
                        source_rank = None
                        if source_square is not None:
                            source_file = chess.square_file(source_square)
                            source_rank = chess.square_rank(source_square)
                            if source_file != dest_file:
                                is_capture = True
                        
                        # Pawn storms are about forward advances, not captures
                        # A capture that changes files is tactical, not part of a storm
                        # Check if this is actually a forward advance
                        is_advance = False
                        if source_rank is not None:
                            # For black, advancing means moving to lower rank (closer to rank 0)
                            is_advance = (dest_rank < source_rank)
                        
                        if is_capture:
                            # Skip captures - they're not part of a pawn storm
                            pass
                        elif not is_advance:
                            # Skip backward moves - they're not part of a pawn storm
                            pass
                        else:
                            side = None
                            if is_kingside_file(dest_file):
                                side = "kingside"
                            elif is_queenside_file(dest_file):
                                side = "queenside"
                            
                            if side:
                                recent_pawn_files = []
                                # Check previous moves in window (exclude current move to avoid double-counting)
                                for j in range(max(0, context.move_index - PAWN_STORM_WINDOW + 1), context.move_index):
                                    check_move = context.moves[j]
                                    if check_move.black_move and len(check_move.black_move) >= 2 and check_move.black_move[0].islower():
                                        if check_move.fen_black and check_move.fen_white:
                                            check_board_after = parse_fen(check_move.fen_black)
                                            check_board_before = parse_fen(check_move.fen_white)
                                            
                                            if check_board_after and check_board_before:
                                                check_pawns_before = list(check_board_before.pieces(chess.PAWN, chess.BLACK))
                                                check_pawns_after = list(check_board_after.pieces(chess.PAWN, chess.BLACK))
                                                
                                                # Find moved pawn and check if it's a capture
                                                check_moved_pawn = None
                                                check_source_sq = None
                                                for pawn_sq in check_pawns_after:
                                                    if pawn_sq not in check_pawns_before:
                                                        check_moved_pawn = pawn_sq
                                                        break
                                                for pawn_sq in check_pawns_before:
                                                    if pawn_sq not in check_pawns_after:
                                                        check_source_sq = pawn_sq
                                                        break
                                                
                                                # Only count non-capture pawn moves (advances)
                                                if check_moved_pawn is not None and check_source_sq is not None:
                                                    check_source_file = chess.square_file(check_source_sq)
                                                    check_dest_file = chess.square_file(check_moved_pawn)
                                                    check_source_rank = chess.square_rank(check_source_sq)
                                                    check_dest_rank = chess.square_rank(check_moved_pawn)
                                                    check_is_capture = (check_source_file != check_dest_file)
                                                    
                                                    # For black, advancing means moving to lower rank (closer to rank 0)
                                                    check_is_advance = (check_dest_rank < check_source_rank)
                                                    
                                                    if not check_is_capture and check_is_advance:
                                                        pawn_file = check_dest_file
                                                        if ((side == "kingside" and is_kingside_file(pawn_file)) or
                                                            (side == "queenside" and is_queenside_file(pawn_file))):
                                                            recent_pawn_files.append((check_move.move_number, pawn_file))
                                
                                recent_pawn_files.append((move_num, dest_file))
                            
                            # Check for at least 2 different files (adjacent pawns)
                            files_involved = sorted(set(f for _, f in recent_pawn_files))
                            if len(files_involved) >= 2:
                                for i_file in range(len(files_involved) - 1):
                                    file1 = files_involved[i_file]
                                    file2 = files_involved[i_file + 1]
                                    if are_adjacent_files(file1, file2):
                                        file1_moves = [m for m in recent_pawn_files if m[1] == file1]
                                        file2_moves = [m for m in recent_pawn_files if m[1] == file2]
                                        
                                        if file1_moves and file2_moves:
                                            # Check if the pawns are on similar ranks (coordinated advance)
                                            # Get the current board to check pawn positions
                                            board_after = parse_fen(move.fen_black) if move.fen_black else None
                                            is_coordinated = False
                                            if board_after:
                                                # Find pawns on these files
                                                file1_pawns = [sq for sq in board_after.pieces(chess.PAWN, chess.BLACK) 
                                                               if chess.square_file(sq) == file1]
                                                file2_pawns = [sq for sq in board_after.pieces(chess.PAWN, chess.BLACK) 
                                                               if chess.square_file(sq) == file2]
                                                
                                                # Check if pawns are on similar ranks (within 1 rank for true coordination)
                                                # A pawn storm requires tightly coordinated advances, not just adjacent files
                                                if file1_pawns and file2_pawns:
                                                    file1_ranks = [chess.square_rank(sq) for sq in file1_pawns]
                                                    file2_ranks = [chess.square_rank(sq) for sq in file2_pawns]
                                                    min_rank_diff = min(abs(r1 - r2) for r1 in file1_ranks for r2 in file2_ranks)
                                                    # Require pawns to be on the same rank or adjacent ranks (within 1 rank)
                                                    is_coordinated = (min_rank_diff <= 1)
                                            
                                            if is_coordinated:
                                                # Verify storm is advancing toward opponent: require at least one pawn on rank <=2 (black)
                                                # For black, rank <=2 means pawn is in opponent's half (ranks 0-7, where 0 is 1st rank)
                                                min_rank = min(file1_ranks + file2_ranks) if file1_ranks and file2_ranks else 7
                                                is_advancing_toward_opponent = min_rank <= 2  # Black advancing toward white
                                                
                                                if is_advancing_toward_opponent:
                                                    # Attribute the storm to the current move (the one that completes the pattern)
                                                    # not the first move, since a single pawn advance is not a storm
                                                    storm_key = (False, side, move_num)
                                                    
                                                    if storm_key not in pawn_storm_created:
                                                        side_name = "kingside" if side == "kingside" else "queenside"
                                                        highlights.append(GameHighlight(
                                                            move_number=move_num,
                                                            is_white=False,
                                                            move_notation=f"{move_num}. ...{move.black_move}",
                                                            description=f"Black initiated a pawn storm on the {side_name}",
                                                            priority=22,
                                                            rule_type="pawn_storm"
                                                        ))
                                                        pawn_storm_created.add(storm_key)
                                                    break
        
        context.shared_state['pawn_storm_created'] = pawn_storm_created
        
        return highlights

