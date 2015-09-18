#!/usr/bin/env python
# encoding: utf-8
#
# Copyright © 2015 deanishe@deanishe.net
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2015-09-17
#

"""
Copy required icons from V7 Flags to workflow.

Icons from http://alpercakici.deviantart.com/
"""

from __future__ import print_function, unicode_literals, absolute_import

import logging
import os
import shutil
import sys

mydir = os.path.abspath(os.path.dirname(__file__))
wfdir = os.path.abspath(os.path.join(mydir, '../src'))

sys.path.insert(0, wfdir)

import flix
from flix import COUNTRIES

logging.basicConfig()
log = logging.getLogger('')
flix.log = log

FLAG_DIR = os.path.expanduser('~/Pictures/Flags (V7)/Png/')


def main():
    """Search Flixsearch.io for QUERIES."""

    for c in COUNTRIES:
        filename = '{}.png'.format(c)
        src_path = os.path.join(FLAG_DIR, filename)
        dest_path = os.path.join(wfdir, 'icons', filename)
        if os.path.exists(src_path):
            if not os.path.exists(dest_path):
                shutil.copy(src_path, dest_path)
        else:
            print('No icon found for `{}`'.format(c))


if __name__ == '__main__':
    main()
