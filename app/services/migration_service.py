"""Migration service for orchestrating application migrations at startup.

Runs after configuration and logging are initialized, and before the main UI
is created. Ensures user settings and other persisted data are migrated
from templates or previous versions before any component uses them.
"""

from app.services.logging_service import LoggingService
from app.services.user_settings_service import UserSettingsService


class MigrationService:
    """Orchestrates all application migrations at startup.

    Call run() once from the application entry point after services that
    hold persisted data (e.g. UserSettingsService) have been loaded, and
    before the main window or controllers use that data.
    """

    @classmethod
    def run(cls) -> None:
        """Run all migrations in order.

        Each migration is idempotent and may be skipped if already applied.
        Failures are logged; the application continues so that a single
        failed migration does not block startup.
        """
        logging_service = LoggingService.get_instance()
        logging_service.info("Running application migrations")

        cls._run_user_settings_migration(logging_service)
        cls._run_engine_assignment_migration(logging_service)

        logging_service.info("Application migrations completed")

    @classmethod
    def _run_user_settings_migration(cls, logging_service: LoggingService) -> None:
        """Run user settings migration (template merge, profile updates)."""
        try:
            logging_service.debug("User settings migration: starting")
            user_settings_service = UserSettingsService.get_instance()
            user_settings_service.migrate()
            logging_service.debug("User settings migration: completed")
        except Exception as e:
            logging_service.error(
                f"User settings migration failed: {e}",
                exc_info=e,
            )

    @classmethod
    def _run_engine_assignment_migration(cls, logging_service: LoggingService) -> None:
        """Migrate engine assignments: if game_analysis is set and brilliancy_detection is not, copy game_analysis to brilliancy_detection."""
        try:
            logging_service.debug("Engine assignment migration: starting")
            user_settings_service = UserSettingsService.get_instance()
            settings = user_settings_service.get_settings()
            assignments = settings.get("engine_assignments", {})
            game_analysis_id = assignments.get("game_analysis")
            brilliancy_id = assignments.get("brilliancy_detection")
            if game_analysis_id and not brilliancy_id:
                user_settings_service.update_engine_assignments({"brilliancy_detection": game_analysis_id})
                user_settings_service.save()
                logging_service.debug("Engine assignment migration: set brilliancy_detection to game_analysis engine")
            else:
                logging_service.debug("Engine assignment migration: no change needed")
        except Exception as e:
            logging_service.error(
                f"Engine assignment migration failed: {e}",
                exc_info=e,
            )
