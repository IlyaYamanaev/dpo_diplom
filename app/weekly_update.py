import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from parsers.general_parser import run_all_parse
from filtration import normalize_all_courses, classify_all_courses
from db_functions import clear_buffer_db, replace_production_data


PROD_DB = "dpo_db"
BUFFER_DB = "buff_dpo_db"


def weekly_update_job():

   logging.info("=== START WEEKLY UPDATE ===")

   try:
      clear_buffer_db()

      run_all_parse(BUFFER_DB)

      normalize_all_courses(BUFFER_DB)

      classify_all_courses(BUFFER_DB)

      replace_production_data()

      logging.info("=== SUCCESS ===")

   except Exception as e:
      logging.exception(f"UPDATE FAILED: {e}")


def start_scheduler():

   scheduler = BackgroundScheduler(
      timezone="Europe/Moscow"
   )

   scheduler.add_job(
      weekly_update_job,
      CronTrigger(
         day_of_week="sun",
         hour=0,
         minute=0
      ),
      id="weekly_course_update",
      replace_existing=True,
   )

   scheduler.start()

   return scheduler

if __name__ == "__main__":
   print("all good.")