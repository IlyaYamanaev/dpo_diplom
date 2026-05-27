from parser_hse import main_hse
from parser_kpfu import main_kpfu
from parser_netalogia import main_netalogia
from parser_ranepa import main_ranepa
from parser_bfu import main_bfu
from parser_dvfu import main_dvfu
from parser_spbgu import main_spbgu
from parser_yandex_practic import main_yandex_practic

DB_NAME = "buff_dpo_db"


if __name__ == "__main__":
   main_hse(DB_NAME)
   main_kpfu(DB_NAME)
   main_netalogia(DB_NAME)
   main_ranepa(DB_NAME)
   main_dvfu(DB_NAME)
   main_bfu(DB_NAME)
   main_spbgu(DB_NAME)
   main_yandex_practic(DB_NAME)