import os
import json
from typing import Dict, Optional, Any, List
from cat.log import log
from cat.mad_hatter.decorators import hook, plugin
from cat.looking_glass.stray_cat import StrayCat
from cat.auth.permissions import AuthUserInfo


def setup_scrapycat_schedule(cheshire_cat, settings: Optional[Dict[str, Any]] = None) -> None:
    """Setup or update the ScrapyCat scheduled job based on settings"""
    try:
        if settings is None:
            settings = cheshire_cat.mad_hatter.get_plugin().load_settings()
            
        scheduled_command: str = settings.get("scheduled_command", "").strip()
        schedule_hour: int = settings.get("schedule_hour", 3)
        schedule_minute: int = settings.get("schedule_minute", 0)
        
        # Job ID for the scheduled task
        job_id: str = "scrapycat_scheduled_scraping"
        
        # Always try to remove any existing job first
        try:
            cheshire_cat.white_rabbit.scheduler.remove_job(job_id)
            log.info(f"Removed existing scheduled ScrapyCat job: {job_id}")
        except Exception:
            pass  # Job doesn't exist, which is fine
        
        # If no command is configured, just remove the job and return
        if not scheduled_command:
            log.info("No scheduled ScrapyCat command configured, job removed")
            return
        
        # Import process_scrapycat_command from the main module
        from .scrapycat import process_scrapycat_command
        
        # Create wrapper function for scheduled execution
        def scheduled_scrapycat_job(user_message: str, cat) -> str:
            """Wrapper function for scheduled ScrapyCat execution"""
            # Create a proper StrayCat instance for the scheduled job
            # Use a system user for scheduled operations
            system_user = AuthUserInfo(
                id="system",
                name="system"
            )
            stray_cat = StrayCat(system_user)
            
            return process_scrapycat_command(user_message, stray_cat, scheduled=True)
        
        # Schedule the new job: call the wrapper function
        cheshire_cat.white_rabbit.schedule_cron_job(
            job=scheduled_scrapycat_job,
            job_id=job_id,
            hour=schedule_hour,
            minute=schedule_minute,
            user_message=scheduled_command,
            cat=None  # The wrapper function will create its own StrayCat
        )
        
        # Get current time for comparison
        from datetime import datetime
        import pytz
        current_utc: datetime = datetime.now(pytz.UTC)
        
        log.info(f"Scheduled ScrapyCat command '{scheduled_command}' to run daily at {schedule_hour:02d}:{schedule_minute:02d} UTC")
        log.info(f"Current UTC time: {current_utc}")
        
        # Debug: Check scheduler status and all jobs
        try:
            scheduler_running: bool = cheshire_cat.white_rabbit.scheduler.running
            log.info(f"White Rabbit scheduler running: {scheduler_running}")
            
            if not scheduler_running:
                log.warning("White Rabbit scheduler is not running! This may be why jobs don't execute.")
            
            # Get all jobs
            all_jobs: List[Any] = cheshire_cat.white_rabbit.get_jobs()
            log.info(f"Total scheduled jobs: {len(all_jobs)}")
            
            # Check our specific job
            job: Optional[Dict[str, Any]] = cheshire_cat.white_rabbit.get_job(job_id)
            if job:
                log.info(f"Job successfully added to scheduler: {job}")
                
                # Log next run time - job is a dictionary, not an object
                if 'next_run' in job:
                    log.info(f"Next scheduled run: {job['next_run']}")
                    time_diff = job['next_run'] - current_utc
                    log.info(f"Time until next run: {time_diff}")
                    
                    if time_diff.total_seconds() < 0:
                        log.warning("Job is scheduled in the past! This might be why it's not executing.")
                else:
                    log.warning("Job dictionary has no 'next_run' key")
            else:
                log.error(f"Job not found in scheduler after creation: {job_id}")
                
        except Exception as debug_e:
            log.error(f"Error checking scheduled job: {debug_e}", exc_info=True)
        
    except Exception as e:
        log.error(f"Failed to setup scheduled ScrapyCat job: {str(e)}")


def save_plugin_settings_to_file(settings: Dict[str, Any], plugin_path: str) -> Dict[str, Any]:
    """
    Save plugin settings to settings.json file in the plugin directory.
    This replicates the default save behavior from the Cat framework.
    
    Args:
        settings: The settings dictionary to save
        plugin_path: The path to the plugin directory
        
    Returns:
        The updated settings dictionary, or empty dict if save failed
    """
    settings_file_path: str = os.path.join(plugin_path, "settings.json")
    
    # Load already saved settings (replicate load_settings behavior)
    old_settings: Dict[str, Any] = {}
    if os.path.exists(settings_file_path):
        try:
            with open(settings_file_path, "r") as json_file:
                old_settings = json.load(json_file)
        except Exception as e:
            log.error(f"Unable to load existing settings: {e}")
    
    # Merge new settings with old ones
    updated_settings: Dict[str, Any] = {**old_settings, **settings}
    
    # Save settings to file
    try:
        with open(settings_file_path, "w") as json_file:
            json.dump(updated_settings, json_file, indent=4)
        return updated_settings
    except Exception as e:
        log.error(f"Unable to save plugin settings: {e}")
        return {}


@hook()
def after_cat_bootstrap(cat) -> None:
    """Hook called at Cat startup to schedule recurring jobs"""
    log.info("Setting up ScrapyCat scheduled jobs after Cat bootstrap")
    # The cat parameter here is CheshireCat during bootstrap
    setup_scrapycat_schedule(cat)


@plugin
def save_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Hook called when plugin settings are saved - reschedule jobs with new settings"""
    log.info(f"ScrapyCat settings saved, updating schedule")
    
    try:
        # Get the CheshireCat instance for scheduling capabilities
        from cat.looking_glass.cheshire_cat import CheshireCat
        cheshire_cat: CheshireCat = CheshireCat()
        
        # Update the schedule with new settings
        setup_scrapycat_schedule(cheshire_cat, settings)
        log.info("ScrapyCat schedule updated successfully")
            
    except Exception as e:
        log.error(f"Error updating ScrapyCat schedule during settings save: {e}")
    
    # Save settings using the extracted function
    plugin_path: str = os.path.dirname(os.path.abspath(__file__))
    return save_plugin_settings_to_file(settings, plugin_path)