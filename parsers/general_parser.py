from parsers.parser_hse import main_hse
from parsers.parser_kpfu import main_kpfu
from parsers.parser_netalogia import main_netalogia
from parsers.parser_ranepa import main_ranepa
from parsers.parser_bfu import main_bfu
from parsers.parser_dvfu import main_dvfu
from parsers.parser_spbgu import main_spbgu
from parsers.parser_yandex_practic import main_yandex_practic
from parsers.parser_safu import main_safu
from parsers.parser_skfu import main_skfu

DB_NAME = "buff_dpo_db"

def run_all_parse(DB_NAME):
   main_hse(DB_NAME)
   main_kpfu(DB_NAME)
   main_netalogia(DB_NAME)
   main_ranepa(DB_NAME)
   main_dvfu(DB_NAME)
   main_bfu(DB_NAME)
   main_spbgu(DB_NAME)
   main_yandex_practic(DB_NAME)
   main_safu(DB_NAME)
   main_skfu(DB_NAME)
   
   
if __name__ == "__main__":
   run_all_parse(DB_NAME)