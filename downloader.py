import os
import ftplib
import logging
from hashlib import md5
from functools import partial
from datetime import datetime
from queue import Queue
import re
from db import DBSession, History
from conf import config


def calc_md5(some_file):
    mymd5 = md5()
    try:
        with open(some_file, 'rb') as f:
            data = iter(partial(f.read, 8192), b'')
            for d in data:
                mymd5.update(d)
        return mymd5.hexdigest()
    except:
        return None


def choosename(path, name):
    count = 1
    while True:
        filename = os.path.join(path, name)
        if os.path.exists(filename):
            name += '.'+str(count)
            continue
        else:
            return filename


class FileDownloader:
    def __init__(self, host, user, password, tmpdir, port=21, tls=False, default_regex=None, timeout=3):
        self.host = host
        self.tls = tls
        self.port = port
        self.timeout = timeout
        self.user = user
        self.password = password
        self.tmpdir = tmpdir
        self.default_regex = default_regex
        self.queue = Queue()

    def __enter__(self):
        if self.tls:
            ftp = ftplib.FTP_TLS()
            ftp.connect(self.host, self.port, self.timeout)
            ftp.auth()
            ftp.login(self.user, self.timeout)
        else:
            ftp = ftplib.FTP()
            ftp.connect(self.host, self.port, self.timeout)
            ftp.login(self.user, self.timeout)
        self.ftp = ftp
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ftp.close()

    def _cwd(self, remotedir):
        dirs = remotedir.split('/')
        self.ftp.cwd('/')
        for d in dirs:
            try:
                self.ftp.cwd(d)
            except:
                self.ftp.mkd(d)
                self.ftp.cwd(d)

    def _download_file(self, dbsession, localdir, filename, mtime, size):
        current_time = datetime.utcnow()
        if (current_time - mtime).seconds < 180:
            logging.info('{} was uploaded within 3 minute, perhaps still uploading'.format(filename))
            return
        record = dbsession.query(History).filter_by(filename=filename, mtime=mtime, size=size).first()
        if record is None:
            # localfile = os.path.join(localdir, filename)
            tmpfile = choosename(self.tmpdir, filename)
            try:
                with open(tmpfile, 'wb') as f:
                    self.ftp.retrbinary('RETR' + filename, f.write)
                data = (tmpfile, localdir, filename, mtime, size)
                self.queue.put(data)
            except:
                logging.error('can not download file {}'.format(filename))

    def _download(self, remotefile, filetype, mtime, regex=None):
        if filetype == 'dir':
            self.ftp.cwd(remotefile)
            l = self.ftp.mlsd()
            for i in l:
                name = i[0]
                prop = i[1]
                if prop['type'] == 'dir':
                    return self._download(name, )
        if not regex:
            regex = self.default_regex
