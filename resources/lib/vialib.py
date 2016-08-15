# -*- coding: utf-8 -*-
"""
A Kodi-agnostic library for Viaplay
"""
import codecs
import os
import cookielib
from datetime import datetime
import re
import json
import uuid
import HTMLParser

import dateutil.parser
import requests


class vialib(object):
    def __init__(self, username, password, cookie_file, deviceid_file, tempdir, country, disable_ssl, debug=False):
        self.debug = debug
        self.username = username
        self.password = password
        self.country = country
        self.disable_ssl = disable_ssl
        self.deviceid_file = deviceid_file
        self.tempdir = tempdir
        self.base_url = 'https://content.viaplay.%s/pc-%s' % (country, country)
        self.http_session = requests.Session()
        self.cookie_jar = cookielib.LWPCookieJar(cookie_file)
        try:
            self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except IOError:
            pass
        self.http_session.cookies = self.cookie_jar      

    class LoginFailure(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    class AuthFailure(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def log(self, string):
        if self.debug:
            try:
                print '[vialib]: %s' % string
            except UnicodeEncodeError:
                # we can't anticipate everything in unicode they might throw at
                # us, but we can handle a simple BOM
                bom = unicode(codecs.BOM_UTF8, 'utf8')
                print '[vialib]: %s' % string.replace(bom, '')
            except:
                pass

    def url_parser(self, url):
        """Sometimes, Viaplay adds some weird templated stuff to the URL
        we need to get rid of. Example: https://content.viaplay.se/androiddash-se/serier{?dtg}"""
        if self.disable_ssl:
            url = url.replace('https', 'http')  # http://forum.kodi.tv/showthread.php?tid=270336
        template = re.search(r'\{.+?\}', url)
        if template is not None:
            url = url.replace(template.group(), '')

        return url

    def make_request(self, url, method, payload=None, headers=None):
        """Make an HTTP request. Return the response as JSON."""
        parsed_url = self.url_parser(url)
        self.log('URL: %s' % url)
        if parsed_url != url:
            self.log('Parsed URL: %s' % parsed_url)

        if method == 'get':
            req = self.http_session.get(parsed_url, params=payload, headers=headers, allow_redirects=False,
                                        verify=False)
        else:
            req = self.http_session.post(parsed_url, data=payload, headers=headers, allow_redirects=False, verify=False)
        self.log('Response code: %s' % req.status_code)
        self.log('Response: %s' % req.content)
        self.cookie_jar.save(ignore_discard=True, ignore_expires=False)

        return json.loads(req.content)

    def login(self, username, password):
        """Login to Viaplay. Return True/False based on the result."""
        url = 'https://login.viaplay.%s/api/login/v1' % self.country
        payload = {
            'deviceKey': 'pc-%s' % self.country,
            'username': username,
            'password': password,
            'persistent': 'true'
        }
        data = self.make_request(url=url, method='get', payload=payload)
        if data['success'] is False:
            return False
        else:
            return True

    def validate_session(self):
        """Check if our session cookies are still valid."""
        url = 'https://login.viaplay.%s/api/persistentLogin/v1' % self.country
        payload = {
            'deviceKey': 'pc-%s' % self.country
        }
        data = self.make_request(url=url, method='get', payload=payload)
        if data['success'] is False:
            return False
        else:
            return True

    def verify_login(self, data):
        try:
            if data['name'] == 'MissingSessionCookieError':
                login_success = self.validate_session()
                if login_success is False:
                    login_success = self.login(self.username, self.password)
                    if login_success is False:
                        raise self.LoginFailure('login failed')
            else:
                login_success = True
        except KeyError:
            login_success = True

        return login_success

    def get_video_urls(self, guid):
        """Return a dict with the stream URL and available subtitle URL:s."""
        video_urls = {}
        url = 'https://play.viaplay.%s/api/stream/byguid' % self.country
        payload = {
            'deviceId': self.get_deviceid(),
            'deviceName': 'web',
            'deviceType': 'pc',
            'userAgent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:47.0) Gecko/20100101 Firefox/47.0',
            'deviceKey': 'pchls-%s' % self.country,
            'guid': guid
        }

        data = self.make_request(url=url, method='get', payload=payload)
        login_status = self.verify_login(data)
        if login_status is True:
            try:
                m3u8_url = data['_links']['viaplay:playlist']['href']
                success = True
            except KeyError:
                # we might have to request the stream again after logging in
                if data['name'] == 'MissingSessionCookieError':
                    data = self.make_request(url=url, method='get', payload=payload)
                try:
                    m3u8_url = data['_links']['viaplay:playlist']['href']
                    success = True
                except KeyError:
                    if data['success'] is False:
                        raise self.AuthFailure(data['name'])
            if success:
                video_urls['stream_url'] = m3u8_url
                video_urls['subtitle_urls'] = self.get_subtitle_urls(data, guid)

                return video_urls

    def get_categories(self, input, method=None):
        if method == 'data':
            data = input
        else:
            data = self.make_request(url=input, method='get')

        pageType = data['pageType']
        try:
            sectionType = data['sectionType']
        except KeyError:
            sectionType = None
        if sectionType == 'sportPerDay':
            categories = data['_links']['viaplay:days']
        elif pageType == 'root':
            categories = data['_links']['viaplay:sections']
        elif pageType == 'section':
            categories = data['_links']['viaplay:categoryFilters']

        return categories

    def get_sortings(self, url):
        data = self.make_request(url=url, method='get')
        sorttypes = data['_links']['viaplay:sortings']

        return sorttypes

    def get_letters(self, url):
        """Return a list of available letters for sorting in alphabetical order."""
        letters = []
        products = self.get_products(input=url, method='url')
        for item in products:
            letter = item['group']
            if letter not in letters:
                letters.append(letter)

        return letters

    def get_products(self, input, method=None):
        if method == 'data':
            data = input
        else:
            data = self.make_request(url=input, method='get')

        if data['type'] == 'season-list' or data['type'] == 'list':
            products = data['_embedded']['viaplay:products']
        elif data['type'] == 'product':
            products = data['_embedded']['viaplay:product']
        else:
            try:
                products = data['_embedded']['viaplay:blocks'][0]['_embedded']['viaplay:products']
            except KeyError:
                products = data['_embedded']['viaplay:blocks'][1]['_embedded']['viaplay:products']

        return products

    def get_seasons(self, url):
        """Return all available series seasons as a list."""
        data = self.make_request(url=url, method='get')
        seasons = []

        items = data['_embedded']['viaplay:blocks']
        for item in items:
            if item['type'] == 'season-list':
                seasons.append(item)

        return seasons

    def get_subtitle_urls(self, data, guid):
        """Return all subtitle SAMI URL:s in a list."""
        subtitle_urls = []
        try:
            for subtitle in data['_links']['viaplay:sami']:
                subtitle_urls.append(subtitle['href'])
        except KeyError:
            self.log('No subtitles found for guid %s' % guid)

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

            if '_sv' in suburl:
                path = os.path.join(self.tempdir, 'swe.smi')
            elif '_no' in suburl:
                path = os.path.join(self.tempdir, 'nor.smi')
            elif '_da' in suburl:
                path = os.path.join(self.tempdir, 'dan.smi')
            elif '_fi' in suburl:
                path = os.path.join(self.tempdir, 'fin.smi')
            f = open(path, 'w')
            f.write(subtitle)
            f.close()
            subtitle_paths.append(path)

        return subtitle_paths

    def get_deviceid(self):
        """"Read/write deviceId (generated UUID4) from/to file and return it."""
        try:
            deviceid = open(self.deviceid_file, 'r').read()
            return deviceid
        except IOError:
            deviceid = str(uuid.uuid4())
            fhandle = open(self.deviceid_file, 'w')
            fhandle.write(deviceid)
            fhandle.close()
            return deviceid

    def get_sports_status(self, data):
        """Return whether the event is live/upcoming/archive."""
        now = datetime.utcnow()
        producttime_start = dateutil.parser.parse(data['epg']['start'])
        producttime_start = producttime_start.replace(tzinfo=None)
        if 'isLive' in data['system']['flags']:
            status = 'live'
        elif producttime_start >= now:
            status = 'upcoming'
        else:
            status = 'archive'

        return status
