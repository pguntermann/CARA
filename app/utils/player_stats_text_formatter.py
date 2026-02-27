"""Text formatter for player statistics view."""

from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.player_stats_service import AggregatedPlayerStats
    from app.services.error_pattern_service import ErrorPattern


class PlayerStatsTextFormatter:
    """Formatter for converting player statistics to text format."""

    @staticmethod
    def _format_top_games(
        best_count: int,
        best_min_acc: Optional[float],
        best_max_acc: Optional[float],
        worst_count: int,
        worst_min_acc: Optional[float],
        worst_max_acc: Optional[float],
    ) -> List[str]:
        """Format Games by Performance (best/worst) section."""
        lines = []
        lines.append("Top Games")
        lines.append("---------")
        lines.append("")
        if best_min_acc is not None and best_max_acc is not None and best_count > 0:
            lines.append(f"Best Games (lowest CPL, Accuracy {best_min_acc:.1f}–{best_max_acc:.1f}%): {best_count} game(s)")
        else:
            lines.append(f"Best Games (lowest CPL): {best_count} game(s)")
        if worst_min_acc is not None and worst_max_acc is not None and worst_count > 0:
            lines.append(f"Worst Games (highest CPL, Accuracy {worst_min_acc:.1f}–{worst_max_acc:.1f}%): {worst_count} game(s)")
        else:
            lines.append(f"Worst Games (highest CPL): {worst_count} game(s)")
        return lines
    
    @staticmethod
    def format_full_stats(
        stats: "AggregatedPlayerStats",
        patterns: List["ErrorPattern"],
        player_name: str,
        *,
        top_games_summary: Optional[Tuple[int, Optional[float], Optional[float], int, Optional[float], Optional[float]]] = None,
    ) -> str:
        """Format the full player statistics as text.
        
        Args:
            stats: AggregatedPlayerStats instance.
            patterns: List of ErrorPattern instances.
            player_name: Name of the player.
            top_games_summary: Optional (best_count, best_min_acc, best_max_acc, worst_count, worst_min_acc, worst_max_acc).
            
        Returns:
            Formatted text string for the full stats.
        """
        lines = []
        lines.append(f"Player Statistics: {player_name}")
        lines.append("=" * (len(f"Player Statistics: {player_name}")))
        lines.append("")
        
        # Add all sections
        lines.extend(PlayerStatsTextFormatter._format_overview(stats))
        lines.append("")
        dist_lines = PlayerStatsTextFormatter._format_accuracy_distribution(stats)
        if dist_lines:
            lines.extend(dist_lines)
            lines.append("")
        lines.extend(PlayerStatsTextFormatter._format_move_accuracy(stats))
        lines.append("")
        lines.extend(PlayerStatsTextFormatter._format_phase_performance(stats))
        lines.append("")
        
        if stats.top_openings or stats.worst_accuracy_openings or stats.best_accuracy_openings:
            lines.extend(PlayerStatsTextFormatter._format_openings(stats))
            lines.append("")
        
        if top_games_summary is not None:
            lines.extend(PlayerStatsTextFormatter._format_top_games(*top_games_summary))
            lines.append("")
        
        if patterns:
            lines.extend(PlayerStatsTextFormatter._format_error_patterns(patterns))
        
        return "\n".join(lines)
    
    @staticmethod
    def format_section(
        stats: "AggregatedPlayerStats",
        patterns: List["ErrorPattern"],
        section_name: str,
        player_name: str,
        *,
        top_games_summary: Optional[Tuple[int, Optional[float], Optional[float], int, Optional[float], Optional[float]]] = None,
    ) -> str:
        """Format a specific section as text.
        
        Args:
            stats: AggregatedPlayerStats instance.
            patterns: List of ErrorPattern instances.
            section_name: Name of the section to format.
            player_name: Name of the player.
            top_games_summary: Required for "Top Games" section: (best_count, best_min_acc, best_max_acc, worst_count, worst_min_acc, worst_max_acc).
            
        Returns:
            Formatted text string for the section.
        """
        lines = []
        lines.append(section_name)
        lines.append("=" * len(section_name))
        
        if section_name == "Overview":
            section_lines = PlayerStatsTextFormatter._format_overview(stats)
            lines.extend(section_lines[2:])  # Skip "Overview" and "-------"
        elif section_name == "Accuracy Distribution":
            section_lines = PlayerStatsTextFormatter._format_accuracy_distribution(stats)
            if section_lines:
                lines.extend(section_lines[2:])
        elif section_name == "Move Accuracy":
            section_lines = PlayerStatsTextFormatter._format_move_accuracy(stats)
            lines.extend(section_lines[2:])
        elif section_name == "Performance by Phase":
            section_lines = PlayerStatsTextFormatter._format_phase_performance(stats)
            lines.extend(section_lines[2:])
        elif section_name == "Openings":
            section_lines = PlayerStatsTextFormatter._format_openings(stats)
            lines.extend(section_lines[2:])
        elif section_name == "Top Games":
            if top_games_summary is not None:
                section_lines = PlayerStatsTextFormatter._format_top_games(*top_games_summary)
                lines.extend(section_lines[2:])  # Skip "Top Games" and "---------"
        elif section_name == "Error Patterns":
            section_lines = PlayerStatsTextFormatter._format_error_patterns(patterns)
            lines.extend(section_lines[2:])
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_overview(stats: "AggregatedPlayerStats") -> List[str]:
        """Format overview statistics.
        
        Args:
            stats: AggregatedPlayerStats instance.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Overview")
        lines.append("-------")
        lines.append("")
        
        lines.append(f"Total Games: {stats.total_games}")
        lines.append(f"Win Rate: {stats.win_rate:.1f}%")
        lines.append(f"Record: {stats.wins}-{stats.draws}-{stats.losses}")
        
        accuracy = stats.player_stats.accuracy if stats.player_stats.accuracy is not None else 0.0
        # Include per-game min/max accuracy if available
        min_acc = getattr(stats, "min_accuracy", None)
        max_acc = getattr(stats, "max_accuracy", None)
        if min_acc is not None and max_acc is not None and stats.analyzed_games > 1:
            lines.append(f"Average Accuracy: {accuracy:.1f}% (Min: {min_acc:.1f}%, Max: {max_acc:.1f}%)")
        else:
            lines.append(f"Average Accuracy: {accuracy:.1f}%")
        
        est_elo = stats.player_stats.estimated_elo if stats.player_stats.estimated_elo is not None else 0
        lines.append(f"Estimated Elo: {est_elo}")
        
        avg_cpl = stats.player_stats.average_cpl if stats.player_stats.average_cpl is not None else 0.0
        # Include per-game min/max ACPL if available
        min_acpl = getattr(stats, "min_acpl", None)
        max_acpl = getattr(stats, "max_acpl", None)
        if min_acpl is not None and max_acpl is not None and stats.analyzed_games > 1:
            lines.append(f"Average CPL: {avg_cpl:.1f} (Min: {min_acpl:.1f}, Max: {max_acpl:.1f})")
        else:
            lines.append(f"Average CPL: {avg_cpl:.1f}")
        
        top3_move_pct = stats.player_stats.top3_move_percentage if stats.player_stats.top3_move_percentage is not None else 0.0
        lines.append(f"Top 3 Move %: {top3_move_pct:.1f}%")
        
        return lines

    @staticmethod
    def _format_accuracy_distribution(stats: "AggregatedPlayerStats") -> List[str]:
        """Format accuracy distribution based on per-game accuracy samples.

        Args:
            stats: AggregatedPlayerStats instance.

        Returns:
            List of formatted lines, or empty list if not enough data.
        """
        values = getattr(stats, "accuracy_values", None) or []
        # Require at least 2 games to make a distribution meaningful
        if len(values) < 2:
            return []

        lines: List[str] = []
        lines.append("Accuracy Distribution")
        lines.append("---------------------")
        lines.append("")

        # Clamp values to [0, 100] and use a dynamic range based on data
        clamped = [max(0.0, min(100.0, v)) for v in values]
        data_min = min(clamped)
        data_max = max(clamped)
        margin = 2.5
        low = max(0.0, data_min - margin)
        high = min(100.0, data_max + margin)
        if high <= low:
            high = min(100.0, low + 5.0)

        bin_count = 10
        bin_size = (high - low) / float(bin_count)
        bins = [0] * bin_count

        for v in clamped:
            idx = int((v - low) // bin_size) if bin_size > 0 else 0
            if idx >= bin_count:
                idx = bin_count - 1
            bins[idx] += 1

        # Emit only non-empty bins, in ascending order
        for i, count in enumerate(bins):
            if count <= 0:
                continue
            start = low + i * bin_size
            end = start + bin_size
            # Use inclusive upper bound 'high' for the last bin
            if i == bin_count - 1:
                label = f"{start:.1f}–{high:.1f}%"
            else:
                label = f"{start:.1f}–{end:.1f}%"
            game_word = "game" if count == 1 else "games"
            lines.append(f"{label}: {count} {game_word}")

        return lines
    
    @staticmethod
    def _format_move_accuracy(stats: "AggregatedPlayerStats") -> List[str]:
        """Format move accuracy statistics.
        
        Args:
            stats: AggregatedPlayerStats instance.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Move Accuracy")
        lines.append("-------------")
        lines.append("")
        
        player_stats = stats.player_stats
        total_moves = player_stats.total_moves if player_stats.total_moves else 0
        
        if total_moves > 0:
            book_moves = player_stats.book_moves if player_stats.book_moves else 0
            brilliant_moves = player_stats.brilliant_moves if player_stats.brilliant_moves else 0
            best_moves = player_stats.best_moves if player_stats.best_moves else 0
            good_moves = player_stats.good_moves if player_stats.good_moves else 0
            inaccuracies = player_stats.inaccuracies if player_stats.inaccuracies else 0
            mistakes = player_stats.mistakes if player_stats.mistakes else 0
            misses = player_stats.misses if player_stats.misses else 0
            blunders = player_stats.blunders if player_stats.blunders else 0
            
            book_pct = (book_moves / total_moves * 100) if book_moves else 0.0
            brilliant_pct = (brilliant_moves / total_moves * 100) if brilliant_moves else 0.0
            best_pct = (best_moves / total_moves * 100) if best_moves else 0.0
            good_pct = (good_moves / total_moves * 100) if good_moves else 0.0
            inaccuracy_pct = (inaccuracies / total_moves * 100) if inaccuracies else 0.0
            mistake_pct = (mistakes / total_moves * 100) if mistakes else 0.0
            miss_pct = (misses / total_moves * 100) if misses else 0.0
            blunder_pct = (blunders / total_moves * 100) if blunders else 0.0
            
            lines.append(f"Book Move: {book_pct:.1f}%")
            lines.append(f"Brilliant: {brilliant_pct:.1f}%")
            lines.append(f"Best Move: {best_pct:.1f}%")
            lines.append(f"Good Move: {good_pct:.1f}%")
            lines.append(f"Inaccuracy: {inaccuracy_pct:.1f}%")
            lines.append(f"Mistake: {mistake_pct:.1f}%")
            lines.append(f"Miss: {miss_pct:.1f}%")
            lines.append(f"Blunder: {blunder_pct:.1f}%")
        
        return lines
    
    @staticmethod
    def _format_phase_performance(stats: "AggregatedPlayerStats") -> List[str]:
        """Format phase performance statistics.
        
        Args:
            stats: AggregatedPlayerStats instance.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Performance by Phase")
        lines.append("-------------------")
        lines.append("")
        
        lines.append("Phase          Avg CPL")
        lines.append("Opening        {:.1f}".format(stats.opening_stats.average_cpl))
        lines.append("Middlegame     {:.1f}".format(stats.middlegame_stats.average_cpl))
        lines.append("Endgame        {:.1f}".format(stats.endgame_stats.average_cpl))
        
        return lines
    
    @staticmethod
    def _format_openings(stats: "AggregatedPlayerStats") -> List[str]:
        """Format openings statistics.
        
        Args:
            stats: AggregatedPlayerStats instance.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Openings")
        lines.append("--------")
        lines.append("")
        
        # Most Played Openings
        if stats.top_openings:
            lines.append("Most Played:")
            for eco, opening_name, count in stats.top_openings:
                if opening_name and eco != "Unknown":
                    lines.append(f"  {eco} ({opening_name}): ({count} games)")
                elif eco != "Unknown":
                    lines.append(f"  {eco}: ({count} games)")
                else:
                    lines.append(f"  Unknown: ({count} games)")
            lines.append("")
        
        # Worst Accuracy Openings
        if stats.worst_accuracy_openings:
            lines.append("Worst Accuracy:")
            for eco, opening_name, avg_cpl, count in stats.worst_accuracy_openings:
                if opening_name and eco != "Unknown":
                    lines.append(f"  {eco} ({opening_name}): Avg CPL {avg_cpl:.1f} ({count} games)")
                elif eco != "Unknown":
                    lines.append(f"  {eco}: Avg CPL {avg_cpl:.1f} ({count} games)")
                else:
                    lines.append(f"  Unknown: Avg CPL {avg_cpl:.1f} ({count} games)")
            lines.append("")
        
        # Best Accuracy Openings
        if stats.best_accuracy_openings:
            lines.append("Best Accuracy:")
            for eco, opening_name, avg_cpl, count in stats.best_accuracy_openings:
                if opening_name and eco != "Unknown":
                    lines.append(f"  {eco} ({opening_name}): Avg CPL {avg_cpl:.1f} ({count} games)")
                elif eco != "Unknown":
                    lines.append(f"  {eco}: Avg CPL {avg_cpl:.1f} ({count} games)")
                else:
                    lines.append(f"  Unknown: Avg CPL {avg_cpl:.1f} ({count} games)")
        
        return lines
    
    @staticmethod
    def _format_error_patterns(patterns: List["ErrorPattern"]) -> List[str]:
        """Format error patterns.
        
        Args:
            patterns: List of ErrorPattern instances.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Error Patterns")
        lines.append("--------------")
        lines.append("")
        
        for pattern in patterns:
            lines.append(f"{pattern.description}")
            lines.append(f"  Frequency: {pattern.frequency} ({pattern.percentage:.1f}%)")
            lines.append("")
        
        return lines

