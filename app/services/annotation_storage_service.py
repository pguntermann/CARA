"""Service for storing and loading chessboard annotations in PGN tags."""

import json
import gzip
import zlib
import base64
import hashlib
from typing import Dict, List, Optional, Any
from io import StringIO
from datetime import datetime

import chess.pgn

from app.models.database_model import GameData
from app.services.pgn_service import PgnService
from app.models.annotation_model import Annotation, AnnotationType
from app.services.logging_service import LoggingService


class AnnotationStorageService:
    """Service for storing and loading chessboard annotations in PGN tags.
    
    This service handles serialization, compression, and storage of annotations
    in a custom PGN tag [CARAAnnotations "..."] for persistence across sessions.
    Also stores [CARAAnnotationsInfo "..."] with app version and datetime, and
    [CARAAnnotationsChecksum "..."] for data integrity validation.
    """
    
    TAG_NAME = "CARAAnnotations"
    TAG_INFO = "CARAAnnotationsInfo"
    TAG_CHECKSUM = "CARAAnnotationsChecksum"
    
    @staticmethod
    def has_annotations(game: GameData) -> bool:
        """Check if game has stored annotations.
        
        Args:
            game: GameData instance to check.
            
        Returns:
            True if CARAAnnotations tag exists, False otherwise.
        """
        if game is None or not hasattr(game, 'pgn') or game.pgn is None:
            return False
        
        try:
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return False
            
            return AnnotationStorageService.TAG_NAME in chess_game.headers
        except Exception:
            return False
    
    @staticmethod
    def get_raw_annotations_data(game: GameData) -> Optional[str]:
        """Get raw decompressed JSON string from CARAAnnotations tag.
        
        Args:
            game: GameData instance to read from.
            
        Returns:
            Decompressed JSON string if tag exists and is valid, None otherwise.
        """
        if game is None or not hasattr(game, 'pgn') or game.pgn is None:
            return None
        
        try:
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return None
            
            if AnnotationStorageService.TAG_NAME not in chess_game.headers:
                return None
            
            encoded = chess_game.headers[AnnotationStorageService.TAG_NAME]
            compressed = base64.b64decode(encoded.encode('ascii'))
            
            try:
                json_str = gzip.decompress(compressed).decode('utf-8')
            except (gzip.BadGzipFile, OSError, zlib.error) as e:
                raise ValueError(f"Annotations data decompression failed: {e}") from e
            
            return json_str
        except Exception:
            return None
    
    @staticmethod
    def store_annotations(game: GameData, annotations: Dict[int, List[Annotation]], 
                         config: Optional[Dict[str, Any]] = None) -> bool:
        """Store annotations in PGN tag.
        
        Args:
            game: GameData instance to update.
            annotations: Dictionary mapping ply_index to list of annotations.
            config: Optional configuration dictionary to get app version.
            
        Returns:
            True if storage was successful, False otherwise.
        """
        try:
            # Serialize annotations to JSON
            annotations_data = {}
            for ply_index, ann_list in annotations.items():
                ann_data = []
                for ann in ann_list:
                    ann_dict = {
                        "id": ann.annotation_id,
                        "type": ann.annotation_type.value,
                        "color": ann.color,
                    }
                    if ann.color_index is not None:
                        ann_dict["color_index"] = ann.color_index
                    if ann.from_square:
                        ann_dict["from_square"] = ann.from_square
                    if ann.to_square:
                        ann_dict["to_square"] = ann.to_square
                    if ann.square:
                        ann_dict["square"] = ann.square
                    if ann.text:
                        ann_dict["text"] = ann.text
                    if ann.text_x is not None:
                        ann_dict["text_x"] = ann.text_x
                    if ann.text_y is not None:
                        ann_dict["text_y"] = ann.text_y
                    if ann.text_size is not None:
                        ann_dict["text_size"] = ann.text_size
                    if ann.text_rotation is not None:
                        ann_dict["text_rotation"] = ann.text_rotation
                    if ann.size is not None:
                        ann_dict["size"] = ann.size
                    if ann.shadow is not None:
                        ann_dict["shadow"] = ann.shadow
                    ann_data.append(ann_dict)
                annotations_data[str(ply_index)] = ann_data
            
            # Convert to JSON string
            json_str = json.dumps(annotations_data, ensure_ascii=False)
            
            # Calculate checksum
            checksum = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
            
            # Compress with gzip
            compressed = gzip.compress(json_str.encode('utf-8'), compresslevel=9)
            
            # Base64 encode
            encoded = base64.b64encode(compressed).decode('ascii')
            
            # Get app version from config
            app_version = config.get('version', '1.0') if config else '1.0'
            current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            info_str = f"App Version: {app_version}, Created: {current_datetime}"
            
            # Parse PGN to add/update tags
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return False
            
            # Add or update the tags
            chess_game.headers[AnnotationStorageService.TAG_NAME] = encoded
            chess_game.headers[AnnotationStorageService.TAG_INFO] = info_str
            chess_game.headers[AnnotationStorageService.TAG_CHECKSUM] = checksum
            
            # Regenerate PGN text
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            
            # Update game's PGN
            game.pgn = new_pgn
            game.annotated = True
            
            return True
        except Exception as e:
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error storing annotations: {e}", exc_info=e)
            return False
    
    @staticmethod
    def load_annotations(game: GameData) -> Optional[Dict[int, List[Annotation]]]:
        """Load annotations from PGN tag.
        
        Args:
            game: GameData instance to read from.
            
        Returns:
            Dictionary mapping ply_index to list of annotations if tag exists and is valid, None otherwise.
        """
        if game is None or not hasattr(game, 'pgn') or game.pgn is None:
            return None
        
        try:
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return None
            
            if AnnotationStorageService.TAG_NAME not in chess_game.headers:
                return None
            
            encoded = chess_game.headers[AnnotationStorageService.TAG_NAME]
            compressed = base64.b64decode(encoded.encode('ascii'))
            
            try:
                json_str = gzip.decompress(compressed).decode('utf-8')
            except (gzip.BadGzipFile, OSError, zlib.error) as e:
                AnnotationStorageService._remove_corrupted_annotation_tags(game)
                raise ValueError(f"Annotations data decompression failed: {e}") from e
            
            # Verify checksum if present
            if AnnotationStorageService.TAG_CHECKSUM in chess_game.headers:
                stored_checksum = chess_game.headers[AnnotationStorageService.TAG_CHECKSUM]
                calculated_checksum = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
                
                if stored_checksum != calculated_checksum:
                    AnnotationStorageService._remove_corrupted_annotation_tags(game)
                    logging_service = LoggingService.get_instance()
                    logging_service.warning("Annotations checksum mismatch.")
                    return None
            
            # Deserialize JSON
            annotations_data = json.loads(json_str)
            
            # Convert to Annotation instances
            annotations: Dict[int, List[Annotation]] = {}
            for ply_str, ann_list in annotations_data.items():
                ply_index = int(ply_str)
                annotations[ply_index] = []
                for ann_dict in ann_list:
                    ann = Annotation(
                        annotation_id=ann_dict.get("id", ""),
                        annotation_type=AnnotationType(ann_dict.get("type", "arrow")),
                        color=ann_dict.get("color", [255, 0, 0]),
                        color_index=ann_dict.get("color_index"),
                        from_square=ann_dict.get("from_square"),
                        to_square=ann_dict.get("to_square"),
                        square=ann_dict.get("square"),
                        text=ann_dict.get("text"),
                        text_x=ann_dict.get("text_x"),
                        text_y=ann_dict.get("text_y"),
                        text_size=ann_dict.get("text_size"),
                        text_rotation=ann_dict.get("text_rotation"),
                        size=ann_dict.get("size", 1.0),
                        shadow=ann_dict.get("shadow", False),
                    )
                    annotations[ply_index].append(ann)
            
            return annotations
        except Exception:
            return None
    
    @staticmethod
    def _remove_corrupted_annotation_tags(game: GameData) -> None:
        """Remove corrupted annotation tags from game PGN.
        
        Args:
            game: GameData instance to update.
        """
        try:
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return
            
            # Remove corrupted tags
            if AnnotationStorageService.TAG_NAME in chess_game.headers:
                del chess_game.headers[AnnotationStorageService.TAG_NAME]
            if AnnotationStorageService.TAG_INFO in chess_game.headers:
                del chess_game.headers[AnnotationStorageService.TAG_INFO]
            if AnnotationStorageService.TAG_CHECKSUM in chess_game.headers:
                del chess_game.headers[AnnotationStorageService.TAG_CHECKSUM]
            
            # Regenerate PGN
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            game.pgn = new_pgn
            game.annotated = False
        except Exception:
            pass

