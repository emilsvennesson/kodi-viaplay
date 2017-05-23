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
from collections import OrderedDict
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
        self.device_key = 'xdk-%s' % self.country
        self.base_url = 'https://content.viaplay.{0}/{1}'.format(self.country, self.device_key)
        self.login_api = 'https://login.viaplay.%s/api' % self.country
        self.vod_pages = ['series', 'movie', 'kids', 'rental']
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

    def parse_url(self, url):
        """Sometimes, Viaplay adds some weird templated stuff to the URL
        we need to get rid of. Example: https://content.viaplay.se/androiddash-se/serier{?dtg}"""
        template = r'\{.+?\}'
        result = re.search(template, url)
        if result:
            self.log('Unparsed URL: {0}'.format(url))
            url = re.sub(template, '', url)

        return url

    def make_request(self, url, method, params=None, payload=None, headers=None):
        """Make an HTTP request. Return the response."""
        url = self.parse_url(url)
        self.log('Request URL: %s' % url)
        self.log('Method: %s' % method)
        if params:
            self.log('Params: %s' % params)
        if payload:
            self.log('Payload: %s' % payload)
        if headers:
            self.log('Headers: %s' % headers)

        if method == 'get':
            req = self.http_session.get(url, params=params, headers=headers)
        elif method == 'put':
            req = self.http_session.put(url, params=params, data=payload, headers=headers)
        else:  # post
            req = self.http_session.post(url, params=params, data=payload, headers=headers)
        self.log('Response code: %s' % req.status_code)
        self.log('Response: %s' % req.content)
        self.cookie_jar.save(ignore_discard=True, ignore_expires=False)

        return self.parse_response(req.content)

    def parse_response(self, response):
        """Try to load JSON data into dict and raise potential errors."""
        try:
            response = json.loads(response, object_pairs_hook=OrderedDict)  # keep the key order
            if 'success' in response.keys() and not response['success']:  # raise ViaplayError when 'success' is False
                raise self.ViaplayError(response['name'].encode('utf-8'))
        except ValueError:  # if response is not json
            pass

        return response

    def get_activation_data(self):
        """Get activation data (reg code etc) needed to authorize the device."""
        url = self.login_api + '/device/code'
        params = {
            'deviceKey': self.device_key,
            'deviceId': self.get_deviceid()
        }

        return self.make_request(url=url, method='get', params=params)

    def authorize_device(self, activation_data):
        """Try to register the device. This will set the session cookies."""
        url = self.login_api + '/device/authorized'
        params = {
            'deviceId': self.get_deviceid(),
            'deviceToken': activation_data['deviceToken'],
            'userCode': activation_data['userCode']
        }

        self.make_request(url=url, method='get', params=params)
        self.validate_session()  # we need this to validate the new cookies
        time.sleep(3)  # sleep to make sure session has been registred before next request

    def validate_session(self):
        """Check if the session is valid."""
        url = self.login_api + '/persistentLogin/v1'
        params = {
            'deviceKey': self.device_key
        }
        self.make_request(url=url, method='get', params=params)

    def log_out(self):
        """Log out from Viaplay."""
        url = self.login_api + '/logout/v1'
        params = {
            'deviceKey': self.device_key
        }
        self.make_request(url=url, method='get', params=params)

    def get_stream(self, guid, pincode=None):
        """Return a dict with the stream URL:s and available subtitle URL:s."""
        stream = {}
        url = 'https://play.viaplay.%s/api/stream/byguid' % self.country
        params = {
            'deviceId': self.get_deviceid(),
            'deviceName': 'web',
            'deviceType': 'pc',
            'userAgent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:47.0) Gecko/20100101 Firefox/47.0',
            'deviceKey': 'pcdash-%s' % self.country,
            'guid': guid
        }
        if pincode:
            payload['pgPin'] = pincode

        data = self.make_request(url=url, method='get', params=params)
        if 'viaplay:media' in data['_links'].keys():
            mpd_url = data['_links']['viaplay:media']['href']
        elif 'viaplay:fallbackMedia' in data['_links'].keys():
            mpd_url = data['_links']['viaplay:fallbackMedia'][0]['href']
        elif 'viaplay:playlist' in data['_links'].keys():
            mpd_url = data['_links']['viaplay:playlist']['href']
        elif 'viaplay:encryptedPlaylist' in data['_links'].keys():
            mpd_url = data['_links']['viaplay:encryptedPlaylist']['href']
        else:
            self.log('Failed to retrieve stream URL.')
            return False

        stream['mpd_url'] = mpd_url
        stream['license_url'] = data['_links']['viaplay:license']['href']
        stream['release_pid'] = data['_links']['viaplay:license']['releasePid']
        if 'viaplay:sami' in data['_links'].keys():
            stream['subtitles'] = [x['href'] for x in data['_links']['viaplay:sami']]

        return stream

    def get_root_page(self):
        """Dynamically builds the root page from the returned _links.
        Uses the named dict as 'id' when no 'id' exists in the dict."""
        pages = []
        data = self.make_request(url=self.base_url, method='get')
        if not 'user' in data.keys():
            raise self.ViaplayError('MissingSessionCookieError')  # raise error if user is not logged in

        for link in data['_links']:
            if isinstance(data['_links'][link], dict):
                # sort out _links that doesn't contain a title
                if 'title' in data['_links'][link].keys() and not data['_links'][link]['title'].islower():
                    data['_links'][link]['id'] = link  # add the dict name as the 'id' tag
                    pages.append(data['_links'][link])
            else:  # list (viaplay:sections for example)
                for i in data['_links'][link]:
                    if 'title' in i.keys() and not i['title'].islower():
                        pages.append(i)

        return pages

    def get_collections(self, url):
        """Return all available collections."""
        data = self.make_request(url=url, method='get')
        # return all blocks (collections) with 'list' in type
        return [x for x in data['_embedded']['viaplay:blocks'] if 'list' in x['type'].lower()]

    def get_products(self, url, filter_event=False, search_query=None):
        """Return a dict containing the products and next page if available."""
        if search_query:
            params = {'query': search_query}
        else:
            params = None
        data = self.make_request(url, method='get', params=params)

        if 'list' in data['type'].lower():
            products = data['_embedded']['viaplay:products']
        elif data['type'] == 'product':
            products = data['_embedded']['viaplay:product']
        elif data.get('sectionType') == 'sportPerDay':
            # products are separated in different viaplay:blocks - collect them all
            products = [p for x in data['_embedded']['viaplay:blocks'] for p in x['_embedded']['viaplay:products']]
        else:
            products = self.get_products_block(data)['_embedded']['viaplay:products']

        # add additional info to sports products
        if isinstance(products, list):  # viaplay:product is not a list
            for product in products:
                if product.get('type') == 'sport':
                    product['event_date'] = self.parse_datetime(product['epg']['start'], localize=True)
                    product['event_status'] = self.get_event_status(product)

        if filter_event:
            # filter out and only return products with event_status in filter_event
            products = [x for x in products if x['event_status'] in filter_event]

        products_dict = {
            'products': products,
            'next_page': self.get_next_page(data)
        }

        return products_dict

    def get_seasons(self, url):
        """Return all available series seasons."""
        data = self.make_request(url=url, method='get')
        return [x for x in data['_embedded']['viaplay:blocks'] if x['type'] == 'season-list']

    def download_subtitles(self, suburls):
        """Download the SAMI subtitles, decode the HTML entities and save to temp directory.
        Return a list of the path to the downloaded subtitles."""
        paths = []
        for url in suburls:
            sami = self.make_request(url=url, method='get').decode('utf-8', 'ignore').strip()
            htmlparser = HTMLParser.HTMLParser()
            subtitle = htmlparser.unescape(sami).encode('utf-8')

            lang_pattern = re.search(r'[_]([a-z]+)', url)
            if lang_pattern:
                sub_lang = lang_pattern.group(1)
            else:
                sub_lang = 'unknown'
                self.log('Failed to identify subtitle language.')

            path = os.path.join(self.tempdir, '{0}.sami'.format(sub_lang))
            with open(path, 'w') as subfile:
                subfile.write(subtitle)
            paths.append(path)

        return paths

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

    def get_next_page(self, data):
        """Return the URL to the next page if the current page count is less than the total page count."""
        if data['type'] == 'page':
            data = self.get_products_block(data)  # sometimes, the info is only available in viaplay:blocks
        if data.get('pageCount'):
            if int(data['pageCount']) > int(data['currentPage']):
                next_page_url = data['_links']['next']['href']
                return next_page_url
            return False

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
