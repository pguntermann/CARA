# CARA v2.4.5 - Initial Release

**Release Date:** 29.11.2025

Initial public release of CARA (Chess Analysis and Review Application), a desktop application for analyzing and reviewing chess games.

## Features

This release includes:

### Core Features

- **Automatic Game Analysis** with MultiPV engine support, move classification (Good, Inaccuracy, Mistake, Blunder, Brilliancy), and Centipawn Loss (CPL) calculation
- **44 Game Highlight Rules** automatically detecting tactical and positional patterns (pins, forks, skewers, batteries, tactical sequences, and more)
- **Interactive Chessboard** with move arrows, PV visualization, positional heatmap overlay, and extensive customization options
- **Game Summary** providing statistical analysis, phase-by-phase breakdowns, evaluation graphs, and key moments
- **Player Statistics** with aggregated metrics across multiple games, phase-specific analysis, and error pattern detection
- **Manual Analysis** with continuous MultiPV engine analysis and positional plan exploration
- **PGN Database Management** with multi-database support, powerful search, deduplication, and bulk operations
- **Online Import** from Lichess and Chess.com with filtering options
- **Free-form Annotations** with text, arrows, circles, and square highlighting
- **AI Summary** integration with OpenAI and Anthropic models for interactive game discussion
- **Moves List** with 32 available columns and flexible profile management

### Technical Details

- Built with PyQt6 using Model/View/Controller architecture
- Fully customizable UI through configuration files (no hardcoded values)
- Thread-safe background operations with progress tracking
- Extensible rule-based system for highlights and positional analysis
- Support for any UCI-compatible chess engine

## Getting Started

1. Install Python 3.8+ and dependencies: `pip install -r requirements.txt`
2. Configure a UCI-compatible chess engine (Stockfish recommended)
3. Launch: `python cara.py`

For detailed installation instructions and documentation, see the [README](README.md).

## Documentation

- **User Manual**: [Online version](https://pguntermann.github.io/CARA/manual.html) (also accessible from **Help → Open Manual** in the application)

## System Requirements

- **OS**: Windows 11 (tested), Linux/macOS (may require some adjustments, will be tested later)
- **Python**: 3.8 or higher
- **Screen**: Minimum 1280×1024 pixels recommended
- **Hardware**: Modern multi-core processor recommended

## License

CARA is released under the **GNU General Public License version 3 (GPL-3.0)**.

---

**Copyright (C) 2025 Philipp Guntermann**
