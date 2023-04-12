import os
import requests
import singer.metrics as metrics
from datetime import datetime


session = requests.Session()


class AuthException(Exception):
    pass


class NotFoundException(Exception):
    pass


# constants
baseUrl = "https://app.signonsite.com.au/api/public"
per_page = 2000  # this is the max that the API allows


def get_page(source, url, start=0, offset=0):
    with metrics.http_request_timer(source) as timer:
        session.headers.update()
        resp = session.request(
            method="get",
            url=f"{baseUrl}{url}?offset={offset}&limit={per_page}",
        )
        if resp.status_code == 401:
            raise AuthException(resp.text)
        if resp.status_code == 403:
            raise AuthException(resp.text)
        if resp.status_code == 404:
            raise NotFoundException(resp.text)

        timer.tags[metrics.Tag.http_status_code] = resp.status_code
        return resp


def get_all_pages(source, url, start=0):
    offset = 0

    # blank bookmark can come through as None, which isn't caught by default value for start, so backend API throws an error
    if start == None:
        start = 0

    while True:
        r = get_page(source, url, start, offset)
        # throw exception if not 200
        r.raise_for_status()
        json = r.json()
        yield json
        if json["last_page"] > json["current_page"]:
            offset = json["current_page"] * per_page
        else:
            break


def formatDate(dt):
    return datetime.strftime(dt, "%Y-%m-%dT%H:%M:%S")


def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)
