#!/usr/bin/python
# encoding: utf-8
#
# Copyright © 2015 deanishe@deanishe.net
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2015-09-17
#

"""flix.py [options] [command] [arg]

Search Flixsearch.io.

Show which Netflix content is available and where.

Usage:
    flix.py search <query>
    flix.py config [<query>]
    flix.py countries [<query>]
    flix.py activate <country>
    flix.py deactivate <country>
    flix.py -h|--help

Options:
    -h, --help  Show this message and exit.

"""

from __future__ import print_function, unicode_literals, absolute_import

import hashlib
import htmlentitydefs
import re
import subprocess
import sys
import time

from bs4 import BeautifulSoup as BS
from bs4 import Tag
from docopt import docopt
from workflow import (
    Workflow,
    web,
    ICON_WARNING,
    ICON_BURN,
)

USER_AGENT = ('Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36')


# Countries where Netflix is available (that Flixsearch.io knows about)
COUNTRIES = [
    'Argentina',
    'Australia',
    'Austria',
    'Belgium',
    'Brazil',
    'Canada',
    'Colombia',
    'Denmark',
    'Finland',
    'France',
    'Germany',
    'Ireland',
    'Luxembourg',
    'Mexico',
    'Netherlands',
    'New Zealand',
    'Norway',
    'Sweden',
    'Switzerland',
    'UK',
    'USA',
]

FLAGS = dict([(c, 'icons/{0}.png'.format(c)) for c in COUNTRIES])

ICON_HELP = 'icons/help.icns'
ICON_UPDATE_AVAILABLE = 'icons/update-available.icns'
ICON_UPDATE_NONE = 'icons/update-none.icns'
ICON_ON = 'icons/toggle_on.icns'
ICON_OFF = 'icons/toggle_off.icns'

HELP_URL = 'https://github.com/deanishe/alfred-flixsearch'
DEFAULT_SETTINGS = {
    # Activate all countries by default
    'countries': COUNTRIES
}
UPDATE_SETTINGS = {
    'github_slug': 'deanishe/alfred-flixsearch'
}

log = None


def unescape(text):
    """Replace HTML entities with Unicode characters.

    From: http://effbot.org/zone/re-sub.htm#unescape-html
    """

    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text  # leave as is

    return re.sub("&#?\w+;", fixup, text)


def flatten(elem, recursive=False):
    """Return the string contents of partial BS elem tree.

    :param elem: BeautifulSoup ``Tag`` or ``NavigableString``
    :param recursive: Whether to flatten children or entire subtree
    :returns: Flattened Unicode text contained in subtree

    """

    content = []

    if recursive:
        elems = elem.descendants
    else:
        elems = elem.contents

    for e in elems:
        # If processing recursively, a NavigableString for the
        # tag text will also be encountered
        if isinstance(e, Tag) and recursive:
            continue
        if hasattr(e, 'string') and e.string is not None:
            # log.debug('[%s] : %s', e.__class__.__name__, e.string)
            content.append(e.string)

    return unescape(re.sub(r'\s+', ' ', ''.join(content))).strip()


def retrieve_flixsearch_url(query):
    """Get HTML response from flixsearch.io.

    Returns Unicode HTML.

    """

    start = time.time()
    url = 'https://flixsearch.io/search/{0}'.format(query.encode('utf-8'))
    log.debug('Retrieving URL `%s` ...', url)
    headers = {'User-Agent': USER_AGENT}
    r = web.get(url, headers=headers)
    r.raise_for_status()
    html = r.content
    # log.debug('HTML : %s', html)
    duration = time.time() - start
    log.debug('URL retrieved in %0.3f seconds', duration)
    return html


def parse_flixsearch_html(html):
    """Parse HTML and return search results."""

    start = time.time()
    results = []

    soup = BS(html, b'html5lib')
    elems = soup.find_all('div', 'card')
    log.debug('%d `card` elems found', len(elems))

    for i, elem in enumerate(elems):
        image = title = description = url = None
        countries = []
        genres = []

        # ---------------------------------------------------------
        # Parse subelements
        img_box = elem.find('div', 'card-image')
        if not img_box:
            log.error('No image box found : %r', elem)
            continue

        # flixsearch.io URL
        url = img_box.find('a').get('href')
        if not url:
            log.error('No URL found : %r', img_box)
            continue

        # tmbd.org image
        image = img_box.find('img').get('src')
        if not image:
            log.error('No image found : %r', img_box)
            continue
        else:
            image = image.decode('utf-8')

        # Film/show title
        title_elem = img_box.find('span', 'card-title')
        if title_elem:
            title = flatten(title_elem)
        else:
            log.error('No title found : %r', img_box)
            continue

        # Genres & description
        content_box = elem.find('div', 'card-content')
        if not content_box:
            log.error('No content box found : %r', elem)
            continue

        paras = content_box.find_all('p')
        if len(paras) == 1:  # description only
            description = paras[0].string
        elif len(paras) == 2:  # expected results
            genres = [s.strip() for s in paras[0].string.split(',')]
            description = paras[1].string
        else:
            log.error('Found %d p elements, not 1 or 2 in %r',
                      len(paras), content_box)
            continue

        # genres = [s.strip() for s in paras[0].string.split(',')]
        # description = paras[1].string

        # Countries
        flag_box = elem.find('div', 'flags')
        if not flag_box:
            log.error('No flag box found : %r', elem)
            continue
        for e in flag_box.find_all('img', 'flag-post'):
            country = e.get('title')
            if country:
                countries.append(country)

        if not len(countries):
            log.error('No countries for %r', elem)
            continue

        if i == 0:
            log.debug('-' * 60)

        log.debug('Title       : %r', title)
        log.debug('URL         : %r', url)
        log.debug('Image       : %r', image)
        log.debug('Description : %r', description)
        log.debug('Genres      : %r', genres)
        log.debug('Countries   : %r', countries)
        log.debug('-' * 60)

        results.append(dict(title=title,
                            url=url,
                            image=image,
                            description=description,
                            genres=genres,
                            countries=countries))

    duration = time.time() - start
    log.debug('HTML parsed in %0.3f seconds', duration)

    return results


def flixsearch(query):
    """Retrieve results from flixsearch.io."""

    def _wrapper():
        html = retrieve_flixsearch_url(query)
        results = parse_flixsearch_html(html)
        return results

    cache_key = 'results-' + hashlib.md5(query.encode('utf-8')).hexdigest()
    results = wf.cached_data(cache_key, _wrapper, max_age=3600)

    return results


class FlixSearch(object):
    """Workflow application."""

    def __init__(self):
        """Create new `FlixSearch` object."""

        self.wf = None

    def run(self, wf):
        """Run workflow. Call appropriate method based on CLI args."""

        self.wf = wf
        args = docopt(__doc__, argv=wf.args)
        log.debug('args : %r', args)

        if args.get('search'):
            return self.do_search(args.get('<query>'))
        elif args.get('config'):
            return self.do_config(args.get('<query>'))
        elif args.get('countries'):
            return self.do_countries(args.get('<query>'))
        elif args.get('activate'):
            return self.do_activate(args.get('<country>'))
        elif args.get('deactivate'):
            return self.do_deactivate(args.get('<country>'))

    # ---------------------------------------------------------
    # Script actions

    def do_search(self, query):
        """Search flixsearch.io and display results in Alfred."""

        log.debug('Searching flixsearch.io for %r ...', query)
        results = flixsearch(query)
        log.debug('%d total results for `%s`', len(results), query)
        results = self._filter_for_countries(results)
        log.debug("%d results in user's countries for `%s`",
                  len(results), query)

        if not results:
            self.wf.add_item('No results found',
                             'Try a different query',
                             icon=ICON_WARNING)
            self.wf.send_feedback()
            return 0

        for r in results:
            subtitles = {
                'cmd': ', '.join(r['genres']),
                'alt': ', '.join(r['countries']),
                'ctrl': r['url'],
            }
            self.wf.add_item(r['title'],
                             # ', '.join(r['genres']),
                             r['description'],
                             modifier_subtitles=subtitles,
                             arg=r['url'],
                             valid=True,
                             uid=r['title'])

        self.wf.send_feedback()
        return 0

    def do_config(self, query):
        """Show configuration options."""

        # Call external trigger to re-run workflow
        if query == 'countries':
            return self._call_countries_trigger()

        # ---------------------------------------------------------
        # Update
        if self.wf.update_available:
            self.wf.add_item('A new version is available',
                             '↩ or ⇥ to update',
                             autocomplete='workflow:update',
                             icon=ICON_UPDATE_AVAILABLE)
        else:
            self.wf.add_item('Workflow is up to date',
                             icon=ICON_UPDATE_NONE)

        # ---------------------------------------------------------
        # Workflow help
        self.wf.add_item('View help',
                         '↩ or ⇥ to open the help in your browser',
                         autocomplete='workflow:help',
                         icon=ICON_HELP)

        # ---------------------------------------------------------
        # Countries
        self.wf.add_item('Select countries',
                         '↩ or ⇥ to choose countries to search',
                         autocomplete='countries',
                         icon=FLAGS['UK'])

        # ---------------------------------------------------------
        # Reset
        self.wf.add_item('Reset workflow',
                         '↩ or ⇥ to clear cache and settings',
                         autocomplete='workflow:reset',
                         icon=ICON_BURN)

        self.wf.send_feedback()
        return 0

    def do_countries(self, query):
        """Show list of available countries."""
        user_countries = self.wf.settings.get('countries', [])

        if not query:  # Show top-level options

            all_selected = len(user_countries) == len(COUNTRIES)
            none_selected = len(user_countries) == 0

            if not all_selected:
                self.wf.add_item('Select all',
                                 '↩ to select all countries',
                                 arg='activate ALL',
                                 valid=True,
                                 icon=ICON_ON)

            if not none_selected:
                self.wf.add_item('Deselect all',
                                 '↩ to deselect all countries',
                                 arg='deactivate ALL',
                                 valid=True,
                                 icon=ICON_OFF)

            if not none_selected:
                self.wf.add_item(
                    'Active countries…',
                    '↩ or ⇥ to view and deactivate active countries',
                    autocomplete='active ',
                    icon=ICON_ON
                )

            if not all_selected:
                self.wf.add_item(
                    'Inactive countries…',
                    '↩ or ⇥ to view and activate inactive countries',
                    autocomplete='inactive ',
                    icon=ICON_OFF
                )

            self.wf.send_feedback()
            return 0

        # ---------------------------------------------------------
        # List active or inactive countries

        if query.startswith('active'):  # List active countries
            query = query[6:].strip()
            log.debug('query : %r', query)

            countries = user_countries[:]

            if query:
                countries = self.wf.filter(query, countries, min_score=30)

            for c in sorted(countries):
                self.wf.add_item(c,
                                 '↩ to deactivate',
                                 arg='deactivate {0}'.format(c),
                                 valid=True,
                                 icon=FLAGS[c])

            self.wf.send_feedback()

        elif query.startswith('inactive'):  # List inactive countries
            query = query[8:].strip()
            log.debug('query : %r', query)

            # Inactive countries
            countries = set(COUNTRIES) - set(user_countries)

            if query:
                countries = self.wf.filter(query, countries, min_score=30)

            for c in sorted(countries):
                self.wf.add_item(c,
                                 '↩ to activate',
                                 arg='activate {0}'.format(c),
                                 valid=True,
                                 icon=FLAGS[c])

            self.wf.send_feedback()

    def do_deactivate(self, country):
        """Deactivate country and re-open settings."""

        if country == 'ALL':
            self.wf.settings['countries'] = []
            msg = 'Deactivated all countries'
            print(msg)
            log.debug(msg)
            self._call_countries_trigger()
            return 0

        if country in self.wf.settings['countries']:
            self.wf.settings['countries'].remove(country)
            self.wf.settings.save()
            msg = 'Deactivated {0}'.format(country)
            log.debug(msg)
            print(msg)
            return self._call_countries_trigger('active ')

    def do_activate(self, country):
        """Activate country and re-open settings."""

        if country == 'ALL':
            self.wf.settings['countries'] = COUNTRIES[:]
            msg = 'Activated all countries'
            print(msg)
            log.debug(msg)
            self._call_countries_trigger()
            return 0

        if country not in self.wf.settings['countries']:
            self.wf.settings['countries'].append(country)
            self.wf.settings.save()
            msg = 'Activated {0}'.format(country)
            log.debug(msg)
            print(msg)
            return self._call_countries_trigger('inactive ')

    # ---------------------------------------------------------
    # Helpers

    def _filter_for_countries(self, results):
        """Remove results that don't match user's configured countries."""

        filtered = []
        for r in results:
            item_countries = set(r['countries'])
            user_countries = set(self.wf.settings.get('countries', []))
            if item_countries & user_countries:
                filtered.append(r)

        return filtered

    def _call_countries_trigger(self, query=None):
        """Tell Alfred to show countries configuration.

        Call external trigger via AppleScript.

        """

        script = ('tell application "Alfred 2" to run trigger "countries" '
                  'in workflow "net.deanishe.alfred-flixsearch"')

        if query:
            script += ' with argument "{0}"'.format(query)

        cmd = [b'/usr/bin/osascript', '-e', script.encode('utf-8')]
        proc = subprocess.call(cmd)
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError('Could not call Alfred via AppleScript')

        return 0

if __name__ == '__main__':
    wf = Workflow(
        default_settings=DEFAULT_SETTINGS,
        update_settings=UPDATE_SETTINGS,
        help_url=HELP_URL,
    )
    log = wf.logger
    app = FlixSearch()
    sys.exit(wf.run(app.run))
