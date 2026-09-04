import os
import dotenv

class EnvLoadUtil:
    
    ALL_KMB_ROUTER_URL = "https://data.etabus.gov.hk/v1/transport/kmb/route/"
    KMB_ROUTER_ETA_URL = "https://data.etabus.gov.hk/v1/transport/kmb/stop-eta/{stop_id}"
    KMB_STOP_URL = "https://data.etabus.gov.hk/v1/transport/kmb/stop"
    KMB_ETA_ROUTE_URL = "https://data.etabus.gov.hk/v1/transport/kmb/route-stop/{route}/{direction}/{service_type}"
    KMB_ROUTE_ETA_URL = "https://data.etabus.gov.hk/v1/transport/kmb/route-eta/{route}/{service_type}"
    HKO_WEATHER_URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType={data_type}&lang={lang}"
    HKO_TIDE_URL = "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=HLT&station={station}&year={year}&rformat=csv"
    HOLIDAYS_URL = "https://www.1823.gov.hk/common/ical/{lang}.json"
    AQHI_RSS_URL = "https://www.aqhi.gov.hk/epd/ddata/html/out/aqhi_ind_rss_Eng.xml"

    @staticmethod
    def load_env(key: str, default: str = None):
        dotenv.load_dotenv()
        return os.getenv(key, "") if default is None else os.getenv(key, default)
        
    @staticmethod
    def get_env_config_dict() -> dict:
        dotenv.load_dotenv()
        config = {}
        for key, value in os.environ.items():
            config[key] = value

        return config
    