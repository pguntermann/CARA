"""Service for aggregating player statistics across multiple games."""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import Counter

from app.models.database_model import GameData, DatabaseModel
from app.models.moveslist_model import MoveData
from app.services.game_summary_service import GameSummary, PlayerStatistics, PhaseStatistics, GameSummaryService
from app.controllers.game_controller import GameController


@dataclass
class AggregatedPlayerStats:
    """Aggregated statistics for a player across multiple games."""
    total_games: int
    analyzed_games: int
    wins: int
    draws: int
    losses: int
    win_rate: float
    player_stats: PlayerStatistics
    opening_stats: PhaseStatistics
    middlegame_stats: PhaseStatistics
    endgame_stats: PhaseStatistics
    top_openings: List[Tuple[str, Optional[str], int]]  # List of (ECO, opening_name, count) tuples
    worst_accuracy_openings: List[Tuple[str, Optional[str], float, int]]  # List of (ECO, opening_name, avg_cpl, count) tuples
    best_accuracy_openings: List[Tuple[str, Optional[str], float, int]]  # List of (ECO, opening_name, avg_cpl, count) tuples


class PlayerStatsService:
    """Service for aggregating player statistics across games."""
    
    def __init__(self, config: Dict[str, Any], game_controller: Optional[GameController] = None):
        """Initialize the player stats service.
        
        Args:
            config: Configuration dictionary.
            game_controller: Optional GameController for extracting moves from games.
        """
        self.config = config
        self.game_controller = game_controller
        self.summary_service = GameSummaryService(config)
    
    def get_player_games(self, player_name: str, databases: List[DatabaseModel], 
                        only_analyzed: bool = True) -> Tuple[List[GameData], int]:
        """Get all games for a player from the given databases.
        
        Args:
            player_name: Player name to search for.
            databases: List of DatabaseModel instances to search.
            only_analyzed: If True, only return analyzed games.
            
        Returns:
            Tuple of (list of GameData, total_count_including_unanalyzed).
        """
        player_games: List[GameData] = []
        total_count = 0
        
        for database in databases:
            games = database.get_all_games()
            for game in games:
                # Check if player is white or black
                is_player = False
                if game.white and game.white.strip() == player_name:
                    is_player = True
                elif game.black and game.black.strip() == player_name:
                    is_player = True
                
                if is_player:
                    total_count += 1
                    if not only_analyzed or game.analyzed:
                        player_games.append(game)
        
        return (player_games, total_count)
    
    def aggregate_player_statistics(self, player_name: str, games: List[GameData],
                                   game_controller: Optional[GameController] = None) -> Optional[AggregatedPlayerStats]:
        """Aggregate statistics for a player across multiple games.
        
        Args:
            player_name: Player name.
            games: List of GameData instances for this player.
            game_controller: Optional GameController for extracting moves.
            
        Returns:
            AggregatedPlayerStats instance, or None if no analyzed games found.
        """
        if not games:
            return None
        
        # Use provided controller or instance controller
        controller = game_controller or self.game_controller
        if not controller:
            return None
        
        # Separate analyzed and unanalyzed games
        analyzed_games = [g for g in games if g.analyzed]
        if not analyzed_games:
            return None
        
        # Count results
        wins = 0
        draws = 0
        losses = 0
        
        # Collect all moves for aggregation (needed for overall aggregated stats)
        # Note: We need to track which color the player was in each game
        # For aggregation, we'll use the majority color to determine which fields to use
        all_moves_white: List[MoveData] = []
        all_moves_black: List[MoveData] = []
        
        white_games_count = 0
        black_games_count = 0
        
        for game in analyzed_games:
            # Count results
            if (game.white == player_name and game.result == "1-0") or \
               (game.black == player_name and game.result == "0-1"):
                wins += 1
            elif game.result == "1/2-1/2":
                draws += 1
            else:
                losses += 1
            
            # Extract moves
            moves = controller.extract_moves_from_game(game)
            if not moves:
                continue
            
            # Determine if player is white or black in this game
            is_white = (game.white == player_name)
            if is_white:
                white_games_count += 1
            else:
                black_games_count += 1
            
            # Collect moves for this player (filter by color) - needed for aggregated overall stats
            for move in moves:
                if is_white and move.white_move:
                    all_moves_white.append(move)
                elif not is_white and move.black_move:
                    all_moves_black.append(move)
        
        # Determine which color to use for aggregation (majority)
        # If player played both colors, we'll aggregate white moves separately
        # For now, use the color they played most often
        use_white = white_games_count >= black_games_count
        
        if use_white:
            all_moves = all_moves_white
            cpl_field = 'cpl_white'
            assess_field = 'assess_white'
        else:
            all_moves = all_moves_black
            cpl_field = 'cpl_black'
            assess_field = 'assess_black'
        
        if not all_moves:
            return None
        
        # Calculate per-game statistics, then average ELO, accuracy, and phase accuracies
        # This ensures formulas work correctly with has_won/has_drawn per game
        elo_values = []
        accuracy_values = []
        opening_accuracy_values = []
        middlegame_accuracy_values = []
        endgame_accuracy_values = []
        
        # Also collect phase statistics for aggregation (moves, CPL, move counts, etc.)
        opening_moves_total = 0
        middlegame_moves_total = 0
        endgame_moves_total = 0
        opening_cpl_sum = 0.0
        middlegame_cpl_sum = 0.0
        endgame_cpl_sum = 0.0
        opening_cpl_count = 0
        middlegame_cpl_count = 0
        endgame_cpl_count = 0
        
        # Aggregate move classification counts for each phase
        opening_book_moves = 0
        opening_brilliant_moves = 0
        opening_best_moves = 0
        opening_good_moves = 0
        opening_inaccuracies = 0
        opening_mistakes = 0
        opening_misses = 0
        opening_blunders = 0
        
        middlegame_book_moves = 0
        middlegame_brilliant_moves = 0
        middlegame_best_moves = 0
        middlegame_good_moves = 0
        middlegame_inaccuracies = 0
        middlegame_mistakes = 0
        middlegame_misses = 0
        middlegame_blunders = 0
        
        endgame_book_moves = 0
        endgame_brilliant_moves = 0
        endgame_best_moves = 0
        endgame_good_moves = 0
        endgame_inaccuracies = 0
        endgame_mistakes = 0
        endgame_misses = 0
        endgame_blunders = 0
        
        for game in analyzed_games:
            moves = controller.extract_moves_from_game(game)
            if not moves:
                continue
            
            is_white_game = (game.white == player_name)
            game_result = game.result
            
            # Calculate complete game summary for this game
            game_summary = self.summary_service.calculate_summary(moves, len(moves), game_result)
            if not game_summary:
                continue
            
            # Get player statistics for this game
            if is_white_game:
                game_stats = game_summary.white_stats
                game_opening = game_summary.white_opening
                game_middlegame = game_summary.white_middlegame
                game_endgame = game_summary.white_endgame
            else:
                game_stats = game_summary.black_stats
                game_opening = game_summary.black_opening
                game_middlegame = game_summary.black_middlegame
                game_endgame = game_summary.black_endgame
            
            # Collect per-game values for averaging
            elo_values.append(game_stats.estimated_elo)
            accuracy_values.append(game_stats.accuracy)
            opening_accuracy_values.append(game_opening.accuracy)
            middlegame_accuracy_values.append(game_middlegame.accuracy)
            endgame_accuracy_values.append(game_endgame.accuracy)
            
            # Collect phase statistics for aggregation (moves, CPL, move counts, etc.)
            opening_moves_total += game_opening.moves
            middlegame_moves_total += game_middlegame.moves
            endgame_moves_total += game_endgame.moves
            
            # Accumulate CPL for weighted average (weighted by number of moves in phase)
            if game_opening.moves > 0:
                opening_cpl_sum += game_opening.average_cpl * game_opening.moves
                opening_cpl_count += game_opening.moves
            if game_middlegame.moves > 0:
                middlegame_cpl_sum += game_middlegame.average_cpl * game_middlegame.moves
                middlegame_cpl_count += game_middlegame.moves
            if game_endgame.moves > 0:
                endgame_cpl_sum += game_endgame.average_cpl * game_endgame.moves
                endgame_cpl_count += game_endgame.moves
            
            # Aggregate move classification counts for each phase
            opening_book_moves += game_opening.book_moves
            opening_brilliant_moves += game_opening.brilliant_moves
            opening_best_moves += game_opening.best_moves
            opening_good_moves += game_opening.good_moves
            opening_inaccuracies += game_opening.inaccuracies
            opening_mistakes += game_opening.mistakes
            opening_misses += game_opening.misses
            opening_blunders += game_opening.blunders
            
            middlegame_book_moves += game_middlegame.book_moves
            middlegame_brilliant_moves += game_middlegame.brilliant_moves
            middlegame_best_moves += game_middlegame.best_moves
            middlegame_good_moves += game_middlegame.good_moves
            middlegame_inaccuracies += game_middlegame.inaccuracies
            middlegame_mistakes += game_middlegame.mistakes
            middlegame_misses += game_middlegame.misses
            middlegame_blunders += game_middlegame.blunders
            
            endgame_book_moves += game_endgame.book_moves
            endgame_brilliant_moves += game_endgame.brilliant_moves
            endgame_best_moves += game_endgame.best_moves
            endgame_good_moves += game_endgame.good_moves
            endgame_inaccuracies += game_endgame.inaccuracies
            endgame_mistakes += game_endgame.mistakes
            endgame_misses += game_endgame.misses
            endgame_blunders += game_endgame.blunders
        
        # Average the results
        if elo_values:
            averaged_elo = sum(elo_values) / len(elo_values)
            averaged_accuracy = sum(accuracy_values) / len(accuracy_values)
        else:
            averaged_elo = 0
            averaged_accuracy = 0.0
        
        # Average phase accuracies
        if opening_accuracy_values:
            averaged_opening_accuracy = sum(opening_accuracy_values) / len(opening_accuracy_values)
        else:
            averaged_opening_accuracy = 0.0
        
        if middlegame_accuracy_values:
            averaged_middlegame_accuracy = sum(middlegame_accuracy_values) / len(middlegame_accuracy_values)
        else:
            averaged_middlegame_accuracy = 0.0
        
        if endgame_accuracy_values:
            averaged_endgame_accuracy = sum(endgame_accuracy_values) / len(endgame_accuracy_values)
        else:
            averaged_endgame_accuracy = 0.0
        
        # Calculate weighted average CPL for each phase
        average_cpl_opening = (opening_cpl_sum / opening_cpl_count) if opening_cpl_count > 0 else 0.0
        average_cpl_middlegame = (middlegame_cpl_sum / middlegame_cpl_count) if middlegame_cpl_count > 0 else 0.0
        average_cpl_endgame = (endgame_cpl_sum / endgame_cpl_count) if endgame_cpl_count > 0 else 0.0
        
        # Still calculate aggregated stats for other metrics (CPL, move counts, etc.)
        # But we'll replace ELO and accuracy with averaged values
        aggregated_stats = self.summary_service._calculate_player_statistics(all_moves, use_white, game_result=None)
        
        # Override with averaged values
        aggregated_stats.estimated_elo = int(averaged_elo)
        aggregated_stats.accuracy = averaged_accuracy
        
        # Create phase statistics with averaged accuracy values
        # Use aggregated move counts and CPL from per-game phase statistics
        opening_stats = PhaseStatistics(
            moves=opening_moves_total,
            average_cpl=average_cpl_opening,
            accuracy=averaged_opening_accuracy,
            book_moves=opening_book_moves,
            brilliant_moves=opening_brilliant_moves,
            best_moves=opening_best_moves,
            good_moves=opening_good_moves,
            inaccuracies=opening_inaccuracies,
            mistakes=opening_mistakes,
            misses=opening_misses,
            blunders=opening_blunders
        )
        
        middlegame_stats = PhaseStatistics(
            moves=middlegame_moves_total,
            average_cpl=average_cpl_middlegame,
            accuracy=averaged_middlegame_accuracy,
            book_moves=middlegame_book_moves,
            brilliant_moves=middlegame_brilliant_moves,
            best_moves=middlegame_best_moves,
            good_moves=middlegame_good_moves,
            inaccuracies=middlegame_inaccuracies,
            mistakes=middlegame_mistakes,
            misses=middlegame_misses,
            blunders=middlegame_blunders
        )
        
        endgame_stats = PhaseStatistics(
            moves=endgame_moves_total,
            average_cpl=average_cpl_endgame,
            accuracy=averaged_endgame_accuracy,
            book_moves=endgame_book_moves,
            brilliant_moves=endgame_brilliant_moves,
            best_moves=endgame_best_moves,
            good_moves=endgame_good_moves,
            inaccuracies=endgame_inaccuracies,
            mistakes=endgame_mistakes,
            misses=endgame_misses,
            blunders=endgame_blunders
        )
        
        # Calculate win rate
        total_games = len(analyzed_games)
        win_rate = (wins / total_games * 100) if total_games > 0 else 0.0
        
        # Track opening usage and CPL - get ECO and opening name from last move with non-"*" opening name
        opening_counter = Counter()
        opening_cpl_data: Dict[Tuple[str, Optional[str]], List[float]] = {}  # Track CPL values per opening (per-game averages)
        repeat_indicator = self.config.get('resources', {}).get('opening_repeat_indicator', '*')
        
        for game in analyzed_games:
            moves = controller.extract_moves_from_game(game)
            if not moves:
                continue
            
            # Determine if player is white or black in this game
            is_white = (game.white == player_name)
            game_cpl_field = 'cpl_white' if is_white else 'cpl_black'
            
            # Determine opening phase end using the same method as GameSummaryService (per game)
            total_moves = len(moves)
            opening_end, _ = self.summary_service._determine_phase_boundaries(moves, total_moves)
            
            # Find the last move with a non-"*" opening name to identify the opening (ECO and name)
            eco = "Unknown"
            opening_name = None
            
            for move in reversed(moves):
                if move.opening_name and move.opening_name != repeat_indicator:
                    eco = move.eco if move.eco else "Unknown"
                    opening_name = move.opening_name
                    break
            
            # If no move with opening name found, fall back to game header ECO
            if eco == "Unknown" and not opening_name:
                eco = game.eco if game.eco else "Unknown"
            
            # Count this opening
            opening_key = (eco, opening_name)
            opening_counter[opening_key] += 1
            
            # Collect CPL values for this opening (from all moves up to and including opening_end)
            if opening_key not in opening_cpl_data:
                opening_cpl_data[opening_key] = []
            
            # Collect CPL from all opening phase moves for this game (up to and including opening_end)
            game_opening_cpls = []
            for move in moves:
                move_num = move.move_number
                if move_num <= opening_end:
                    if is_white and move.white_move:
                        cpl_str = getattr(move, game_cpl_field, "")
                        if cpl_str:
                            try:
                                cpl = float(cpl_str)
                                game_opening_cpls.append(cpl)
                            except (ValueError, TypeError):
                                pass
                    elif not is_white and move.black_move:
                        cpl_str = getattr(move, game_cpl_field, "")
                        if cpl_str:
                            try:
                                cpl = float(cpl_str)
                                game_opening_cpls.append(cpl)
                            except (ValueError, TypeError):
                                pass
            
            # Calculate average CPL for this game's opening phase and store it
            if game_opening_cpls:
                # Cap CPL at 500 for average calculation (same as in game_summary_service)
                CPL_CAP_FOR_AVERAGE = 500.0
                capped_cpl_values = [min(cpl, CPL_CAP_FOR_AVERAGE) for cpl in game_opening_cpls]
                game_avg_cpl = sum(capped_cpl_values) / len(capped_cpl_values)
                opening_cpl_data[opening_key].append(game_avg_cpl)
        
        # Get top 3 most played openings
        top_openings = opening_counter.most_common(3)
        top_openings_list = [(eco, opening_name, count) for (eco, opening_name), count in top_openings]
        
        # Calculate average CPL for each opening across all games
        # opening_cpl_data now contains per-game averages, so we just average those
        opening_avg_cpl: List[Tuple[Tuple[str, Optional[str]], float, int]] = []
        for opening_key, game_avg_cpls in opening_cpl_data.items():
            if game_avg_cpls:
                # Average the per-game averages to get overall average CPL for this opening
                overall_avg_cpl = sum(game_avg_cpls) / len(game_avg_cpls)
                count = opening_counter[opening_key]
                opening_avg_cpl.append((opening_key, overall_avg_cpl, count))
        
        # Sort by average CPL (worst = highest CPL, best = lowest CPL)
        # Exclude openings with 0 CPL (perfect play) from worst accuracy list
        opening_avg_cpl.sort(key=lambda x: x[1], reverse=True)  # Highest CPL first (worst)
        worst_openings = [opening for opening in opening_avg_cpl if opening[1] > 0.0][:3]  # Top 3 worst, excluding 0 CPL
        worst_openings_list = [(eco, opening_name, avg_cpl, count) for (eco, opening_name), avg_cpl, count in worst_openings]
        
        opening_avg_cpl.sort(key=lambda x: x[1])  # Lowest CPL first (best)
        best_openings = opening_avg_cpl[:3]  # Top 3 best
        best_openings_list = [(eco, opening_name, avg_cpl, count) for (eco, opening_name), avg_cpl, count in best_openings]
        
        return AggregatedPlayerStats(
            total_games=total_games,
            analyzed_games=len(analyzed_games),
            wins=wins,
            draws=draws,
            losses=losses,
            win_rate=win_rate,
            player_stats=aggregated_stats,
            opening_stats=opening_stats,
            middlegame_stats=middlegame_stats,
            endgame_stats=endgame_stats,
            top_openings=top_openings_list,
            worst_accuracy_openings=worst_openings_list,
            best_accuracy_openings=best_openings_list
        )

