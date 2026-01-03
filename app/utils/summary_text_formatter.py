"""Text formatter for game summary sections.

This module provides utilities to format game summary data as plain text,
matching exactly what is displayed in the UI sections.
"""

from typing import List, Optional
from app.services.game_summary_service import (
    GameSummary, PlayerStatistics, PhaseStatistics, CriticalMove, GameHighlight
)


class SummaryTextFormatter:
    """Formats game summary data as plain text matching the UI display."""
    
    @staticmethod
    def format_key_statistics(summary: GameSummary, white_name: str, black_name: str) -> List[str]:
        """Format key statistics section matching the UI display.
        
        Args:
            summary: GameSummary instance.
            white_name: White player name.
            black_name: Black player name.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Key Statistics")
        lines.append("-" * 14)
        
        if summary.white_stats:
            lines.append(f"\n{white_name} (White):")
            stats = summary.white_stats
            avg_cpl = stats.average_cpl if stats.average_cpl is not None else 0.0
            accuracy = stats.accuracy if stats.accuracy is not None else 0.0
            est_elo = stats.estimated_elo if stats.estimated_elo is not None else 0
            total_moves = stats.total_moves if stats.total_moves is not None else 0
            best_move_pct = stats.best_move_percentage if stats.best_move_percentage is not None else 0.0
            top3_move_pct = stats.top3_move_percentage if stats.top3_move_percentage is not None else 0.0
            blunder_rate = stats.blunder_rate if stats.blunder_rate is not None else 0.0
            
            lines.append(f"  Average CPL: {avg_cpl:.1f}")
            lines.append(f"  Accuracy: {accuracy:.1f}%")
            lines.append(f"  Est. Elo: {est_elo}")
            lines.append(f"  Total Moves: {total_moves}")
            lines.append(f"  Best Move %: {best_move_pct:.1f}%")
            lines.append(f"  Top3-Move Accuracy: {top3_move_pct:.1f}%")
            lines.append(f"  Blunder Rate: {blunder_rate:.1f}%")
        
        if summary.black_stats:
            lines.append(f"\n{black_name} (Black):")
            stats = summary.black_stats
            avg_cpl = stats.average_cpl if stats.average_cpl is not None else 0.0
            accuracy = stats.accuracy if stats.accuracy is not None else 0.0
            est_elo = stats.estimated_elo if stats.estimated_elo is not None else 0
            total_moves = stats.total_moves if stats.total_moves is not None else 0
            best_move_pct = stats.best_move_percentage if stats.best_move_percentage is not None else 0.0
            top3_move_pct = stats.top3_move_percentage if stats.top3_move_percentage is not None else 0.0
            blunder_rate = stats.blunder_rate if stats.blunder_rate is not None else 0.0
            
            lines.append(f"  Average CPL: {avg_cpl:.1f}")
            lines.append(f"  Accuracy: {accuracy:.1f}%")
            lines.append(f"  Est. Elo: {est_elo}")
            lines.append(f"  Total Moves: {total_moves}")
            lines.append(f"  Best Move %: {best_move_pct:.1f}%")
            lines.append(f"  Top3-Move Accuracy: {top3_move_pct:.1f}%")
            lines.append(f"  Blunder Rate: {blunder_rate:.1f}%")
        
        return lines
    
    @staticmethod
    def format_move_classification(summary: GameSummary, white_name: str, black_name: str) -> List[str]:
        """Format move classification section matching the UI display.
        
        Args:
            summary: GameSummary instance.
            white_name: White player name.
            black_name: Black player name.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Move Classification")
        lines.append("-" * 20)
        
        if summary.white_stats:
            lines.append(f"\n{white_name} (White):")
            stats = summary.white_stats
            lines.append(f"  Book Move: {stats.book_moves or 0}")
            lines.append(f"  Brilliant: {stats.brilliant_moves or 0}")
            lines.append(f"  Best Move: {stats.best_moves or 0}")
            lines.append(f"  Good Move: {stats.good_moves or 0}")
            lines.append(f"  Inaccuracy: {stats.inaccuracies or 0}")
            lines.append(f"  Mistake: {stats.mistakes or 0}")
            lines.append(f"  Miss: {stats.misses or 0}")
            lines.append(f"  Blunder: {stats.blunders or 0}")
        
        if summary.black_stats:
            lines.append(f"\n{black_name} (Black):")
            stats = summary.black_stats
            lines.append(f"  Book Move: {stats.book_moves or 0}")
            lines.append(f"  Brilliant: {stats.brilliant_moves or 0}")
            lines.append(f"  Best Move: {stats.best_moves or 0}")
            lines.append(f"  Good Move: {stats.good_moves or 0}")
            lines.append(f"  Inaccuracy: {stats.inaccuracies or 0}")
            lines.append(f"  Mistake: {stats.mistakes or 0}")
            lines.append(f"  Miss: {stats.misses or 0}")
            lines.append(f"  Blunder: {stats.blunders or 0}")
        
        return lines
    
    @staticmethod
    def format_phase_analysis(summary: GameSummary, white_name: str, black_name: str) -> List[str]:
        """Format phase analysis section matching the UI display.
        
        Args:
            summary: GameSummary instance.
            white_name: White player name.
            black_name: Black player name.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Phase Analysis")
        lines.append("-" * 15)
        
        if summary.opening_end > 0:
            lines.append(f"\nOpening ends at move {summary.opening_end}")
        if summary.middlegame_end > 0:
            lines.append(f"Middlegame ends at move {summary.middlegame_end}")
        if summary.endgame_type:
            lines.append(f"Endgame type: {summary.endgame_type}")
        
        if summary.white_opening:
            lines.append(f"\n{white_name} (White):")
            lines.extend(SummaryTextFormatter._format_player_phases(
                summary.white_opening, summary.white_middlegame, summary.white_endgame,
                summary.opening_end, summary.middlegame_end, summary.endgame_type
            ))
        
        if summary.black_opening:
            lines.append(f"\n{black_name} (Black):")
            lines.extend(SummaryTextFormatter._format_player_phases(
                summary.black_opening, summary.black_middlegame, summary.black_endgame,
                summary.opening_end, summary.middlegame_end, summary.endgame_type
            ))
        
        return lines
    
    @staticmethod
    def _format_player_phases(opening: PhaseStatistics, middlegame: Optional[PhaseStatistics],
                              endgame: Optional[PhaseStatistics], opening_end: int,
                              middlegame_end: int, endgame_type: Optional[str]) -> List[str]:
        """Format phases for a single player.
        
        Args:
            opening: Opening phase statistics.
            middlegame: Middlegame phase statistics.
            endgame: Endgame phase statistics.
            opening_end: Move number where opening ends.
            middlegame_end: Move number where middlegame ends.
            endgame_type: Type of endgame.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        
        # Opening
        move_range = f" (.. move {opening_end})" if opening_end > 0 else ""
        phase_name = f"Opening{move_range}"
        accuracy = "-" if opening.moves == 0 else f"{opening.accuracy:.1f}%" if opening.accuracy is not None else "-"
        acpl = opening.average_cpl if opening.average_cpl is not None else 0.0
        lines.append(f"  {phase_name}:")
        lines.append(f"    Accuracy: {accuracy}")
        lines.append(f"    ACPL: {acpl:.1f}")
        
        # Middlegame
        if middlegame:
            move_range = f" (.. move {middlegame_end})" if middlegame_end > 0 else ""
            phase_name = f"Middlegame{move_range}"
            accuracy = "-" if middlegame.moves == 0 else f"{middlegame.accuracy:.1f}%" if middlegame.accuracy is not None else "-"
            acpl = middlegame.average_cpl if middlegame.average_cpl is not None else 0.0
            lines.append(f"  {phase_name}:")
            lines.append(f"    Accuracy: {accuracy}")
            lines.append(f"    ACPL: {acpl:.1f}")
        
        # Endgame
        if endgame:
            if endgame_type:
                if endgame_type == "Endgame":
                    phase_name = "Endgame\n    (undefined)"
                else:
                    phase_name = f"Endgame\n    ({endgame_type})"
            else:
                phase_name = "Endgame"
            accuracy = "-" if endgame.moves == 0 else f"{endgame.accuracy:.1f}%" if endgame.accuracy is not None else "-"
            acpl = endgame.average_cpl if endgame.average_cpl is not None else 0.0
            lines.append(f"  {phase_name}:")
            lines.append(f"    Accuracy: {accuracy}")
            lines.append(f"    ACPL: {acpl:.1f}")
        
        return lines
    
    @staticmethod
    def format_game_highlights(highlights: List[GameHighlight]) -> List[str]:
        """Format game highlights section matching the UI display.
        
        Args:
            highlights: List of GameHighlight instances.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Game Highlights")
        lines.append("-" * 16)
        
        if highlights:
            for highlight in highlights:
                lines.append(f"\n{highlight.move_notation}: {highlight.description}")
        
        return lines
    
    @staticmethod
    def format_critical_moments(summary: GameSummary, white_name: str, black_name: str) -> List[str]:
        """Format critical moments section matching the UI display.
        
        Args:
            summary: GameSummary instance.
            white_name: White player name.
            black_name: Black player name.
            
        Returns:
            List of formatted lines.
        """
        lines = []
        lines.append("Critical Moments")
        lines.append("-" * 17)
        
        if summary.white_top_worst:
            lines.append(f"\n{white_name} (White) - Top 3 Worst Moves:")
            for i, move in enumerate(summary.white_top_worst[:3], 1):
                move_notation = move.move_notation if move.move_notation else "N/A"
                assessment = move.assessment if move.assessment else "N/A"
                cpl = move.cpl if move.cpl is not None else 0.0
                lines.append(f"  {i}. {move_notation} ({assessment}, CPL: {cpl:.0f})")
                if move.best_move:
                    lines.append(f"     Best: {move.best_move}")
        
        if summary.white_top_best:
            lines.append(f"\n{white_name} (White) - Top 3 Best Moves:")
            for i, move in enumerate(summary.white_top_best[:3], 1):
                move_notation = move.move_notation if move.move_notation else "N/A"
                assessment = move.assessment if move.assessment else "N/A"
                cpl = move.cpl if move.cpl is not None else 0.0
                lines.append(f"  {i}. {move_notation} ({assessment}, CPL: {cpl:.0f})")
        
        if summary.black_top_worst:
            lines.append(f"\n{black_name} (Black) - Top 3 Worst Moves:")
            for i, move in enumerate(summary.black_top_worst[:3], 1):
                move_notation = move.move_notation if move.move_notation else "N/A"
                assessment = move.assessment if move.assessment else "N/A"
                cpl = move.cpl if move.cpl is not None else 0.0
                lines.append(f"  {i}. {move_notation} ({assessment}, CPL: {cpl:.0f})")
                if move.best_move:
                    lines.append(f"     Best: {move.best_move}")
        
        if summary.black_top_best:
            lines.append(f"\n{black_name} (Black) - Top 3 Best Moves:")
            for i, move in enumerate(summary.black_top_best[:3], 1):
                move_notation = move.move_notation if move.move_notation else "N/A"
                assessment = move.assessment if move.assessment else "N/A"
                cpl = move.cpl if move.cpl is not None else 0.0
                lines.append(f"  {i}. {move_notation} ({assessment}, CPL: {cpl:.0f})")
        
        return lines
    
    @staticmethod
    def format_section(summary: GameSummary, section_name: str, white_name: str, black_name: str) -> str:
        """Format a specific section as text.
        
        Args:
            summary: GameSummary instance.
            section_name: Name of the section to format.
            white_name: White player name.
            black_name: Black player name.
            
        Returns:
            Formatted text string for the section.
        """
        lines = []
        lines.append(section_name)
        lines.append("=" * len(section_name))
        
        if section_name == "Key Statistics":
            # Skip the header line from format_key_statistics
            section_lines = SummaryTextFormatter.format_key_statistics(summary, white_name, black_name)
            lines.extend(section_lines[2:])  # Skip "Key Statistics" and "--------------"
        elif section_name == "Move Classification":
            # Skip the header line from format_move_classification
            section_lines = SummaryTextFormatter.format_move_classification(summary, white_name, black_name)
            lines.extend(section_lines[2:])  # Skip "Move Classification" and "---------------------"
        elif section_name == "Phase Analysis":
            # Skip the header line from format_phase_analysis
            section_lines = SummaryTextFormatter.format_phase_analysis(summary, white_name, black_name)
            lines.extend(section_lines[2:])  # Skip "Phase Analysis" and "---------------"
        elif section_name == "Game Highlights":
            # Skip the header line from format_game_highlights
            section_lines = SummaryTextFormatter.format_game_highlights(summary.highlights or [])
            lines.extend(section_lines[2:])  # Skip "Game Highlights" and "----------------"
        elif section_name == "Critical Moments":
            # Skip the header line from format_critical_moments
            section_lines = SummaryTextFormatter.format_critical_moments(summary, white_name, black_name)
            lines.extend(section_lines[2:])  # Skip "Critical Moments" and "-----------------"
        
        return "\n".join(lines)
    
    @staticmethod
    def format_full_summary(summary: GameSummary, white_name: str, black_name: str) -> str:
        """Format the full summary as text.
        
        Args:
            summary: GameSummary instance.
            white_name: White player name.
            black_name: Black player name.
            
        Returns:
            Formatted text string for the entire summary.
        """
        lines = []
        lines.append("Game Summary\n" + "=" * 12 + "\n")
        
        # Add all sections
        lines.extend(SummaryTextFormatter.format_key_statistics(summary, white_name, black_name))
        lines.append("")
        lines.extend(SummaryTextFormatter.format_move_classification(summary, white_name, black_name))
        lines.append("")
        lines.extend(SummaryTextFormatter.format_phase_analysis(summary, white_name, black_name))
        lines.append("")
        if summary.highlights:
            lines.extend(SummaryTextFormatter.format_game_highlights(summary.highlights))
            lines.append("")
        lines.extend(SummaryTextFormatter.format_critical_moments(summary, white_name, black_name))
        
        return "\n".join(lines)

