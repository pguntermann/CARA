"""Service for storing and loading chessboard annotations in PGN tags."""

import json
from typing import Dict, List, Optional, Any, Union
from io import StringIO
from datetime import datetime

import chess.pgn

from app.models.database_model import GameData
from app.services.pgn_service import PgnService
from app.models.annotation_model import Annotation, AnnotationType, AnnotationKey, normalize_annotation_key
from app.services.logging_service import LoggingService
from app.utils.pgn_tag_compression import (
    decode_and_decompress_to_str,
    compress_and_encode_from_str,
    compute_checksum,
)
from app.utils.pgn_variation_path import encode_path, mainline_path_for_ply


class AnnotationStorageService:
    """Service for storing and loading chessboard annotations in PGN tags.
    
    This service handles serialization, compression, and storage of annotations
    in a custom PGN tag [CARAAnnotations "..."] for persistence across sessions.
    Also stores [CARAAnnotationsInfo "..."] with app version and datetime, and
    [CARAAnnotationsChecksum "..."] for data integrity validation.

    Storage format v2 keys annotations by variation path (encode_path). Legacy
    flat maps keyed by ply index are still loaded and converted.
    """
    
    TAG_NAME = "CARAAnnotations"
    TAG_INFO = "CARAAnnotationsInfo"
    TAG_CHECKSUM = "CARAAnnotationsChecksum"
    FORMAT_VERSION = 2
    
    @staticmethod
    def has_annotations(game: GameData) -> bool:
        """Check if game has stored annotations."""
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
        """Get raw decompressed JSON string from CARAAnnotations tag."""
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
            json_str = decode_and_decompress_to_str(encoded)
            return json_str
        except (ValueError, Exception):
            return None

    @staticmethod
    def _serialize_annotation(ann: Annotation) -> Dict[str, Any]:
        ann_dict: Dict[str, Any] = {
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
        return ann_dict

    @staticmethod
    def _deserialize_annotation(ann_dict: Dict[str, Any]) -> Annotation:
        return Annotation(
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

    @staticmethod
    def _legacy_ply_map_to_path_map(
        annotations_data: Dict[str, Any]
    ) -> Dict[AnnotationKey, List[Annotation]]:
        """Convert legacy ply-index JSON map to path-keyed annotations."""
        annotations: Dict[AnnotationKey, List[Annotation]] = {}
        for ply_str, ann_list in annotations_data.items():
            try:
                ply_index = int(ply_str)
            except (TypeError, ValueError):
                key = str(ply_str)
            else:
                key = encode_path(mainline_path_for_ply(ply_index))
            annotations[key] = [
                AnnotationStorageService._deserialize_annotation(ann_dict)
                for ann_dict in ann_list
            ]
        return annotations
    
    @staticmethod
    def store_annotations(
        game: GameData,
        annotations: Dict[Union[str, int], List[Annotation]],
        config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store annotations in PGN tag (path-keyed format v2)."""
        try:
            paths_data: Dict[str, List[Dict[str, Any]]] = {}
            for path_or_key, ann_list in annotations.items():
                key = normalize_annotation_key(path_or_key)
                if not ann_list:
                    continue
                paths_data[key] = [
                    AnnotationStorageService._serialize_annotation(ann)
                    for ann in ann_list
                ]

            payload = {
                "_v": AnnotationStorageService.FORMAT_VERSION,
                "paths": paths_data,
            }
            
            json_str = json.dumps(payload, ensure_ascii=False)
            data_bytes = json_str.encode("utf-8")
            checksum = compute_checksum(data_bytes)
            encoded = compress_and_encode_from_str(json_str, compresslevel=9)
            
            app_version = config.get('version', '1.0') if config else '1.0'
            current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            info_str = f"App Version: {app_version}, Created: {current_datetime}"
            
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return False
            
            chess_game.headers[AnnotationStorageService.TAG_NAME] = encoded
            chess_game.headers[AnnotationStorageService.TAG_INFO] = info_str
            chess_game.headers[AnnotationStorageService.TAG_CHECKSUM] = checksum
            
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            
            game.pgn = new_pgn
            game.annotated = bool(paths_data)
            
            return True
        except Exception as e:
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error storing annotations: {e}", exc_info=e)
            return False
    
    @staticmethod
    def load_annotations(game: GameData) -> Optional[Dict[AnnotationKey, List[Annotation]]]:
        """Load annotations from PGN tag (v2 path keys or legacy ply keys)."""
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
            try:
                json_str = decode_and_decompress_to_str(encoded)
            except ValueError:
                AnnotationStorageService._remove_corrupted_annotation_tags(game)
                raise
            
            if AnnotationStorageService.TAG_CHECKSUM in chess_game.headers:
                stored_checksum = chess_game.headers[AnnotationStorageService.TAG_CHECKSUM]
                calculated_checksum = compute_checksum(json_str.encode("utf-8"))
                
                if stored_checksum != calculated_checksum:
                    AnnotationStorageService._remove_corrupted_annotation_tags(game)
                    logging_service = LoggingService.get_instance()
                    logging_service.warning("Annotations checksum mismatch.")
                    return None
            
            annotations_data = json.loads(json_str)
            if not isinstance(annotations_data, dict):
                return None

            # Format v2: {"_v": 2, "paths": {"0.1": [...]}}
            if (
                annotations_data.get("_v") == AnnotationStorageService.FORMAT_VERSION
                and isinstance(annotations_data.get("paths"), dict)
            ):
                annotations: Dict[AnnotationKey, List[Annotation]] = {}
                for path_key, ann_list in annotations_data["paths"].items():
                    key = str(path_key)
                    annotations[key] = [
                        AnnotationStorageService._deserialize_annotation(ann_dict)
                        for ann_dict in ann_list
                    ]
                return annotations

            # Legacy flat map: {"0": [...], "1": [...]} keyed by ply index
            return AnnotationStorageService._legacy_ply_map_to_path_map(annotations_data)
        except ValueError:
            raise
        except Exception:
            return None
    
    @staticmethod
    def _remove_corrupted_annotation_tags(game: GameData) -> None:
        """Remove corrupted annotation tags from game PGN."""
        try:
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return
            
            if AnnotationStorageService.TAG_NAME in chess_game.headers:
                del chess_game.headers[AnnotationStorageService.TAG_NAME]
            if AnnotationStorageService.TAG_INFO in chess_game.headers:
                del chess_game.headers[AnnotationStorageService.TAG_INFO]
            if AnnotationStorageService.TAG_CHECKSUM in chess_game.headers:
                del chess_game.headers[AnnotationStorageService.TAG_CHECKSUM]
            
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            game.pgn = new_pgn
            game.annotated = False
        except Exception:
            pass
