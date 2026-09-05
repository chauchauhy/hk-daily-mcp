from pydantic import BaseModel

# {
#     "generalSituation": "東北季候風正影響廣東。此外，一道雲帶覆蓋沿岸地區及南海北部。",
#     "tcInfo": "",
#     "fireDangerWarning": "",
#     "forecastPeriod": "本港地區今晚及明日天氣預測",
#     "forecastDesc": "大致多雲。明早清涼，市區最低氣溫約16度，新界再低一兩度，日間短暫時間有陽光及乾燥，最高氣溫約21度。吹和緩至清勁東北風。",
#     "outlook": "年初三早上清涼，風勢頗大，日間短暫時間有陽光。隨後兩三日日間溫暖。",
#     "updateTime": "2026-02-17T19:45:00+08:00"
# }

class HkoFLWResponse(BaseModel):
    generalSituation: str
    tcInfo: str
    fireDangerWarning: str
    forecastPeriod: str
    forecastDesc: str
    outlook: str
    updateTime: str