# -*- coding: utf-8 -*-
"""Configuration for the KY bracket scraper (szky1688.com/ky/).

All paths are resolved relative to this file so the scraper can be
launched from any working directory.
"""

from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
IMAGE_DIR = os.path.join(DATA_DIR, "images")
REPORT_DIR = os.path.join(DATA_DIR, "report")
LOG_DIR = os.path.join(BASE_DIR, "logs")
DB_PATH = os.path.join(DATA_DIR, "ky.db")

SITE_ROOT = "http://www.szky1688.com"
INDEX_URL = SITE_ROOT + "/ky/"
BRAND_LIST_URL = SITE_ROOT + "/Car/"
BRACKET_LIST_URL = SITE_ROOT + "/2"
CAR_SHOW_URL = SITE_ROOT + "/Car_show/?idd={idd}"
CAR2_URL = SITE_ROOT + "/Car2/?BigClassName={brand}"
PRODUCTS_URL = SITE_ROOT + "/Products/?BigClassName={brand}&SmallClassName={model}"

# Site pages are encoded in GB2312/GB18030; query strings must be
# percent-encoded with GBK, otherwise the server returns mojibake.
PAGE_ENCODING = "gb18030"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Politeness settings: the site is a single IIS box without CDN.
WORKERS = 3
MIN_INTERVAL = 0.5  # global seconds between two requests (>= 0.5s -> <= 2 req/s)
TIMEOUT = 30
MAX_RETRY = 3
RETRY_BACKOFF = 2.0

# Sampling ratio for the B2 (Products) stage.
DEFAULT_SAMPLE = 0.2

for _d in (DATA_DIR, RAW_DIR, IMAGE_DIR, REPORT_DIR, LOG_DIR):
    os.makedirs(_d, exist_ok=True)
