import responses

from surfwa.fetch.buienradar import FEED_URL, coastal_wind


@responses.activate
def test_coastal_wind_returns_only_coastal_station_winds():
    responses.get(
        FEED_URL,
        json={
            "actual": {
                "stationmeasurements": [
                    {
                        "stationname": "Meetstation IJmuiden",
                        "windspeedBft": 5,
                        "winddirection": "WZW",
                    },
                    {
                        "stationname": "Meetstation De Bilt",
                        "windspeedBft": 2,
                        "winddirection": "Z",
                    },
                    {
                        "stationname": "Meetstation Hoek van Holland",
                        "windspeedBft": 4,
                        "winddirection": "W",
                    },
                ]
            }
        },
    )

    assert coastal_wind() == {"IJmuiden": (5, "WZW"), "Hoek van Holland": (4, "W")}
