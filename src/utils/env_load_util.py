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
    MTR_SCHEDULE_URL = "https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php?line={line}&sta={sta}"
    HKKF_BASE_URL = "https://www.hkkfeta.com"
    SUNFERRY_ETA_URL = "https://www.sunferry.com.hk/eta/?route={route_code}"

    @staticmethod
    def load_env(key: str, default: str = None):
        dotenv.load_dotenv()
        return os.getenv(key, "") if default is None else os.getenv(key, default)

    @staticmethod
    def res_path(filename: str) -> str:
        """Resolve a file in res/ — independent of the process working directory.

        Uses BASE_FOLDER when set; otherwise derives the repo root from this
        file's location (src/utils/ -> repo root), so the MCP server and the
        REST app work no matter which directory a host launches them from.
        """
        base_folder = EnvLoadUtil.load_env("BASE_FOLDER")
        if not base_folder:
            base_folder = os.path.abspath(
                os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
        return os.path.normpath(os.path.join(base_folder, "res", filename))
        
    @staticmethod
    def get_env_config_dict() -> dict:
        dotenv.load_dotenv()
        config = {}
        for key, value in os.environ.items():
            config[key] = value

        return config
    