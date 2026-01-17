from curl_cffi import requests


def parse_response(response: requests.Response) -> dict:
    return response.json()
