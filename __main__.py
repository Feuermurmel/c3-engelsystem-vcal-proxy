import html
import logging
import os
import re
import wsgiref.util
import wsgiref.simple_server
import wsgiref.handlers
from urllib.parse import urlsplit, parse_qs, urlunsplit, \
    urlencode

import bs4
import requests
from datetime import date, timedelta, datetime, time

from pytz import timezone


tzinfo = timezone('Europe/Berlin')


base_url = 'https://engelsystem.de/33c3/?p=user_shifts&start_day=2016-12-26&start_time=00%3A00&end_day=2016-12-26&end_time=23%3A59&rooms%5B%5D=60&rooms%5B%5D=50&rooms%5B%5D=10&rooms%5B%5D=6&rooms%5B%5D=17&rooms%5B%5D=46&rooms%5B%5D=49&rooms%5B%5D=11&rooms%5B%5D=52&rooms%5B%5D=53&rooms%5B%5D=58&rooms%5B%5D=55&rooms%5B%5D=57&rooms%5B%5D=54&rooms%5B%5D=47&rooms%5B%5D=48&rooms%5B%5D=5&rooms%5B%5D=8&rooms%5B%5D=40&rooms%5B%5D=41&rooms%5B%5D=56&rooms%5B%5D=9&rooms%5B%5D=15&rooms%5B%5D=16&rooms%5B%5D=4&rooms%5B%5D=7&rooms%5B%5D=63&rooms%5B%5D=59&rooms%5B%5D=44&rooms%5B%5D=45&rooms%5B%5D=33&rooms%5B%5D=61&rooms%5B%5D=62&rooms%5B%5D=42&rooms%5B%5D=43&types%5B%5D=4&types%5B%5D=41&types%5B%5D=9&filled%5B%5D=0'


def get_shifts(soup: bs4.BeautifulSoup, day):
    shift_divs = soup.find_all('div', class_='shift')

    def iter_shifts():
        for i in shift_divs:
            heading = html.unescape(i.find(class_='panel-heading').text.strip())
            room = html.unescape(i.find(class_='panel-body').find('a').text.strip())

            heading_match = re.match(
                '([0-9]+):([0-9]+) ‐ ([0-9]+):([0-9]+) — (.*)$',
                heading)

            start_time = time(
                hour=int(heading_match.group(1)),
                minute=int(heading_match.group(2)))

            end_time = time(
                hour=int(heading_match.group(3)),
                minute=int(heading_match.group(4)))

            description = heading_match.group(5)

            yield tzinfo.localize(datetime.combine(day, start_time)), tzinfo.localize(datetime.combine(day, end_time)), description, room

    return list(iter_shifts())


def get_shifts_for_date(session: requests.Session, day: date):
    url_parts = urlsplit(base_url)
    query = parse_qs(url_parts.query)

    query['start_day'] = query['end_day'] = [day.strftime('%Y-%m-%d')]
    query['start_time'] = ['00:00']
    query['end_time'] = ['23:59']

    url = urlunsplit(url_parts._replace(query=urlencode([(k, i) for k, v in query.items() for i in v])))
    response = session.get(url)

    soup = bs4.BeautifulSoup(response.text, 'html.parser')

    return get_shifts(soup, day)


def date_range(start: date, end: date):
    while start < end:
        yield start

        start += timedelta(days=1)


def get_all_shifts():
    session = requests.session()
    pw = open('pw.txt', 'r', encoding='utf-8').read().strip()

    session.post(
        'https://engelsystem.de/33c3/?p=login',
        dict(nick='Feuermurmel', password=pw, submit='Login'))

    today = datetime.now(tzinfo).date()

    return [
        j 
        for i in date_range(today, date(2017, 1, 1)) for
        j in get_shifts_for_date(session, i)]


class Event:
    def __init__(self, start: datetime, end: datetime,
            title: str, location: str, notes: str):
        self.start = start
        self.end = end
        self.title = title
        self.location = location
        self.notes = notes
    
    def iter_lines(self):
        yield 'BEGIN:VEVENT'
        yield 'DTSTART:{}'.format(self._encode_time(self.start))
        yield 'DTEND:{}'.format(self._encode_time(self.end))
        yield 'SUMMARY:{}'.format(self._encode_string(self.title))
        yield 'LOCATION:{}'.format(self._encode_string(self.location))
        yield 'DESCRIPTION:{}'.format(self._encode_string(self.notes))
        yield 'END:VEVENT'
    
    @classmethod
    def _encode_time(cls, value: datetime):
        return value.strftime('%Y%m%dT%H%M%SZ')
    
    @classmethod
    def _encode_string(cls, value: str):
        return re.sub('([\\\\\n,;])', '\\\\\\1', value)


class Calendar:
    def __init__(self, events: list):
        self.events = events
    
    def iter_lines(self):
        yield 'BEGIN:VCALENDAR'
        yield 'VERSION:2.0'
        yield 'CALSCALE:GREGORIAN'
        
        for i in self.events:
            yield from i.iter_lines()
        
        yield 'END:VCALENDAR'


def get_vcal():
    calender = Calendar(
        [
            Event(start_time, end_time, description, room, '')
            for start_time, end_time, description, room in get_all_shifts()])
    
    return ''.join(i + '\n' for i in calender.iter_lines())


def app(environ, start_response):
    wsgiref.util.setup_testing_defaults(environ)
    
    start_response(
        '200 OK',
        [('content-type', 'text/calendar; charset=utf-8')])
    
    return [get_vcal().encode()]


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("requests.packages.urllib3").setLevel(logging.DEBUG)
    
    if 'PATH_INFO' in os.environ:
        wsgiref.handlers.CGIHandler().run(app)
    else:
        httpd = wsgiref.simple_server.make_server('', 8000, app)
        logging.info("Serving on port 8000...")
        httpd.serve_forever()


main()
