# -*- coding: utf-8 -*-
"""
A Kodi-agnostic library for Viaplay
"""
import codecs
import os
import cookielib
import calendar
import time
import re
import json
import uuid
import HTMLParser
from urllib import urlencode
from datetime import datetime, timedelta

import iso8601
import requests


class Viaplay(object):
    def __init__(self, settings_folder, country, debug=False):
        self.debug = debug
        self.country = country
        self.settings_folder = settings_folder
        self.cookie_jar = cookielib.LWPCookieJar(os.path.join(self.settings_folder, 'cookie_file'))
        self.tempdir = os.path.join(settings_folder, 'tmp')
        if not os.path.exists(self.tempdir):
            os.makedirs(self.tempdir)
        self.deviceid_file = os.path.join(settings_folder, 'deviceId')
        self.http_session = requests.Session()
        self.base_url = 'https://content.viaplay.%s/pc-%s' % (self.country, self.country)
        try:
            self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except IOError:
            pass
        self.http_session.cookies = self.cookie_jar

    class ViaplayError(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def log(self, string):
        if self.debug:
            try:
                print '[Viaplay]: %s' % string
            except UnicodeEncodeError:
                # we can't anticipate everything in unicode they might throw at
                # us, but we can handle a simple BOM
                bom = unicode(codecs.BOM_UTF8, 'utf8')
                print '[Viaplay]: %s' % string.replace(bom, '')
            except:
                pass

    def url_parser(self, url):
        """Sometimes, Viaplay adds some weird templated stuff to the URL
        we need to get rid of. Example: https://content.viaplay.se/androiddash-se/serier{?dtg}"""
        template = re.search(r'\{.+?\}', url)
        if template:
            url = url.replace(template.group(), '')

        return url

    def make_request(self, url, method, payload=None, headers=None):
        """Make an HTTP request. Return the JSON response in a dict."""
        self.log('URL: %s' % url)
        parsed_url = self.url_parser(url)
        if parsed_url != url:
            url = parsed_url
            self.log('Parsed URL: %s' % url)
        if method == 'get':
            req = self.http_session.get(url, params=payload, headers=headers, allow_redirects=False, verify=False)
        else:
            req = self.http_session.post(url, data=payload, headers=headers, allow_redirects=False, verify=False)
        self.log('Response code: %s' % req.status_code)
        self.log('Response: %s' % req.content)
        self.cookie_jar.save(ignore_discard=True, ignore_expires=False)

        return self.validate_response(req.content)

    def validate_response(self, response):
        response_dict = json.loads(response)
        try:
            if not response_dict['success']:
                raise self.ViaplayError(response_dict['name'].encode('utf-8'))
        except KeyError:
            pass

        return response_dict

    def get_activation_data(self):
        """Get activation data (reg code etc) needed to authorize the device."""
        url = 'https://login.viaplay.%s/api/device/code' % self.country
        payload = {
            'deviceKey': 'pc-%s' % self.country,
            'deviceId': self.get_deviceid()
        }

        return self.make_request(url=url, method='get', payload=payload)

    def authorize_device(self, activation_data):
        """Try to register the device. This will set the session cookies."""
        url = 'https://login.viaplay.%s/api/device/authorized' % self.country
        payload = {
            'deviceId': self.get_deviceid(),
            'deviceToken': activation_data['deviceToken'],
            'userCode': activation_data['userCode']
        }

        self.make_request(url=url, method='get', payload=payload)
        self.validate_session()  # we need this to validate the new cookies


    def validate_session(self):
        """Check if the session is valid."""
        url = 'https://login.viaplay.%s/api/persistentLogin/v1' % self.country
        payload = {
            'deviceKey': 'pc-%s' % self.country
        }
        self.make_request(url=url, method='get', payload=payload)

    def get_stream(self, guid, pincode=None):
        """Return a dict with the stream URL:s and available subtitle URL:s."""
        stream = {}
        url = 'https://play.viaplay.%s/api/stream/byguid' % self.country
        payload = {
            'deviceId': self.get_deviceid(),
            'deviceName': 'web',
            'deviceType': 'pc',
            'userAgent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:47.0) Gecko/20100101 Firefox/47.0',
            'deviceKey': 'pcdash-%s' % self.country,
            'guid': guid
        }
        if pincode:
            payload['pgPin'] = pincode

        data = self.make_request(url=url, method='get', payload=payload)
        if 'viaplay:media' in data['_links'].keys():
            mpd_url = data['_links']['viaplay:media']['href']
        elif 'viaplay:fallbackMedia' in data['_links'].keys():
            mpd_url = data['_links']['viaplay:fallbackMedia'][0]['href']
        elif 'viaplay:playlist' in data['_links'].keys():
            mpd_url = data['_links']['viaplay:playlist']['href']
        elif 'viaplay:encryptedPlaylist' in data['_links'].keys():
            mpd_url = data['_links']['viaplay:encryptedPlaylist']['href']
        else:
            self.log('Unable to retrieve stream URL.')
            return False

        stream['mpd_url'] = mpd_url
        # strip out template from license url
        stream['license_url'] = data['_links']['viaplay:license']['href'].replace('&_widevineChallenge={widevineChallenge}', '')
        stream['release_pid'] = data['_links']['viaplay:license']['releasePid']
        stream['subtitle_urls'] = self.get_subtitle_urls(data)

        return stream

    def format_license_post_data(self, release_pid, wv_challenge):
        self.log('release_pid: {0}'.format(release_pid))
        self.log('wv_challenge: {0}'.format(wv_challenge))

        post_data = {
            'getWidevineLicense': {
                'releasePid': release_pid,
                'widevineChallenge': wv_challenge
            }
        }

        return json.dumps(post_data)

    def get_categories(self, input, method=None):
        if method == 'data':
            data = input
        else:
            data = self.make_request(url=input, method='get')

        if data['pageType'] == 'root':
            categories = data['_links']['viaplay:sections']
        elif data['pageType'] == 'section':
            categories = data['_links']['viaplay:categoryFilters']

        return categories

    def get_sortings(self, url):
        data = self.make_request(url=url, method='get')
        try:
            sorttypes = data['_links']['viaplay:sortings']
        except KeyError:
            self.log('No sortings available for this category.')
            return None

        return sorttypes

    def get_letters(self, url):
        """Return a list of available letters for sorting in alphabetical order."""
        letters = []
        products = self.get_products(input=url, method='url')
        for item in products:
            letter = item['group'].encode('utf-8')
            if letter not in letters:
                letters.append(letter)

        return letters

    def get_products(self, input, method=None, filter_event=False):
        """Return a list of all available products."""
        if method == 'data':
            data = input
        else:
            data = self.make_request(url=input, method='get')

        if 'list' in data['type']:
            products = data['_embedded']['viaplay:products']
        elif data['type'] == 'product':
            products = data['_embedded']['viaplay:product']
        else:
            products = self.get_products_block(data)['_embedded']['viaplay:products']

        try:
            # try adding additional info to sports dict
            aproducts = []
            for product in products:
                if product['type'] == 'sport':
                    product['event_date'] = self.parse_datetime(product['epg']['start'], localize=True)
                    product['event_status'] = self.get_event_status(product)
                aproducts.append(product)
            products = aproducts
        except TypeError:
            pass

        if filter_event:
            fproducts = []
            for product in products:
                for event in filter_event:
                    if event == product['event_status']:
                        fproducts.append(product)
            products = fproducts

        return products

    def get_seasons(self, url):
        """Return all available series seasons as a list."""
        seasons = []
        data = self.make_request(url=url, method='get')

        items = data['_embedded']['viaplay:blocks']
        for item in items:
            if item['type'] == 'season-list':
                seasons.append(item)

        return seasons

    def get_subtitle_urls(self, data):
        """Return all subtitle SAMI URL:s in a list."""
        subtitle_urls = []
        try:
            for subtitle in data['_links']['viaplay:sami']:
                subtitle_urls.append(subtitle['href'])
        except KeyError:
            self.log('No subtitles found for guid: %s' % data['socket2']['productGuid'])

        return subtitle_urls

    def download_subtitles(self, suburls):
        """Download the SAMI subtitles, decode the HTML entities and save to temp directory.
        Return a list of the path to the downloaded subtitles."""
        subtitle_paths = []
        for suburl in suburls:
            req = requests.get(suburl)
            sami = req.content.decode('utf-8', 'ignore').strip()
            htmlparser = HTMLParser.HTMLParser()
            subtitle = htmlparser.unescape(sami).encode('utf-8')
            subtitle = subtitle.replace('  ', ' ')  # replace two spaces with one

            subpattern = re.search(r'[_]([a-z]+)', suburl)
            if subpattern:
                sublang = subpattern.group(1)
            else:
                sublang = 'unknown'
                self.log('Unable to identify subtitle language.')

            path = os.path.join(self.tempdir, '%s.sami') % sublang
            with open(path, 'w') as subfile:
                subfile.write(subtitle)
            subtitle_paths.append(path)

        return subtitle_paths

    def get_deviceid(self):
        """"Read/write deviceId (generated UUID4) from/to file and return it."""
        try:
            with open(self.deviceid_file, 'r') as deviceid:
                return deviceid.read()
        except IOError:
            deviceid = str(uuid.uuid4())
            with open(self.deviceid_file, 'w') as idfile:
                idfile.write(deviceid)
            return deviceid

    def get_event_status(self, data):
        """Return whether the event is live/upcoming/archive."""
        now = datetime.utcnow()
        producttime_start = self.parse_datetime(data['epg']['start'])
        producttime_start = producttime_start.replace(tzinfo=None)
        if 'isLive' in data['system']['flags']:
            status = 'live'
        elif producttime_start >= now:
            status = 'upcoming'
        else:
            status = 'archive'

        return status

    def get_sports_dates(self, url, event_date=None):
        """Return the available sports dates.
        Filter upcoming/previous dates with the event_date parameter."""
        dates = []
        data = self.make_request(url=url, method='get')
        dates_data = data['_links']['viaplay:days']
        now = datetime.now()

        for date in dates_data:
            date_obj = datetime(*(time.strptime(date['date'], '%Y-%m-%d')[0:6]))  # http://forum.kodi.tv/showthread.php?tid=112916
            if event_date == 'upcoming':
                if date_obj.date() > now.date():
                    dates.append(date)
            elif event_date == 'archive':
                if date_obj.date() < now.date():
                    dates.append(date)
            else:
                dates.append(date)

        return dates

    def get_next_page(self, data):
        """Return the URL to the next page if the current page count is less than the total page count."""
        # first page is always (?) from viaplay:blocks
        if data['type'] == 'page':
            data = self.get_products_block(data)
        if int(data['pageCount']) > int(data['currentPage']):
            next_page_url = data['_links']['next']['href']
            return next_page_url

    def get_products_block(self, data):
        """Get the viaplay:blocks containing all product information."""
        blocks = []
        blocks_data = data['_embedded']['viaplay:blocks']
        for block in blocks_data:
            # example: https://content.viaplay.se/pc-se/sport
            if 'viaplay:products' in block['_embedded'].keys():
                blocks.append(block)
        return blocks[-1]  # the last block is always (?) the right one

    def utc_to_local(self, utc_dt):
        # get integer timestamp to avoid precision lost
        timestamp = calendar.timegm(utc_dt.timetuple())
        local_dt = datetime.fromtimestamp(timestamp)
        assert utc_dt.resolution >= timedelta(microseconds=1)
        return local_dt.replace(microsecond=utc_dt.microsecond)

    def parse_datetime(self, iso8601_string, localize=False):
        """Parse ISO8601 string to datetime object."""
        datetime_obj = iso8601.parse_date(iso8601_string)
        if localize:
            return self.utc_to_local(datetime_obj)
        else:
            return datetime_obj
