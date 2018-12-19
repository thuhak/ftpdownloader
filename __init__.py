import logging
from logging.handlers import RotatingFileHandler
import threading
import time
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

def change_level():
    while True:
        new_level = get_level()
        cur_level = logging.getLevelName(logging.getLogger().level)
        if cur_level != new_level:
            logging.getLogger().setLevel(new_level)
        time.sleep(3)



if __name__ == '__main__':
    dyn_conf = threading.Thread(target=change_level)
    dyn_conf.setDaemon(True)
    dyn_conf.start()
    with FileDownloader(**ftpconfig) as downloader:
        downloader.run()
