from typing import Dict, Any, Optional
from .base import BotPlugin

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

class WeatherPlugin(BotPlugin):
    @property
    def commands(self) -> list[str]:
        return ['weather', 'pogoda']

    def handle(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool, bot: Any) -> Optional[Dict[str, Any]]:
        city = args.strip() if args else "Warsaw"
        if not city:
            city = "Warsaw"
        if not _HAS_REQUESTS:
            response = "[WEATHER] Error: requests library not available."
            return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}
        try:
            import urllib.parse
            safe_city = urllib.parse.quote_plus(city)
            url = f"https://wttr.in/{safe_city}?format=j1"
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()

            # Using safe `.get()` to avoid KeyErrors
            current_condition = data.get('current_condition', [{}])[0]
            weather_desc = current_condition.get('weatherDesc', [{'value': 'Unknown'}])[0].get('value', 'Unknown')
            temp = current_condition.get('temp_C', '?')

            # Use tomorrow's forecast like original code: data['weather'][1] (if available)
            weather_forecasts = data.get('weather', [])
            if len(weather_forecasts) > 1:
                tomorrow = weather_forecasts[1]
                tmax = tomorrow.get('maxtempC', '?')
                tmin = tomorrow.get('mintempC', '?')
            else:
                # Fallback to today if tomorrow isn't there
                today = weather_forecasts[0] if weather_forecasts else {}
                tmax = today.get('maxtempC', '?')
                tmin = today.get('mintempC', '?')

            desc = weather_desc
            if len(desc) > 15:
                desc = desc[:12] + "..."

            response = (f"[WEATHER] {city.capitalize()}\n"
                        f"• Now: {temp}°C, {desc}\n"
                        f"• 24h: {tmin}°C-{tmax}°C")
        except Exception as e:
            response = f"[WEATHER] Error: {str(e)[:60]}"

        return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}
