# -*- coding: utf-8 -*-
"""
A Kodi add-on for Viaplay
"""
import sys
from datetime import datetime

from resources.lib.kodihelper import KodiHelper

try:
    import urllib.request, urllib.parse, urllib.error
    from urllib.parse import urlencode, quote_plus, quote, unquote, parse_qsl
    import http.cookiejar as cookielib
except ImportError:
    import urllib
    import urlparse
    from urllib import urlencode, quote_plus, quote, unquote
    from urlparse import parse_qsl
    import cookielib

import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import routing
import re
import os

import sqlite3

import requests
import json

if sys.version_info[0] > 2:
    PY3 = True
else:
    PY3 = False

base_url = sys.argv[0]
handle = int(sys.argv[1])
params = dict(parse_qsl(sys.argv[2][1:]))
helper = KodiHelper(base_url, handle)
plugin = routing.Plugin()
addon = xbmcaddon.Addon(id='plugin.video.viaplay')

path = addon.getAddonInfo('path')
resources = os.path.join(path, 'resources')
icons = os.path.join(resources, 'icons')

movie_icon = os.path.join(icons, 'movie.png')
tv_icon = os.path.join(icons, 'tv.png')
vod_icon = os.path.join(icons, 'vod.png')
sport_icon = os.path.join(icons, 'sport.png')
kids_icon = os.path.join(icons, 'kids.png')
fav_icon = os.path.join(icons, 'fav.png')
search_icon = os.path.join(icons, 'search.png')
root_icon = os.path.join(icons, 'root.png')
settings_icon = os.path.join(icons, 'settings.png')
logout_icon = os.path.join(icons, 'logout.png')
watched_icon = os.path.join(icons, 'watched.png')

if PY3:
    profile_path = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile'))
else:
    profile_path = xbmc.translatePath(xbmcaddon.Addon().getAddonInfo('profile'))

def get_sql_source():
    kodi_version = xbmc.getInfoLabel('System.BuildVersion')[:2]

    kodi_list = [('18', '116'), ('19', '119'), ('20', '121'), ('21', '121')]

    for k in kodi_list:
        if k[0] == kodi_version:
            version = k[1]

    SOURCE_DB = 'MyVideos{v}.db'.format(v=version)

    path = xbmcvfs.translatePath("special://profile/")

    database_path = os.path.join(path, 'Database', SOURCE_DB)

    return database_path

def sql_watched():
    database_path = get_sql_source()

    conn = sqlite3.connect(database_path, detect_types=sqlite3.PARSE_DECLTYPES, cached_statements=2000)
    conn.row_factory = sqlite3.Row

    c = conn.cursor()

    watched_list = []

    c.execute('SELECT idFile, strFilename, playcount, lastPlayed FROM files')

    for row in c:
        viaplay_str = row[str('strFilename')]
        if 'plugin://plugin.video.viaplay' in viaplay_str:
            id = row[str('idFile')]
            playcount = row[str('playcount')]
            lastplayed = row[str('lastPlayed')]

            kv_pairs = viaplay_str.split("?")[1].split("&")
            viaplay_dict = {kv.split("=")[0]: kv.split("=")[1] for kv in kv_pairs}

            guid = viaplay_dict['guid'].split('-')[0]

            watched_list.append((guid, playcount, lastplayed, id))

    duration_list = []

    c.execute('SELECT idFile, TimeInSeconds, TotalTimeInSeconds FROM bookmark')

    for row in c:
        id = row[str('idFile')]
        time = row[str('TimeInSeconds')]
        total = row[str('TotalTimeInSeconds')]

        duration_list.append((time, total, id))

    conn.close()

    return watched_list, duration_list

def sql_remove_watched(guid):
    database_path = get_sql_source()

    conn = sqlite3.connect(database_path, detect_types=sqlite3.PARSE_DECLTYPES, cached_statements=2000)
    conn.row_factory = sqlite3.Row

    c = conn.cursor()

    c.execute('SELECT idFile, strFilename FROM files')

    for row in c:
        viaplay_str = row[str('strFilename')]
        if 'plugin://plugin.video.viaplay' in viaplay_str:
            kv_pairs = viaplay_str.split("?")[1].split("&")
            viaplay_dict = {kv.split("=")[0]: kv.split("=")[1] for kv in kv_pairs}

            guid_ = viaplay_dict['guid']

            if guid.split('-')[0] == guid_.split('-')[0]:
                id = row[str('idFile')]
                c.execute('UPDATE files SET playCount=? WHERE idFile=?', [None, id])
                c.execute('DELETE FROM bookmark WHERE idFile like ?', [id])
                conn.commit()

    conn.close()

def run():
    mode = params.get('mode', None)
    action = params.get('action', '')
    gen = params.get('guid', '')

    if action == 'BUILD_M3U':
        generate_m3u()

    elif action == 'remove_watched':
        guid = sys.argv[3][5:]
        watched(guid)

    elif action == 'remove_watched_program':
        guid = sys.argv[3][5:]
        watched(guid, program=True)

    elif action == 'favourite':
        guid = sys.argv[3][5:]
        favourite(guid)

    elif action == 'favourite_program':
        guid = sys.argv[3][5:]
        favourite(guid, program=True)

    elif action == 'remove_favourite':
        guid = sys.argv[3][5:]
        favourite(guid, remove=True)

    elif action == 'remove_favourite_program':
        guid = sys.argv[3][5:]
        favourite(guid, program=True, remove=True)

    elif gen != '':
        id = params.get('url', '')
        tve = params.get('tve', '')
        guid = params.get('guid', '')
        helper.play(url=id, tve=tve, guid=guid)

    try:
        plugin.run()
    except helper.vp.ViaplayError as error:
        missing_cookie = 'MissingSessionCookieError'

        if error.value == missing_cookie:
            if helper.authorize():
                plugin.run()
        else:
            show_error(error.value)

    except:
        pass

def watched(guid, program=False):
    params = {
        'profileId': helper.vp.get_setting('profileid'),
    }

    if program:
        if guid == 'no_guid':
            message = helper.language(30072)
            helper.dialog(dialog_type='notification', heading=helper.language(30017), message=message)
            return

        program_guid = guid

    else:
        guid = guid.split('-')[0]

        program_guid = guid

        if not guid[1:].isnumeric():
            message = helper.language(30072)
            helper.dialog(dialog_type='notification', heading=helper.language(30017), message=message)
            return

    url = helper.vp.base_url + '/deleteAllProgress/default/{0}/{1}'.format(program_guid, helper.vp.get_user_id()['id'])

    response = helper.vp.make_request(url=url, method='post', params=params, status=True)

    sql_remove_watched(program_guid)

    xbmc.executebuiltin('Container.Refresh')

    message = helper.language(30091)
    helper.dialog(dialog_type='notification', heading=helper.language(30017), message=message)

def favourite(guid, program=False, remove=False):
    params = {
        'profileId': helper.vp.get_setting('profileid'),
    }

    if program:
        if guid == 'no_guid':
            message = helper.language(30072)
            helper.dialog(dialog_type='notification', heading=helper.language(30017), message=message)
            return

        program_guid = guid

    else:
        guid = guid.split('-')[0]

        program_guid = guid

        if not guid[1:].isnumeric():
            message = helper.language(30072)
            helper.dialog(dialog_type='notification', heading=helper.language(30017), message=message)
            return

    if remove:
        json_data = {
            'programGuid': program_guid,
            'action': 'remove',
        }

        response = helper.vp.make_request(url=helper.vp.base_url + '/myList', method='put', params=params, payload=json_data, status=True)

        xbmc.executebuiltin('Container.Refresh')

        message = helper.language(30091)
        helper.dialog(dialog_type='notification', heading=helper.language(30017), message=message)

    else:
        json_data = {
            'programGuid': program_guid,
            'action': 'add',
        }

        response = helper.vp.make_request(url=helper.vp.base_url + '/myList', method='put', params=params, payload=json_data, status=True)

        message = helper.language(30071)
        helper.dialog(dialog_type='notification', heading=helper.language(30017), message=message)

def generate_m3u():
    sessionid = helper.authorize()
    if not sessionid:
        sessionid = helper.authorize()

    file_name = helper.get_setting('fname')
    path = helper.get_setting('path')

    if file_name == '' or path == '':
        xbmcgui.Dialog().notification('Viaplay', helper.language(30062),
                                      xbmcgui.NOTIFICATION_ERROR)
        return
    xbmcgui.Dialog().notification('Viaplay', helper.language(30063), xbmcgui.NOTIFICATION_INFO)

    data = '#EXTM3U\n'

    country_id = helper.get_setting('site')
    if country_id == '0':
        chann = 'kanaler'
    elif country_id == '1':
        chann = 'kanaler'
    elif country_id == '2':
        chann = 'kanaler'
    elif country_id == '3':
        chann = 'channels'
    elif country_id == '4':
        chann = 'channels'

    url = helper.vp.base_url + '/{0}'.format(chann)

    response = helper.vp.make_request(url=url, method='get')
    channels_block = response['_embedded']['viaplay:blocks'][0]['_embedded']['viaplay:blocks']
    channels = [x['viaplay:channel']['content']['title'] for x in channels_block]
    images = [x['viaplay:channel']['_embedded']['viaplay:products'][0]['station']['images']['fallbackImage']['template'] for x in channels_block]
    guids = [x['viaplay:channel']['_embedded']['viaplay:products'][1]['epg']['channelGuids'][0] for x in channels_block]

    for i in range(len(channels)):
        image = images[i].split('{')[0]

        img = re.compile(r'replace-(.*?)_.*\.png')

        try:
            title = img.search(image).group(1)
            title = re.sub(r"(\w)([A-Z])", r"\1 \2", title)
            title = title + ' ' + helper.get_country_code().upper()

        except:
            title = channels[i] + ' ' + helper.get_country_code().upper() 

        guid = guids[i]
        data += '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="Viasat",%s\nplugin://plugin.video.viaplay/play?guid=%s&url=None&tve=true\n' % (guid, title, image, title, guid)

    f = xbmcvfs.File(path + file_name, 'wb')
    if sys.version_info[0] > 2:
        f.write(data)
    else:
        f.write(bytearray(data, 'utf-8'))
    f.close()
    xbmcgui.Dialog().notification('Viaplay', helper.language(30064), xbmcgui.NOTIFICATION_INFO)

@plugin.route('/profiles')
def profiles():
    helper.profiles_dialog()
    xbmc.executebuiltin('Container.Refresh()')

@plugin.route('/')
def root():
    pages = helper.vp.get_root_page()

    supported_pages = {
        'viaplay:root': start,
        'viaplay:search': search,
        'viaplay:logout': log_out,
        'viaplay:starred': list_products,
        'viaplay:watched': list_products,
        'viaplay:purchased': list_products,
        'series': vod,
        'movie': vod,
        'kids': vod,
        'rental': vod,
        'sport': sport,
        'tve': channels,
        'channels': channels
    }

    profiles_dict = helper.vp.get_profiles()
    if profiles_dict:
        for profile in profiles_dict:
            if helper.vp.get_setting('profileid'):
                id = helper.vp.get_setting('profileid')
            else:
                id = helper.vp.get_user_id()['id']

            if id == profile['data'].get('id'):
                name = '{0} {1}'.format(helper.language(30090), profile['data'].get('name'))
                avatar = {'thumb': profile['embedded']['avatar']['data'].get('url')}
                helper.add_item(name, plugin.url_for(profiles), art=avatar)

    sorted_json = sorted(pages, key=lambda x: x['name'] == 'viaplay:logout')

    for page in sorted_json:
        page['title'] = capitalize(page['title'])

        if page['name'] in supported_pages:
            art = None
            if page['name'] == 'viaplay:root':
                art = {'icon': root_icon}
            elif page['name'] == 'viaplay:search':
                art = {'icon': search_icon}
            elif page['name'] == 'viaplay:logout':
                page['title'] = helper.language(30042)
                art = {'icon': logout_icon}
            elif page['name'] == 'viaplay:starred':
                page['title'] = helper.language(30077)
                art = {'icon': fav_icon}
            elif page['name'] == 'viaplay:watched':
                art = {'icon': watched_icon}
            elif page['name'] == 'series':
                art = {'icon': vod_icon}
            elif page['name'] == 'movie':
                art = {'icon': movie_icon}
            elif page['name'] == 'kids':
                art = {'icon': kids_icon}
            elif page['name'] == 'sport':
                art = {'icon': sport_icon}
            elif page['name'] == 'channels':
                art = {'icon': tv_icon}

            helper.add_item(page['title'], plugin.url_for(supported_pages[page['name']], url=page['href']), art=art)
        elif 'type' in page and page['type'] in supported_pages:  # weird channels listing fix on some subscriptions
            helper.add_item(page['title'], plugin.url_for(supported_pages[page['type']], url=page['href']))
        else:
            helper.log('Unsupported page found: %s' % page['name'])

    helper.eod()

@plugin.route('/start')
def start():
    collections = helper.vp.get_collections(plugin.args['url'][0])
    for i in collections:
        if i['type'] == 'list-featurebox':  # skip feature box for now
            continue
        helper.add_item(i['title'], plugin.url_for(list_products, url=i['_links']['self']['href']))
    helper.eod()


@plugin.route('/search')
def search():
    pages = helper.vp.get_root_page()
    title = [x['title'] for x in pages if x['name'] == 'viaplay:search'][0]

    file_search = os.path.join(profile_path, 'last_search.list')

    if xbmc.getInfoLabel('ListItem.Label') == title:
        file_name = os.path.join(profile_path, 'title_search.list')
        f = xbmcvfs.File(file_name, 'rb')
        searches = sorted(f.read().splitlines())
        f.close()

        actions = [helper.language(30079), helper.language(30080)] + searches

        action = helper.dialog(dialog_type='select', heading=helper.language(30081), options=actions)
        title = None

        if action == -1:
            return
        elif action == 0:
            pass
        elif action == 1:
            which = helper.dialog(dialog_type='multiselect', heading=helper.language(30080), options=searches)
            if which is None:
                return
            else:
                for item in reversed(which):
                    del searches[item]

                f = xbmcvfs.File(file_name, 'wb')
                if sys.version_info[0] < 3:
                    searches = [x.decode('utf-8') for x in searches]
                f.write(bytearray('\n'.join(searches), 'utf-8'))
                f.close()
                return
        else:
            if searches:
                title = searches[action - 2]

        if action == 0:
            search = helper.get_user_input(helper.language(30015))

        else:
            if sys.version_info[0] > 2:
                search = title
            else:
                search = title.encode('utf-8')

        if not search:
            return
        searches = (set([search] + searches))
        f = xbmcvfs.File(file_name, 'wb')
        if sys.version_info[0] < 3:
            searches = [x.decode('utf-8') for x in searches]
        f.write(bytearray('\n'.join(searches), 'utf-8'))
        f.close()

        if search != '':
            f = xbmcvfs.File(file_search, 'w')
            f.write(search)
            f.close()

            list_products(plugin.args['url'][0], search_query=search)
    else:
        f = xbmcvfs.File(file_search, 'r')
        search = f.read().splitlines()
        f.close()

        list_products(plugin.args['url'][0], search_query=search)


@plugin.route('/vod')
def vod():
    """List categories and collections from the VOD pages (movies, series, kids, store)."""
    helper.add_item(helper.language(30041), plugin.url_for(categories, url=plugin.args['url'][0]))
    collections = helper.vp.get_collections(plugin.args['url'][0])

    for i in collections:
        if i['type'] == 'list-featurebox':  # skip feature box for now
            continue

        if i['title'] == '':
            i = None

        try:
            helper.add_item(i['title'], plugin.url_for(list_products, url=i['_links']['self']['href']))
        except:
            pass

    """
    add_lst = []

    for i in collections:
        if 'a6-01' in i['id'] or 'a6-00' in i['id']:
            add_lst.append(i['_links']['self']['href'])
            add = False

    if add_lst:
        ordered_lst = ""

        for url in add_lst:
            ordered_lst += url

        helper.add_item('Seriale', plugin.url_for(list_products, url=ordered_lst))


    for i in collections:
        add = True

        if i['type'] == 'list-featurebox':  # skip feature box for now
            continue

        if i['title'] == '':
            for x in i['_embedded']['viaplay:products']:
                if x['type'] != 'series':
                    title = x['content']['title']
                    url = x['_links']['self']['href']
                    helper.add_item(title, plugin.url_for(list_products, url=url))
                    add = False        
                else:
                    add = False 

        if add:
            helper.add_item(i['title'], plugin.url_for(list_products, url=i['_links']['self']['href']))
        """

    helper.eod()

@plugin.route('/sport')
def sport():
    collections = helper.vp.get_collections(plugin.args['url'][0])
    schedule_added = False

    for i in collections:
        if 'viaplay:seeTableau' in i['_links'] and not schedule_added:
            plugin_url = plugin.url_for(sports_schedule, url=i['_links']['viaplay:seeTableau']['href'])
            helper.add_item(i['_links']['viaplay:seeTableau']['title'], plugin_url)
            schedule_added = True

        if i.get('totalProductCount'):
            if i.get('totalProductCount', 0) < 1:
                continue  # hide empty collections
        helper.add_item(i['title'], plugin.url_for(list_products, url=i['_links']['self']['href']))
    helper.eod()


@plugin.route('/channels')
def channels():
    channels_dict = helper.vp.get_channels(plugin.args['url'][0])

    for channel in channels_dict['channels']:
        plugin_url = plugin.url_for(list_products, url=channel['_links']['self']['href'])
        if 'fallback' in channel['content']['images']:
            channel_image = channel['content']['images']['fallback']['template'].split('{')[0]
        else:
            channel_image = channel['content']['images']['logo']['template'].split('{')[0]
        art = {
            'thumb': channel_image,
            'fanart': channel_image
        }

        current_program_title = coloring(helper.language(30049), 'no_broadcast')

        for index, program in enumerate(channel['_embedded']['viaplay:products']):  # get current live program
            if index > 0:
                if helper.vp.get_event_status(program) in ['live', 'archive', 'upcoming']:
                    if program.get('content'):
                        current_program_title = coloring(program['content']['title'], 'live')
                    else:  # no broadcast
                        current_program_title = coloring(helper.language(30049), 'no_broadcast')
                    break

        regex = fr'\(SimplyTV\)\s*|\b{helper.get_country_code().upper()}\b\s*'
        title = re.sub(regex, '', channel['content']['title'])

        if sys.version_info[0] > 2:
            list_title = '[B]{0}[/B]: {1}'.format(title, current_program_title)
        else:
            list_title = '[B]{0}[/B]: {1}'.format(title, current_program_title.encode('utf-8'))

        helper.add_item(list_title, plugin_url, art=art)

    if channels_dict['next_page']:
        helper.add_item(helper.language(30018), plugin.url_for(channels, url=channels_dict['next_page']))
    helper.eod()


@plugin.route('/log_out')
def log_out():
    confirm = helper.dialog('yesno', helper.language(30042), helper.language(30043))
    if confirm:
        helper.vp.log_out()


@plugin.route('/list_products')
def list_products(url=None, search_query=None):
    if not url or url is None:
        url = plugin.args['url'][0]
    products_dict = helper.vp.get_products(url, search_query=search_query)
    for product in products_dict['products']:
        if product['type'] == 'series':
            add_series(product, url)
        elif product['type'] == 'episode':
            add_episode(product, url)
        elif product['type'] == 'movie':
            add_movie(product, url)
        elif product['type'] == 'sport':
            add_sports_event(product, url)
        elif product['type'] == 'sportSeries':
            add_sports_series(product, url)
        elif product['type'] == 'tvEvent':
            add_tv_event(product, url)
        elif product['type'] == 'clip':
            add_event(product, url)
        else:
            helper.log('product type: {0} is not (yet) supported.'.format(product['type']))
            return False

    if products_dict['next_page']:
        helper.add_item(helper.language(30018), plugin.url_for(list_products, url=products_dict['next_page']))
    helper.eod()


@plugin.route('/sports_schedule')
def sports_schedule():
    dates = helper.vp.make_request(url=plugin.args['url'][0], method='get')['_links']['viaplay:days']
    for date in dates:
        helper.add_item(date['date'], plugin.url_for(list_products, url=date['href']))
    helper.eod()


@plugin.route('/sport_series')
def sport_series():
    categories = helper.vp.get_sport_series(plugin.args['url'][0])
    for category in categories:
        if category['content'].get('title'):
            if category['_links'].get('self'):
                helper.add_item(category['content']['title'], plugin.url_for(list_products, url=category['_links']['self']['href']))
    helper.eod()


@plugin.route('/seasons_page')
def seasons_page():
    """List all series seasons."""
    seasons = helper.vp.get_seasons(plugin.args['url'][0])
    if len(seasons) == 1:  # list products if there's only one season
        list_products(seasons[0]['_links']['self']['href'])
    else:
        for season in seasons:
            title = helper.language(30014).format(season['title'])
            helper.add_item(title, plugin.url_for(list_products, url=season['_links']['self']['href']))
        helper.eod()


@plugin.route('/categories')
def categories():
    categories_data = helper.vp.make_request(plugin.args['url'][0], 'get')['_links']['viaplay:categoryFilters']
    for i in categories_data:
        helper.add_item(i['title'], plugin.url_for(sortings, url=i['href']))
    helper.eod()


@plugin.route('/sortings')
def sortings():
    sortings_data = helper.vp.make_request(plugin.args['url'][0], 'get')['_links']['viaplay:sortings']
    for i in sortings_data:
        helper.add_item(i['title'], plugin.url_for(list_products, url=i['href']))
    helper.eod()


@plugin.route('/play')
def play():
    sessionid = helper.authorize()
    if not sessionid:
        sessionid = helper.authorize()

    helper.play(guid=plugin.args['guid'][0], url=plugin.args['url'][0], tve=plugin.args['tve'][0])

@plugin.route('/dialog')
def dialog():
    helper.dialog(dialog_type=plugin.args['dialog_type'][0],
                  heading=plugin.args['heading'][0],
                  message=plugin.args['message'][0])


@plugin.route('/ia_settings')
def ia_settings():
    helper.ia_settings()

def capitalize(string):
    return string[0].upper()+string[1:]

def add_movie(movie, site):
    #print('Category: add_movie')
    if movie['system'].get('guid'):
        url = None
        guid = movie['system']['guid']
    else:
        guid = None
        url = movie['_links']['self']['href']

    plugin_url = plugin.url_for(play, guid=guid, url=url, tve='false')

    details = movie['content']

    try:
        plotx = details.get('synopsis')
    except:
        plotx = ''

    movie_info = {
        'mediatype': 'movie',
        'title': details['title'],
        'plot': plotx,
        'genre': ', '.join([x['title'] for x in movie['_links']['viaplay:genres']]),
        'year': details['production'].get('year'),
        'duration': int(details['duration'].get('milliseconds')) // 1000 if 'duration' in details else None,
        'cast': details['people'].get('actors', []) if 'people' in details else [],
        'director': ', '.join(details['people'].get('directors', [])) if 'people' in details else [],
        'mpaa': details.get('parentalRating'),
        'rating': float(details['imdb'].get('rating')) if 'imdb' in details else None,
        'votes': str(details['imdb'].get('votes')) if 'imdb' in details else None,
        'code': details['imdb'].get('id') if 'imdb' in details else None
    }

    watched_list, duration_list = sql_watched()

    properties = []

    for w in watched_list:
        if w[0] == guid:
            movie_info.update({'playcount': w[1], 'lastplayed': w[2]})

            for d in duration_list:
                if d[2] == w[3]:
                    properties.append((d[0], d[1]))

    helper.add_item(movie_info['title'], plugin_url, info=movie_info, art=add_art(details['images'], 'movie'),
                    site=site, content='movies', playable=True, properties=properties, context=True)

def add_series(show, site):
    #print('Category: add_series')
    plugin_url = plugin.url_for(seasons_page, url=show['_links']['viaplay:page']['href'])

    details = show['content']

    if show['system'].get('guid'):
        guid = show['system']['guid']
    else:
        guid = None

    series_info = {
        'mediatype': 'tvshow',
        'title': details['series']['title'],
        'tvshowtitle': details['series']['title'],
        'plot': details['synopsis'] if details.get('synopsis') else details['series'].get('synopsis'),
        'genre': ', '.join([x['title'] for x in show['_links']['viaplay:genres']]),
        'year': details['production'].get('year') if 'production' in details else None,
        'cast': details['people'].get('actors', []) if 'people' in details else [],
        'director': ', '.join(details['people'].get('directors', [])) if 'people' in details else None,
        'mpaa': details.get('parentalRating'),
        'rating': float(details['imdb'].get('rating')) if 'imdb' in details else None,
        'votes': str(details['imdb'].get('votes')) if 'imdb' in details else None,
        'code': details['imdb'].get('id') if 'imdb' in details else None,
        'season': int(details['series']['seasons']) if details['series'].get('seasons') else None
    }

    helper.add_item(series_info['title'], plugin_url, folder=True, info=series_info,
                    art=add_art(details['images'], 'series'), site=site, content='tvshows', context=True)


def add_episode(episode, site):
    #print('Category: add_episode')
    plugin_url = plugin.url_for(play, guid=episode['system']['guid'], url=None, tve='false')

    details = episode['content']

    if episode['system'].get('guid'):
        guid = episode['system']['guid']
    else:
        guid = None

    episode_info = {
        'mediatype': 'episode',
        'originaltitle': details.get('title'),
        'title': details['series']['episodeTitle'] if details['series'].get('episodeTitle') else details.get(
            'title'),
        'tvshowtitle': details['series'].get('title'),
        'plot': details['synopsis'] if details.get('synopsis') else details['series'].get('synopsis'),
        'duration': details['duration']['milliseconds'] // 1000 if 'duration' in details else None,
        'genre': ', '.join([x['title'] for x in episode['_links']['viaplay:genres']]),
        'year': details['production'].get('year') if 'production' in details else None,
        'cast': details['people'].get('actors', []) if 'people' in details else [],
        'director': ', '.join(details['people'].get('directors', [])) if 'people' in details else None,
        'mpaa': details.get('parentalRating'),
        'rating': float(details['imdb'].get('rating')) if 'imdb' in details else None,
        'votes': str(details['imdb'].get('votes')) if 'imdb' in details else None,
        'code': details['imdb'].get('id') if 'imdb' in details else None,
        'season': int(details['series']['season'].get('seasonNumber')),
        'episode': int(details['series'].get('episodeNumber'))
    } 

    watched_list, duration_list = sql_watched()

    properties = []

    for w in watched_list:
        if w[0] == guid:
            episode_info.update({'playcount': w[1], 'lastplayed': w[2]})

            for d in duration_list:
                if d[2] == w[3]:
                    properties.append((d[0], d[1]))

    helper.add_item(episode_info['title'], plugin_url, info=episode_info,
                    art=add_art(details['images'], 'episode'), site=site, content='episodes', playable=True, episode=True, properties=properties, context=True)


def add_sports_event(event, site):
    #print('Category: add_sports_event')
    now = datetime.now()
    date_today = now.date()
    event_date = helper.vp.parse_datetime(event['epg']['start'], localize=True)
    event_status = helper.vp.get_event_status(event)

    if date_today == event_date.date():
        start_time = '{0} {1}'.format(helper.language(30027), event_date.strftime('%H:%M'))
    else:
        start_time = event_date.strftime('%Y-%m-%d %H:%M')

    if event_status != 'upcoming':
        plugin_url = plugin.url_for(play, guid=event['system']['guid'] + '-%s' % helper.get_country_code().upper(), url=None, tve='false')
        playable = True
    else:
        plugin_url = plugin.url_for(dialog, dialog_type='ok',
                             heading=helper.language(30017),
                             message=helper.language(30016).format(start_time).encode('utf-8'))
        playable = False

    details = event['content']

    if event['system'].get('guid'):
        guid = event['system']['guid']
    else:
        guid = None

    if sys.version_info[0] > 2:
        title = details.get('title')
    else:
        title = details.get('title').encode('utf-8')
    try:
        plotx = details.get('synopsis')
    except:
        plotx = ''

    event_info = {
        'mediatype': 'video',
        'originaltitle': details.get('title'),
        'plot': plotx,
        'year': int(details['production'].get('year')),
        'genre': details['format'].get('title'),
        'title': '[B]{0}:[/B] {1}'.format(coloring(start_time, event_status), title)
    }

    watched_list, duration_list = sql_watched()

    properties = []

    for w in watched_list:
        if w[0] == guid:
            event_info.update({'playcount': w[1], 'lastplayed': w[2]})

            for d in duration_list:
                if d[2] == w[3]:
                    properties.append((d[0], d[1]))

    helper.add_item(event_info['title'], plugin_url, playable=playable, info=event_info,
                    art=add_art(details['images'], 'sport'), sys_guid=event['system']['guid'], site=site, content='episodes', properties=properties, context=True)


def add_sports_series(event, site):
    #print('Category: add_sports_series')
    now = datetime.now()
    date_today = now.date()
    if event.get('epg'):
        event_date = helper.vp.parse_datetime(event['epg']['start'], localize=True)
    else:
        event_date = helper.vp.parse_datetime(event['system']['availability']['start'], localize=True)
    event_status = helper.vp.get_event_status(event)

    if date_today == event_date.date():
        start_time = '{0} {1}'.format(helper.language(30027), event_date.strftime('%H:%M'))
    else:
        start_time = event_date.strftime('%Y-%m-%d %H:%M')

    event_url = event['_links']['viaplay:page']['href']

    if event_status != 'upcoming':
        plugin_url = plugin.url_for(sport_series, url=event_url)
        playable = False
    else:
        plugin_url = plugin.url_for(dialog, dialog_type='ok',
                             heading=helper.language(30017),
                             message=helper.language(30016).format(start_time).encode('utf-8'))
        playable = False

    details = event['content']

    if sys.version_info[0] > 2:
        if details.get('title'):
            title = details.get('title')
        else:
            title = details.get('series', {}).get('title')
    else:
        if details.get('title'):
            title = details.get('title').encode('utf-8')
        else:
            title = details.get('series', {}).get('title').encode('utf-8')
    try:
        plotx = details.get('synopsis')
    except:
        plotx = ''

    if details.get('format'):
        genre = details.get('format').get('title')
    else:
        genre = ''

    event_info = {
        'mediatype': 'video',
        'originaltitle': title,
        'plot': plotx,
        'year': details['production'].get('year'),
        'genre': genre,
        'title': '[B]{0}:[/B] {1}'.format(coloring(start_time, event_status), title)
    }

    helper.add_item(event_info['title'], plugin_url, playable=playable, info=event_info,
                    art=add_art(details['images'], 'sport'), sys_guid=event['system']['guid'], site=site, content='episodes', context=True)


def add_tv_event(event, site):
    #print('Category: add_tv_event')
    now = datetime.now()
    date_today = now.date()

    start_time_obj = helper.vp.parse_datetime(event['epg']['startTime'], localize=True)
    end_time_obj = helper.vp.parse_datetime(event['epg']['endTime'], localize=True)

    event_status = helper.vp.get_event_status(event)

    status = False

    if end_time_obj >= now and helper.get_setting('previous_channels'):
        status = True
    elif not helper.get_setting('previous_channels'):
        status = True

    if status:
        # hide non-available catchup items
        start_time = str(datetime.now())[:-16]
        if now > helper.vp.parse_datetime(event['system']['catchupAvailability']['end'], localize=True):
            return

        if date_today == start_time_obj.date():
            start_time = '{0} {1}'.format(helper.language(30027), start_time_obj.strftime('%H:%M'))
        else:
            start_time = start_time_obj.strftime('%Y-%m-%d %H:%M')

        if event_status != 'upcoming':
            plugin_url = plugin.url_for(play, guid=event['system']['guid'] + '-%s' % helper.get_country_code().upper(), url=None, tve='true')
            playable = True
        else:
            plugin_url = plugin.url_for(dialog, dialog_type='ok',
                                 heading=helper.language(30017),
                                 message=helper.language(30016).format(start_time).encode('utf-8'))
            playable = False

        details = event['content']

        if sys.version_info[0] > 2:
            title = details.get('title')
        else:
            title = details.get('title').encode('utf-8')

        event_info = {
            'mediatype': 'video',
            'originaltitle': details.get('title'),
            'plot': details.get('synopsis'),
            'year': details['production'].get('year'),
            'title': '[B]{0}:[/B] {1}'.format(coloring(start_time, event_status), title)
        }

        art = {
            'thumb': event['content']['images']['landscape']['template'].split('{')[0] if 'landscape' in details['images'] else None,
            'fanart': event['content']['images']['landscape']['template'].split('{')[0] if 'landscape' in details['images'] else None
        }

        helper.add_item(event_info['title'], plugin_url, playable=playable, info=event_info, art=art, sys_guid=event['system']['guid'], site=site, content='episodes', context=True)

def add_event(event, site):
    #print('Category: add_event')
    plugin_url = plugin.url_for(play, guid=event['system']['guid'], url=None, tve='false')

    details = event['content']

    if sys.version_info[0] > 2:
        title = details.get('title')
    else:
        title = details.get('title').encode('utf-8')

    event_info = {
        'mediatype': 'episode',
        'originaltitle': details.get('title'),
        'plot': details.get('synopsis'),
        'year': details['production'].get('year'),
        'title': '{0}'.format(title),
    }

    art = {
        'thumb': event['content']['images']['landscape']['template'].split('{')[0] if 'landscape' in details['images'] else None,
        'fanart': event['content']['images']['landscape']['template'].split('{')[0] if 'landscape' in details['images'] else None
    }

    watched_list, duration_list = sql_watched()

    properties = []

    for w in watched_list:
        if w[0] == event['system']['guid']:
            event_info.update({'playcount': w[1], 'lastplayed': w[2]})

            for d in duration_list:
                if d[2] == w[3]:
                    properties.append((d[0], d[1]))

    helper.add_item(event_info['title'], plugin_url, playable=True, info=event_info, art=art, site=site, content='episodes', properties=properties, context=True)

def add_art(images, content_type):
    artwork = {}

    for i in images:
        image_url = images[i]['template'].split('{')[0]  # get rid of template

        if i == 'landscape':
            if content_type == 'episode' or 'sport':
                artwork['thumb'] = image_url
            artwork['banner'] = image_url
        elif i == 'hero169':
            artwork['fanart'] = image_url
        elif i == 'coverart23':
            if content_type != 'sport':
                artwork['poster'] = image_url
        elif i == 'coverart169':
            artwork['cover'] = image_url
        elif i == 'boxart':
            if content_type != 'episode' or content_type != 'sport':
                artwork['thumb'] = image_url

    return artwork


def coloring(text, meaning):
    """Return the text wrapped in appropriate color markup."""
    if meaning == 'live':
        color = 'FF03F12F'
    elif meaning == 'upcoming':
        color = 'FFF16C00'
    elif meaning == 'archive':
        color = 'FFFF0EE0'
    elif meaning == 'no_broadcast':
        color = 'FFFF3333'
    colored_text = '[COLOR=%s]%s[/COLOR]' % (color, text)
    return colored_text


def show_error(error):
    if error == 'UserNotAuthorizedForContentError':
        message = helper.language(30020)
    elif error == 'PurchaseConfirmationRequiredError':
        message = helper.language(30021)
    elif error == 'UserNotAuthorizedRegionBlockedError':
        message = helper.language(30022)
    elif error == 'ConcurrentStreamsLimitReachedError':
        message = helper.language(30050)
    elif error == 'PersistentLoginError':
        message = error
    else:
        message = error


    helper.dialog(dialog_type='ok', heading=helper.language(30017), message=message)