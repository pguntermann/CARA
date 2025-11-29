"""Service for searching games in databases based on criteria."""

from typing import List, Optional, Dict, Any
from io import StringIO
import chess.pgn

from app.models.database_model import GameData, DatabaseModel
from app.models.search_criteria import SearchCriteria, SearchField, SearchOperator
from app.services.date_matcher import DateMatcher


class DatabaseSearchService:
    """Service for searching games in databases."""
    
    @staticmethod
    def search_databases(
        databases: List[DatabaseModel],
        criteria: List[SearchCriteria],
        database_names: Optional[List[str]] = None
    ) -> List[tuple[GameData, str]]:
        """Search games across multiple databases.
        
        Args:
            databases: List of DatabaseModel instances to search.
            criteria: List of SearchCriteria to apply.
            database_names: Optional list of database names corresponding to databases list.
                          If None, will use "Database 1", "Database 2", etc.
            
        Returns:
            List of tuples (GameData, database_name) for games that match all criteria.
        """
        if not criteria:
            return []
        
        # Build criteria tree for evaluation
        criteria_tree = DatabaseSearchService._build_criteria_tree(criteria)
        
        # Collect matching games from all databases
        matching_games: List[tuple[GameData, str]] = []
        
        for idx, database in enumerate(databases):
            # Get database name
            if database_names and idx < len(database_names):
                db_name = database_names[idx]
            else:
                db_name = f"Database {idx + 1}"
            
            games = database.get_all_games()
            for game in games:
                if DatabaseSearchService._evaluate_criteria_tree(game, criteria_tree):
                    matching_games.append((game, db_name))
        
        return matching_games
    
    @staticmethod
    def _build_criteria_tree(criteria: List[SearchCriteria]) -> Dict[str, Any]:
        """Build a tree structure from criteria list for evaluation.
        
        Args:
            criteria: List of SearchCriteria.
            
        Returns:
            Tree structure representing criteria with groups.
        """
        if not criteria:
            return {"type": "empty"}
        
        # Simple approach: evaluate sequentially with AND/OR precedence
        # Groups are handled by tracking nesting level
        return {
            "type": "criteria_list",
            "criteria": criteria
        }
    
    @staticmethod
    def _evaluate_criteria_tree(game: GameData, tree: Dict[str, Any]) -> bool:
        """Evaluate if a game matches the criteria tree.
        
        Args:
            game: GameData instance to evaluate.
            tree: Criteria tree structure.
            
        Returns:
            True if game matches all criteria, False otherwise.
        """
        if tree.get("type") == "empty":
            return True
        
        if tree.get("type") == "criteria_list":
            criteria = tree.get("criteria", [])
            return DatabaseSearchService._evaluate_criteria_list(game, criteria)
        
        return False
    
    @staticmethod
    def _evaluate_criteria_list(game: GameData, criteria: List[SearchCriteria]) -> bool:
        """Evaluate a list of criteria against a game.
        
        Handles AND/OR logic and grouping using recursive evaluation.
        
        Args:
            game: GameData instance to evaluate.
            criteria: List of SearchCriteria.
            
        Returns:
            True if game matches criteria, False otherwise.
        """
        if not criteria:
            return True
        
        # Parse criteria into groups and evaluate recursively
        return DatabaseSearchService._evaluate_criteria_recursive(game, criteria, 0, len(criteria))
    
    @staticmethod
    def _evaluate_criteria_recursive(
        game: GameData,
        criteria: List[SearchCriteria],
        start_idx: int,
        end_idx: int,
        default_logic: str = "and"
    ) -> bool:
        """Recursively evaluate criteria with grouping support.
        
        Args:
            game: GameData instance to evaluate.
            criteria: Full list of SearchCriteria.
            start_idx: Start index in criteria list.
            end_idx: End index (exclusive) in criteria list.
            default_logic: Default logic operator ("and" or "or").
            
        Returns:
            True if game matches criteria in range, False otherwise.
        """
        if start_idx >= end_idx:
            return True
        
        results: List[bool] = []
        logic_operators: List[str] = []
        i = start_idx
        
        while i < end_idx:
            criterion = criteria[i]
            
            # Handle group start
            if criterion.is_group_start:
                # Find matching group end
                group_start = i
                group_level = criterion.group_level
                i += 1
                
                # Find the matching end group at the same level
                nested_level = 0
                group_end = -1
                while i < end_idx:
                    if criteria[i].is_group_start:
                        nested_level += 1
                    elif criteria[i].is_group_end and criteria[i].group_level == group_level:
                        if nested_level == 0:
                            group_end = i
                            break
                        else:
                            nested_level -= 1
                    i += 1
                
                if group_end == -1:
                    # No matching end group found, treat as regular criterion
                    matches = DatabaseSearchService._evaluate_criterion(game, criterion)
                    results.append(matches)
                    if criterion.logic_operator:
                        logic_operators.append(criterion.logic_operator.value)
                    i += 1
                    continue
                
                # Evaluate the group recursively
                # The group includes criteria from group_start to group_end (both inclusive)
                # But we need to skip the group markers when evaluating, so we evaluate the actual criteria
                # The group logic is determined by the logic operator of the first actual criterion in the group
                group_logic = default_logic
                # Check the first criterion in the group (which is the group_start marker itself)
                # Its logic operator indicates how to combine it with the next criterion
                if group_start + 1 <= group_end:
                    # Look at the first actual criterion after the group_start marker
                    first_actual = criteria[group_start + 1] if group_start + 1 < group_end else criteria[group_start]
                    # But actually, the group_start criterion's logic operator tells us the group logic
                    if criteria[group_start].logic_operator:
                        group_logic = criteria[group_start].logic_operator.value
                    elif first_actual.logic_operator:
                        group_logic = first_actual.logic_operator.value
                
                # Evaluate the group: from group_start to group_end (both inclusive)
                # Both group_start and group_end are actual criteria that should be evaluated
                # Manually evaluate the criteria in the group
                group_criteria_results = []
                group_criteria_logic = []
                for j in range(group_start, group_end + 1):
                    # Evaluate this criterion
                    matches = DatabaseSearchService._evaluate_criterion(game, criteria[j])
                    group_criteria_results.append(matches)
                    
                    # Get logic operator for combining with next criterion in group
                    # The logic operator on a criterion indicates how to combine it with the NEXT criterion
                    if j < group_end:
                        # Look at the NEXT criterion's logic operator (not this one's)
                        next_in_group = criteria[j + 1]
                        if next_in_group.logic_operator:
                            group_criteria_logic.append(next_in_group.logic_operator.value)
                        else:
                            group_criteria_logic.append(group_logic)
                
                # Combine group criteria results
                if not group_criteria_results:
                    group_result = True
                elif len(group_criteria_results) == 1:
                    group_result = group_criteria_results[0]
                else:
                    group_result = group_criteria_results[0]
                    for k in range(1, len(group_criteria_results)):
                        logic_op = group_criteria_logic[k - 1] if k - 1 < len(group_criteria_logic) else group_logic
                        if logic_op == "or":
                            group_result = group_result or group_criteria_results[k]
                        else:
                            group_result = group_result and group_criteria_results[k]
                results.append(group_result)
                
                # Get logic operator for combining group result with next criterion
                # The logic operator on the group_end criterion indicates how to combine
                # the group result with the next criterion (outside the group)
                next_idx = group_end + 1
                
                # Skip any consecutive group_end markers
                while next_idx < end_idx and criteria[next_idx].is_group_end:
                    next_idx += 1
                
                if next_idx < end_idx:
                    # Use the next criterion's logic operator to combine group with next criterion
                    # The logic operator on the next criterion indicates how to combine the previous
                    # result (which is the group result) with that criterion
                    next_criterion = criteria[next_idx]
                    if next_criterion.logic_operator:
                        logic_operators.append(next_criterion.logic_operator.value)
                    else:
                        # Fall back to default if next criterion doesn't have a logic operator
                        logic_operators.append(default_logic)
                else:
                    # No next criterion, use default
                    logic_operators.append(default_logic)
                
                i = group_end + 1
                continue
            
            # Handle group end (should be handled by group start, but handle orphaned ends)
            if criterion.is_group_end:
                i += 1
                continue
            
            # Regular criterion
            matches = DatabaseSearchService._evaluate_criterion(game, criterion)
            results.append(matches)
            
            # Get logic operator for combining this result with the NEXT result
            # The logic operator on a criterion indicates how to combine it with the previous criterion
            # But we need it for combining with the next, so we look ahead
            if i + 1 < end_idx:
                next_criterion = criteria[i + 1]
                if next_criterion.logic_operator:
                    logic_operators.append(next_criterion.logic_operator.value)
                else:
                    logic_operators.append(default_logic)
            # If this is the last criterion, no logic operator needed
            
            i += 1
        
        # Evaluate results with logic operators
        if not results:
            return True
        
        # If only one result, return it directly
        if len(results) == 1:
            return results[0]
        
        # Start with first result
        result = results[0]
        
        # Combine with remaining results using logic operators
        # The logic operator at index i-1 indicates how to combine results[i-1] with results[i]
        for i in range(1, len(results)):
            # Get the logic operator from the criterion at position i (which indicates how to combine with previous)
            # But we need to map back to the original criterion index
            # For now, use the logic operator from the criterion that produced results[i]
            # Actually, logic_operators[i-1] should correspond to how to combine results[i-1] with results[i]
            if i - 1 < len(logic_operators):
                logic = logic_operators[i - 1]
            else:
                # If no logic operator specified, check the criterion at position i
                # Find which criterion index corresponds to results[i]
                # This is complex, so for now use default_logic
                logic = default_logic
            
            if logic == "or":
                result = result or results[i]
            else:  # "and"
                result = result and results[i]
        return result
    
    @staticmethod
    def _evaluate_criterion(game: GameData, criterion: SearchCriteria) -> bool:
        """Evaluate a single criterion against a game.
        
        Args:
            game: GameData instance to evaluate.
            criterion: SearchCriteria to check.
            
        Returns:
            True if game matches criterion, False otherwise.
        """
        # Get field value
        field_value = DatabaseSearchService._get_field_value(game, criterion)
        
        # Evaluate based on operator
        operator = criterion.operator
        value = criterion.value
        
        if operator == SearchOperator.CONTAINS:
            if field_value is None:
                return False
            return str(value).lower() in str(field_value).lower()
        
        elif operator == SearchOperator.EQUALS:
            if field_value is None:
                return False
            return str(value).lower() == str(field_value).lower()
        
        elif operator == SearchOperator.NOT_EQUALS:
            if field_value is None:
                return True  # None is not equal to any value
            return str(value).lower() != str(field_value).lower()
        
        elif operator == SearchOperator.STARTS_WITH:
            if field_value is None:
                return False
            return str(field_value).lower().startswith(str(value).lower())
        
        elif operator == SearchOperator.ENDS_WITH:
            if field_value is None:
                return False
            return str(field_value).lower().endswith(str(value).lower())
        
        elif operator == SearchOperator.IS_EMPTY:
            return field_value is None or str(field_value).strip() == ""
        
        elif operator == SearchOperator.IS_NOT_EMPTY:
            return field_value is not None and str(field_value).strip() != ""
        
        elif operator == SearchOperator.EQUALS_NUM:
            try:
                field_num = float(field_value) if field_value else 0
                value_num = float(value)
                return field_num == value_num
            except (ValueError, TypeError):
                return False
        
        elif operator == SearchOperator.NOT_EQUALS_NUM:
            try:
                field_num = float(field_value) if field_value else 0
                value_num = float(value)
                return field_num != value_num
            except (ValueError, TypeError):
                return True  # If conversion fails, they're not equal
        
        elif operator == SearchOperator.GREATER_THAN:
            try:
                field_num = float(field_value) if field_value else 0
                value_num = float(value)
                return field_num > value_num
            except (ValueError, TypeError):
                return False
        
        elif operator == SearchOperator.LESS_THAN:
            try:
                field_num = float(field_value) if field_value else 0
                value_num = float(value)
                return field_num < value_num
            except (ValueError, TypeError):
                return False
        
        elif operator == SearchOperator.GREATER_THAN_OR_EQUAL:
            try:
                field_num = float(field_value) if field_value else 0
                value_num = float(value)
                return field_num >= value_num
            except (ValueError, TypeError):
                return False
        
        elif operator == SearchOperator.LESS_THAN_OR_EQUAL:
            try:
                field_num = float(field_value) if field_value else 0
                value_num = float(value)
                return field_num <= value_num
            except (ValueError, TypeError):
                return False
        
        elif operator == SearchOperator.DATE_EQUALS:
            if field_value is None:
                return False
            return DateMatcher.date_equals(str(field_value), str(value))
        
        elif operator == SearchOperator.DATE_NOT_EQUALS:
            if field_value is None:
                return True  # None is not equal to any date
            return not DateMatcher.date_equals(str(field_value), str(value))
        
        elif operator == SearchOperator.DATE_BEFORE:
            if field_value is None:
                return False
            return DateMatcher.date_before(str(field_value), str(value))
        
        elif operator == SearchOperator.DATE_AFTER:
            if field_value is None:
                return False
            return DateMatcher.date_after(str(field_value), str(value))
        
        elif operator == SearchOperator.DATE_CONTAINS:
            if field_value is None:
                return False
            return DateMatcher.date_contains(str(field_value), str(value))
        
        elif operator == SearchOperator.IS_TRUE:
            if criterion.field == SearchField.ANALYZED:
                return bool(game.analyzed)
            if criterion.field == SearchField.ANNOTATED:
                return bool(getattr(game, "annotated", False))
            return bool(field_value)
        
        elif operator == SearchOperator.IS_FALSE:
            if criterion.field == SearchField.ANALYZED:
                return not bool(game.analyzed)
            if criterion.field == SearchField.ANNOTATED:
                return not bool(getattr(game, "annotated", False))
            return not bool(field_value)
        
        return False
    
    @staticmethod
    def _get_field_value(game: GameData, criterion: SearchCriteria) -> Any:
        """Get the value of a field from a game.
        
        Args:
            game: GameData instance.
            criterion: SearchCriteria with field to get.
            
        Returns:
            Field value or None if not found.
        """
        field = criterion.field
        
        if field == SearchField.WHITE:
            return game.white
        elif field == SearchField.BLACK:
            return game.black
        elif field == SearchField.WHITE_ELO:
            return game.white_elo
        elif field == SearchField.BLACK_ELO:
            return game.black_elo
        elif field == SearchField.RESULT:
            return game.result
        elif field == SearchField.DATE:
            return game.date
        elif field == SearchField.EVENT:
            return game.event
        elif field == SearchField.SITE:
            return game.site
        elif field == SearchField.ECO:
            return game.eco
        elif field == SearchField.ANALYZED:
            return game.analyzed
        elif field == SearchField.ANNOTATED:
            return getattr(game, "annotated", False)
        elif field == SearchField.CUSTOM_TAG:
            # Extract custom PGN tag
            if not game.pgn or not criterion.custom_tag_name:
                return None
            try:
                pgn_io = StringIO(game.pgn)
                chess_game = chess.pgn.read_game(pgn_io)
                if chess_game:
                    return chess_game.headers.get(criterion.custom_tag_name, None)
            except Exception:
                pass
            return None
        
        return None
    
    @staticmethod
    def _format_search_formula(criteria: List[SearchCriteria]) -> str:
        """Format search criteria into a readable formula string.
        
        Args:
            criteria: List of SearchCriteria.
            
        Returns:
            Formatted formula string like '(White equals "Hans" OR Black equals "Hans") AND (Result not equals "1/2-1/2")'
        """
        if not criteria:
            return ""
        
        # Map fields to readable names
        field_names = {
            SearchField.WHITE: "White",
            SearchField.BLACK: "Black",
            SearchField.WHITE_ELO: "WhiteElo",
            SearchField.BLACK_ELO: "BlackElo",
            SearchField.RESULT: "Result",
            SearchField.DATE: "Date",
            SearchField.EVENT: "Event",
            SearchField.SITE: "Site",
            SearchField.ECO: "ECO",
            SearchField.ANALYZED: "Analyzed",
            SearchField.ANNOTATED: "Annotated",
            SearchField.CUSTOM_TAG: "Custom Tag",
        }
        
        # Map operators to readable names
        operator_names = {
            SearchOperator.CONTAINS: "contains",
            SearchOperator.EQUALS: "equals",
            SearchOperator.NOT_EQUALS: "not equals",
            SearchOperator.STARTS_WITH: "starts with",
            SearchOperator.ENDS_WITH: "ends with",
            SearchOperator.IS_EMPTY: "is empty",
            SearchOperator.IS_NOT_EMPTY: "is not empty",
            SearchOperator.EQUALS_NUM: "equals",
            SearchOperator.NOT_EQUALS_NUM: "not equals",
            SearchOperator.GREATER_THAN: "greater than",
            SearchOperator.LESS_THAN: "less than",
            SearchOperator.GREATER_THAN_OR_EQUAL: "greater than or equal",
            SearchOperator.LESS_THAN_OR_EQUAL: "less than or equal",
            SearchOperator.DATE_EQUALS: "equals",
            SearchOperator.DATE_NOT_EQUALS: "not equals",
            SearchOperator.DATE_BEFORE: "before",
            SearchOperator.DATE_AFTER: "after",
            SearchOperator.DATE_CONTAINS: "contains",
            SearchOperator.IS_TRUE: "is",
            SearchOperator.IS_FALSE: "is not",
        }
        
        parts = []
        i = 0
        while i < len(criteria):
            criterion = criteria[i]
            
            # Format field name
            field_name = field_names.get(criterion.field, criterion.field.value)
            if criterion.field == SearchField.CUSTOM_TAG and criterion.custom_tag_name:
                field_name = f"{criterion.custom_tag_name}"
            
            # Format operator
            operator_name = operator_names.get(criterion.operator, criterion.operator.value)
            
            # Format value
            if criterion.operator in [SearchOperator.IS_EMPTY, SearchOperator.IS_NOT_EMPTY]:
                value_str = ""
            elif criterion.operator in [SearchOperator.IS_TRUE, SearchOperator.IS_FALSE]:
                value_str = ""
            elif criterion.value is None:
                value_str = ""
            else:
                value_str = f'"{criterion.value}"'
            
            # Build criterion string
            if value_str:
                criterion_str = f"{field_name} {operator_name} {value_str}"
            else:
                criterion_str = f"{field_name} {operator_name}"
            
            # Handle groups
            if criterion.is_group_start:
                # Find matching group end
                group_start = i
                group_level = criterion.group_level
                group_end = -1
                nested_level = 0
                j = i + 1
                while j < len(criteria):
                    if criteria[j].is_group_start:
                        nested_level += 1
                    elif criteria[j].is_group_end and criteria[j].group_level == group_level:
                        if nested_level == 0:
                            group_end = j
                            break
                        else:
                            nested_level -= 1
                    j += 1
                
                if group_end != -1:
                    # Format group
                    group_parts = []
                    for k in range(group_start, group_end + 1):
                        group_criterion = criteria[k]
                        group_field = field_names.get(group_criterion.field, group_criterion.field.value)
                        if group_criterion.field == SearchField.CUSTOM_TAG and group_criterion.custom_tag_name:
                            group_field = f"{group_criterion.custom_tag_name}"
                        group_operator = operator_names.get(group_criterion.operator, group_criterion.operator.value)
                        if group_criterion.operator in [SearchOperator.IS_EMPTY, SearchOperator.IS_NOT_EMPTY]:
                            group_value = ""
                        elif group_criterion.operator in [SearchOperator.IS_TRUE, SearchOperator.IS_FALSE]:
                            group_value = ""
                        elif group_criterion.value is None:
                            group_value = ""
                        else:
                            group_value = f'"{group_criterion.value}"'
                        
                        if group_value:
                            group_criterion_str = f"{group_field} {group_operator} {group_value}"
                        else:
                            group_criterion_str = f"{group_field} {group_operator}"
                        
                        group_parts.append(group_criterion_str)
                        
                        # Add logic operator if not last in group
                        # The logic operator on the NEXT criterion indicates how to combine current with next
                        if k < group_end:
                            next_in_group = criteria[k + 1]
                            if next_in_group.logic_operator:
                                logic_op = next_in_group.logic_operator.value.upper()
                                group_parts.append(logic_op)
                    
                    # Combine group parts
                    group_formula = " ".join(group_parts)
                    parts.append(f"({group_formula})")
                    
                    # Add logic operator after group if not last criterion
                    if group_end < len(criteria) - 1:
                        next_criterion = criteria[group_end + 1]
                        if next_criterion.logic_operator:
                            parts.append(next_criterion.logic_operator.value.upper())
                    
                    i = group_end + 1
                    continue
            
            # Regular criterion (not in a group)
            parts.append(criterion_str)
            
            # Add logic operator if not last criterion
            if i < len(criteria) - 1:
                next_criterion = criteria[i + 1]
                if not next_criterion.is_group_start and next_criterion.logic_operator:
                    parts.append(next_criterion.logic_operator.value.upper())
            
            i += 1
        
        return " ".join(parts)

