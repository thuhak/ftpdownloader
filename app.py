#!/usr/bin/env python
import logging
from logging.handlers import RotatingFileHandler
from api import app
from api.conf import config


LOG_LEVEL = getattr(logging, config['log']['level'].upper())
loghandler = RotatingFileHandler(config['log']['path'], maxBytes=10*1024*1024, backupCount=10)
logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s [%(levelname)s]: %(message)s',
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[loghandler, logging.StreamHandler()]
        )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5337, debug=True)
