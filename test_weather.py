import requests

def get_weather(city):
    try:
        url = f"https://wttr.in/{city}?format=j1"
        r = requests.get(url, timeout=10)
        data = r.json()

        current = data['current_condition'][0]
        temp = current['temp_C']
        desc = current['weatherDesc'][0]['value']

        # Forecast for next day
        tomorrow = data['weather'][1]
        t_max = tomorrow['maxtempC']
        t_min = tomorrow['mintempC']

        print(f"[WEATHER] {city.capitalize()}")
        print(f"• Now: {temp}°C, {desc}")
        print(f"• 24h: {t_min}°C-{t_max}°C")
    except Exception as e:
        print("Error", e)

get_weather('Warsaw')
