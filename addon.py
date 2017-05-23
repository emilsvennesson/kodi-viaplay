# -*- coding: utf-8 -*-
"""
A Kodi add-on for Viaplay
"""
import sys
import urlparse
from datetime import datetime

from resources.lib.kodihelper import KodiHelper

base_url = sys.argv[0]
handle = int(sys.argv[1])
helper = KodiHelper(base_url, handle)


def run():
    try:
        router(sys.argv[2][1:])  # trim the leading '?' from the plugin call paramstring
    except helper.vp.ViaplayError as error:
        if error.value == 'MissingSessionCookieError':
            if helper.authorize():
                router(sys.argv[2][1:])
        else:
            helper.dialog('ok', helper.language(30005), error.value)


def root_page():
    pages = helper.vp.get_root_page()

    for page in pages:
        params = {
            'action': page['name'] if page.get('name') else page['id'],
            'url': page['href']
        }
        helper.add_item(page['title'], params)
    helper.eod()


def start_page(url):
    collections = helper.vp.get_collections(url)

    for i in collections:
        params = {
            'action': 'list_products',
            'url': i['_links']['self']['href']
        }
        helper.add_item(i['title'], params)
    helper.eod()


def vod_page(url):
    """List categories and collections from the VOD pages (movies, series, kids, store)."""
    collections = helper.vp.get_collections(url)

    categories_item(url)
    for i in collections:
        params = {
            'action': 'list_products',
            'url': i['_links']['self']['href']
        }
        helper.add_item(i['title'], params)
    helper.eod()


def categories_page(url):
    categories = helper.vp.make_request(url, 'get')['_links']['viaplay:categoryFilters']

    for i in categories:
        params = {
            'action': 'sortings_page',
            'url': i['href']
        }
        helper.add_item(i['title'], params)
    helper.eod()

def sortings_page(url):
    sortings = helper.vp.make_request(url, 'get')['_links']['viaplay:sortings']

    for i in sortings:
        params = {
            'action': 'list_products',
            'url': i['href']
        }
        helper.add_item(i['title'], params)
    helper.eod()


def categories_item(url):
    title = helper.language(30041)
    params = {
        'action': 'categories_page',
        'url': url
    }
    helper.add_item(title, params)


def list_next_page(url):
    title = helper.language(30018)
    params = {
        'action': 'list_products',
        'url': url
    }
    helper.add_item(title, params)


def list_products(url, filter_event=False, search_query=None):
    if filter_event:
        filter_event = filter_event.split(', ')

    products_dict = helper.vp.get_products(url, filter_event=filter_event, search_query=search_query)
    for product in products_dict['products']:

        if product['type'] == 'series':
            add_series(product)
        elif product['type'] == 'episode':
            add_episode(product)
        elif product['type'] == 'movie':
            add_movie(product)
        elif product['type'] == 'sport':
            add_sports_event(product)
        else:
            helper.log('product type: {0} not (yet) supported.'.format(product['type']))
            return False

    if products_dict['next_page']:
        list_next_page(products_dict['next_page'])
    helper.eod()


def add_movie(movie):
    params = {}
    if movie['system'].get('guid'):
        params['action'] = 'play_guid'
        params['guid'] = movie['system']['guid']
    else:
        params['action'] = 'play_url'
        params['url'] = movie['_links']['self']['href']

    details = movie['content']

    movie_info = {
        'mediatype': 'movie',
        'title': details['title'],
        'plot': details.get('synopsis'),
        'genre': ', '.join([x['title'] for x in movie['_links']['viaplay:genres']]),
        'year': details['production'].get('year'),
        'duration': int(details['duration'].get('milliseconds')) / 1000,
        'cast': details['people'].get('actors', []) if 'people' in details.keys() else [],
        'director': ', '.join(details['people'].get('directors', [])) if 'people' in details.keys() else [],
        'mpaa': details.get('parentalRating'),
        'rating': float(details['imdb'].get('rating')) if 'imdb' in details.keys() else None,
        'votes': str(details['imdb'].get('votes')) if 'imdb' in details.keys() else None,
        'code': details['imdb'].get('id') if 'imdb' in details.keys() else None
    }

    helper.add_item(movie_info['title'], params=params, info=movie_info, art=add_art(details['images'], 'movie'), content='movies', playable=True)


def add_series(show):
    params = {
        'action': 'list_seasons',
        'url': show['_links']['viaplay:page']['href']
    }

    details = show['content']

    series_info = {
        'mediatype': 'tvshow',
        'title': details['series']['title'],
        'tvshowtitle': details['series']['title'],
        'plot': details['synopsis'] if details.get('synopsis') else details['series'].get('synopsis'),
        'genre': ', '.join([x['title'] for x in show['_links']['viaplay:genres']]),
        'year': details['production'].get('year') if 'production' in details.keys() else None,
        'cast': details['people'].get('actors', []) if 'people' in details.keys() else [],
        'director': ', '.join(details['people'].get('directors', [])) if 'people' in details.keys() else None,
        'mpaa': details.get('parentalRating'),
        'rating': float(details['imdb'].get('rating')) if 'imdb' in details.keys() else None,
        'votes': str(details['imdb'].get('votes')) if 'imdb' in details.keys() else None,
        'code': details['imdb'].get('id') if 'imdb' in details.keys() else None,
        'season': int(details['series']['seasons']) if details['series'].get('seasons') else None
    }

    helper.add_item(series_info['title'], params=params, folder=True, info=series_info, art=add_art(details['images'], 'series'), content='tvshows')


def add_episode(episode):
    params = {
        'action': 'play_guid',
        'guid': episode['system']['guid']
    }

    details = episode['content']

    episode_info = {
        'mediatype': 'episode',
        'title': details.get('title'),
        'list_title': details['series']['episodeTitle'] if details['series'].get('episodeTitle') else details.get('title'),
        'tvshowtitle': details['series'].get('title'),
        'plot': details['synopsis'] if details.get('synopsis') else details['series'].get('synopsis'),
        'duration' : details['duration']['milliseconds'] / 1000,
        'genre': ', '.join([x['title'] for x in episode['_links']['viaplay:genres']]),
        'year': details['production'].get('year') if 'production' in details.keys() else None,
        'cast': details['people'].get('actors', []) if 'people' in details.keys() else [],
        'director': ', '.join(details['people'].get('directors', [])) if 'people' in details.keys() else None,
        'mpaa': details.get('parentalRating'),
        'rating': float(details['imdb'].get('rating')) if 'imdb' in details.keys() else None,
        'votes': str(details['imdb'].get('votes')) if 'imdb' in details.keys() else None,
        'code': details['imdb'].get('id') if 'imdb' in details.keys() else None,
        'season': int(details['series']['season'].get('seasonNumber')),
        'episode': int(details['series'].get('episodeNumber'))
    }

    helper.add_item(episode_info['list_title'], params=params, info=episode_info, art=add_art(details['images'], 'episode'), content='episodes', playable=True)


def add_sports_event(event):
    now = datetime.now()
    date_today = now.date()

    if date_today == event['event_date'].date():
        start_time = '{0} {1}'.format(helper.language(30027), event['event_date'].strftime('%H:%M'))
    else:
        start_time = event['event_date'].strftime('%Y-%m-%d %H:%M')

    if event['event_status'] == 'upcoming':
        params = {
            'action': 'dialog',
            'dialog_type': 'ok',
            'heading': helper.language(30017),
            'message': helper.language(30016).format(start_time)
        }
        playable = False
    else:
        params = {
            'action': 'play_guid',
            'guid': event['system']['guid']
        }
        playable = True

    details = event['content']

    event_info = {
        'mediatype': 'video',
        'title': details.get('title'),
        'plot': details['synopsis'],
        'year': int(details['production'].get('year')),
        'genre': details['format'].get('title'),
        'list_title': '[B]{0}:[/B] {1}'.format(coloring(start_time, event['event_status']), details.get('title').encode('utf-8'))
    }

    helper.add_item(event_info['list_title'], params=params, playable=playable, info=event_info, art=add_art(details['images'], 'sport'), content='movies')

def list_seasons(url):
    """List all series seasons."""
    seasons = helper.vp.get_seasons(url)
    if len(seasons) == 1:
        # list products if there's only one season
        season_url = seasons[0]['_links']['self']['href']
        list_products(season_url)
    else:
        for season in seasons:
            season_url = season['_links']['self']['href']
            title = '%s %s' % (helper.language(30014), season['title'])
            parameters = {
                'action': 'list_products',
                'url': season_url
            }

            helper.add_item(title, parameters)
        helper.eod()


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
            artwork['cover'] = image_url
        elif i == 'boxart':
            if content_type != 'episode' or 'sport':
                artwork['thumb'] = image_url
            artwork['poster'] = image_url

    return artwork


def search(url):
    query = helper.get_user_input(helper.language(30015))
    if query:
        list_products(url, search_query=query)

def sports_page(url):
    event_date = ['today', 'upcoming', 'archive']

    for date in event_date:
        if date == 'today':
            title = helper.language(30027)
        elif date == 'upcoming':
            title = helper.language(30028)
        else:
            title = helper.language(30029)
        if date == 'today':
            parameters = {
                'action': 'list_sports_today',
                'url': url
            }
        else:
            parameters = {
                'action': 'list_sports_dates',
                'url': url,
                'event_date': date
            }

        helper.add_item(title, parameters)
    helper.eod()


def list_sports_today(url):
    event_status = [helper.language(30037), helper.language(30031)]
    for status in event_status:
        if status == helper.language(30037):
            filter = 'live, upcoming'
        else:
            filter = 'archive'
        parameters = {
            'action': 'list_products_sports_today',
            'url': url,
            'filter_sports_event': filter
        }

        helper.add_item(status, parameters)
    helper.eod()


def list_sports_dates(url, event_date):
    dates = helper.vp.get_sports_dates(url, event_date)
    for date in dates:
        title = date['date']
        parameters = {
            'action': 'list_products',
            'url': date['href']
        }

        helper.add_item(title, parameters)
    helper.eod()


def coloring(text, meaning):
    """Return the text wrapped in appropriate color markup."""
    if meaning == 'live':
        color = 'FF03F12F'
    elif meaning == 'upcoming':
        color = 'FFF16C00'
    elif meaning == 'archive':
        color = 'FFFF0EE0'
    colored_text = '[COLOR=%s]%s[/COLOR]' % (color, text)
    return colored_text


def show_auth_error(error):
    if error == 'UserNotAuthorizedForContentError':
        message = helper.language(30020)
    elif error == 'PurchaseConfirmationRequiredError':
        message = helper.language(30021)
    elif error == 'UserNotAuthorizedRegionBlockedError':
        message = helper.language(30022)
    else:
        message = error

    helper.dialog(dialog_type='ok', heading=helper.language(30017), message=message)


def router(paramstring):
    """Router function that calls other functions depending on the provided paramstring."""
    params = dict(urlparse.parse_qsl(paramstring))
    if 'action' in params:
        if params['action'] in helper.vp.vod_pages:
            vod_page(params['url'])
        elif params['action'] == 'sport':
            sports_page(params['url'])
        elif params['action'] == 'categories_page':
            categories_page(params['url'])
        elif params['action'] == 'sortings_page':
            sortings_page(params['url'])
        if params['action'] == 'viaplay:root':
            start_page(params['url'])
        elif params['action'] == 'viaplay:search':
            search(params['url'])
        elif params['action'] == 'viaplay:logout':
            helper.log_out()
        elif params['action'] == 'play_guid':
            helper.play(guid=params['guid'])
        elif params['action'] == 'play_url':
            helper.play(url=params['url'])
        elif params['action'] == 'list_seasons':
            list_seasons(params['url'])
        elif params['action'] == 'list_products':
            list_products(params['url'])
        elif params['action'] == 'list_sports_today':
            list_sports_today(params['url'])
        elif params['action'] == 'list_products_sports_today':
            list_products(params['url'], params['filter_sports_event'])
        elif params['action'] == 'list_sports_dates':
            list_sports_dates(params['url'], params['event_date'])
        elif params['action'] == 'dialog':
            helper.dialog(params['dialog_type'], params['heading'], params['message'])
    else:
        root_page()
