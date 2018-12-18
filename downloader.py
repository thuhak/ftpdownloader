import os
import shutil
import ftplib
import logging
from hashlib import md5
from functools import partial
from datetime import datetime
from tempfile import NamedTemporaryFile
from queue import Queue
import re
from db import DBSession, FileMapper, History
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


class JobDone(Exception):
    pass


class FileDownloader:
    def __init__(self, host, user, password, port=21, tls=False, default_regex=None, timeout=3):
        self.host = host
        self.tls = tls
        self.port = port
        self.timeout = timeout
        self.user = user
        self.password = password
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

    def handle_data(self):
        session = DBSession()
        while True:
            data = self.queue.get()
            if data is JobDone:
                logging.info('all job done')
                break
            else:
                tmpfile, targetdir, filename, mtime, size = data
                logging.info('processing file {}'.format(tmpfile))
                checksum = calc_md5(tmpfile)
                samerecord = session.query(History).filter_by(size=size, md5sum=checksum).first()
                newrecord = History(filename=filename, size=size, mtime=mtime, md5sum=checksum)
                if samerecord:
                    logging.warning('{} was processed before, the old name is {}'.format(filename, samerecord.filename))
                    session.add(newrecord)
                else:
                    targetfile = os.path.join(targetdir, filename)
                    logging.info('prepare move {} to {}'.format(filename, targetdir))
                    try:
                        shutil.move(tmpfile, targetfile)
                        session.add(newrecord)
                    except:
                        logging.error('can not move {} to {}'.format(filename, targetfile))
                session.commit()
        session.close()


    def _download_file(self, dbsession, targetdir, filename, mtime, size):
        current_time = datetime.utcnow()
        if (current_time - mtime).seconds < 180:
            logging.info('{} was uploaded within 3 minute, perhaps still uploading'.format(filename))
            return
        record = dbsession.query(History).filter_by(filename=filename, mtime=mtime, size=size).first()
        if record is None:
            tmpfile = NamedTemporaryFile(delete=False)
            try:
                self.ftp.retrbinary('RETR' + filename, tmpfile.write)
                tmpfile.close()
                data = (tmpfile.name, targetdir, filename, mtime, size)
                self.queue.put(data)
            except:
                logging.error('can not download file {}'.format(filename))
        else:
            logging.info('{} was processed before'.format(filename))


    def _download(self, dbsession, remotedir, targetdir, regex=None):
        self.ftp.cwd(remotedir)
        l = self.ftp.mlsd()
        for i in l:
            name = i[0]
            prop = i[1]
            if prop['type'] == 'dir':
                return self._download(dbsession, name, targetdir, regex)
            elif prop['type'] == 'file':
                if not regex:
                    regex = self.default_regex
                if regex:
                    m = re.match(regex, name)
                    if not m:
                        logging.debug('{} does not match regex {}, pass it'.format(name, regex))
                        continue
                mtime = datetime.strptime(prop['modify'], '%Y%m%d%H%M%S')
                size = int(prop['size'])
                self._download_file(dbsession, targetdir, name, mtime, size)
        self.ftp.cwd('..')


    def download(self):
        dbsession = DBSession()
        jobs = dbsession.query(FileMapper).all()

