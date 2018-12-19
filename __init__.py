#!/usr/bin/env python3
#author: thuhak.zhou@nio.com
import logging
from logging.handlers import RotatingFileHandler

from conf import config
from downloader import FileDownloader


def get_level():
    return getattr(logging, logconfig['level'].upper())


ftpconfig = config['ftp']
logconfig = config['log']
logger = logging.getLogger(__name__)
loghandler = RotatingFileHandler(logconfig['path'], maxBytes=10*1024*1024, backupCount=10, encoding='utf-8')
logging.basicConfig(
        level=get_level(),
        format='%(asctime)s [%(levelname)s]: %(message)s',
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[loghandler, logging.StreamHandler()]
        )


if __name__ == '__main__':
    with FileDownloader(**ftpconfig) as downloader:
        downloader.run()
