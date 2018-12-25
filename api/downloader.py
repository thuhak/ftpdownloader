import os
import shutil
import ftplib
import logging
import threading
from hashlib import md5
from functools import partial
from datetime import datetime
from tempfile import NamedTemporaryFile
from queue import Queue
import re

from .db import FileMapper, History, session_scope


__all__ = ['FileDownloader']


def ftp_path_join(base, filename):
    '''for windows comp'''
    if filename.startswith('/'):
        filename = filename[1:]
    if base.endswith('/'):
        return base + filename
    else:
        return base + '/' + filename


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
    def __init__(self, host, user, password, port=21, tls=False, timeout=3, default_regex=None, default_processed=None):
        self.host = host
        self.tls = tls
        self.port = port
        self.timeout = timeout
        self.user = user
        self.password = password
        self.default_regex = default_regex
        self.default_processed = default_processed
        self.queue = Queue()
        self.lock = threading.Lock()

    def __enter__(self):
        if self.tls:
            ftp = ftplib.FTP_TLS()
            ftp.encoding = 'utf-8'
            ftp.connect(self.host, self.port, self.timeout)
            ftp.auth()
            ftp.login(self.user, self.password, self.timeout)
        else:
            ftp = ftplib.FTP()
            ftp.encoding = 'utf-8'
            ftp.connect(self.host, self.port, self.timeout)
            ftp.login(self.user, self.password, self.timeout)
        self.ftp = ftp
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ftp.close()

    def check_dir(self, basedir, enter=False):
        with self.lock:
            current_dir = self.ftp.pwd()
            try:
                base = ftp_path_join('/', basedir)
                self.ftp.cwd(base)
            except ftplib.Error:
                return False
            if not enter:
                self.ftp.cwd(current_dir)
            return True

    def process_data(self, ret_log):
        with session_scope() as session:
            while True:
                data = self.queue.get()
                if data is JobDone:
                    logging.info('all job done')
                    break
                tmpfile, targetdir, remotefile, mtime, size, processeddir, mapperid = data
                filename = os.path.basename(remotefile)
                targetfile = os.path.join(targetdir, filename)
                if processeddir:
                    processed_file = ftp_path_join(processeddir, filename)
                logging.debug('processing file {}'.format(tmpfile))
                checksum = calc_md5(tmpfile)
                if not checksum:
                    msg = 'can not check {} md5sum'.format(filename)
                    ret_log.append(msg)
                    logging.error(msg)
                    continue
                samerecord = session.query(History).filter_by(size=size, md5sum=checksum).first()
                newrecord = History(filename=filename, size=size, mtime=mtime, md5sum=checksum, mapperid=mapperid)
                if samerecord:
                    logging.warning('{} was processed before, the old name is {}'.format(filename, samerecord.filename))
                    self._move_processed(remotefile, processed_file)
                    session.add(newrecord)
                    session.commit()
                else:
                    logging.debug('prepare to move local file {} to {}'.format(filename, targetdir))
                    try:
                        shutil.move(tmpfile, targetfile)
                        self._move_processed(remotefile, processed_file)
                        session.add(newrecord)
                        session.commit()
                    except ftplib.Error:
                        logging.error('can not move remote file {} to {}'.format(remotefile, processed_file))
                    except Exception as e:
                        logging.error('can not move local file {} to {}'.format(tmpfile, targetfile))
                        continue

    def _move_processed(self, remotefile, processed_file):
        logging.debug('prepare to move remote file {} to {}'.format(remotefile, processed_file))
        try:
            with self.lock:
                self.ftp.rename(remotefile, processed_file)
        except:
            logging.error('can not move remote file {} to {}'.format(remotefile, processed_file))


    def _download_file(self, dbsession, targetdir, remotefile, mtime, size, processeddir, mapperid, ret_log):
        filename = os.path.basename(remotefile)
        current_time = datetime.utcnow()
        if (current_time - mtime).seconds < 180:
            msg = '{} was uploaded within 3 minute, perhaps still uploading'.format(filename)
            ret_log.append(msg)
            logging.info(msg)
            return
        record = dbsession.query(History).filter_by(filename=filename, mtime=mtime, size=size).first()
        if record is None:
            tmpfile = NamedTemporaryFile(delete=False)
            try:
                with self.lock:
                    self.ftp.retrbinary('RETR ' + filename, tmpfile.write)
                tmpfile.close()
                data = (tmpfile.name, targetdir, remotefile, mtime, size, processeddir, mapperid)
                self.queue.put(data)
            except Exception as e:
                msg = 'can not download file {}'.format(filename)
                ret_log.append(msg)
                logging.error(msg)
        else:
            self._move_processed(remotefile, processeddir)
            logging.info('{} was processed before'.format(filename))

    def _download(self, dbsession, remotedir, targetdir, regex, processeddir, mapperid, ret_log):
        with self.lock:
            self.ftp.cwd(remotedir)
            pwd = self.ftp.pwd()
            currentdir = list(self.ftp.mlsd())
        for i in currentdir:
            name = i[0]
            prop = i[1]
            if prop['type'] == 'dir':
                self._download(dbsession, name, targetdir, regex, processeddir, mapperid, ret_log)
            elif prop['type'] == 'file':
                remotepath = ftp_path_join(pwd, name)
                if regex:
                    m = re.match(regex, name)
                    if not m:
                        msg = '{} does not match regex {}, pass it'.format(name, regex)
                        logging.debug(msg)
                        continue
                mtime = datetime.strptime(prop['modify'], '%Y%m%d%H%M%S')
                size = int(prop['size'])
                self._download_file(dbsession, targetdir, remotepath, mtime, size, processeddir, mapperid, ret_log)
        with self.lock:
            self.ftp.cwd('..')

    def download(self, ret_log):
        with self.lock:
            self.ftp.cwd('/')
        with session_scope() as dbsession:
            jobs = dbsession.query(FileMapper).all()
            for job in jobs:
                targetdir = job.localdir
                if not os.path.exists(targetdir):
                    msg = 'local directory {} does not exist'.format(targetdir)
                    ret_log.append(msg)
                    logging.error(msg)
                    continue
                mapperid = job.id
                basedir = ftp_path_join('/', job.basedir)
                remotedir = job.remotedir
                processeddir = job.processeddir
                if not processeddir and self.default_processed:
                    processeddir = remotedir + self.default_processed
                regex = job.regex
                if not regex:
                    regex = self.default_regex
                checkbase = self.check_dir(basedir, enter=True)
                if not checkbase:
                    msg = 'there is no base directory {}'.format(basedir)
                    ret_log.append(msg)
                    logging.error(msg)
                    continue
                with self.lock:
                    l = self.ftp.nlst()
                if remotedir not in l:
                    logging.info('creating directory {}'.format(remotedir))
                    with self.lock:
                        self.ftp.mkd(remotedir)
                    continue
                if processeddir and processeddir not in l:
                    logging.info('creating directory {}'.format(processeddir))
                    with self.lock:
                        self.ftp.mkd(processeddir)
                if processeddir:
                    processeddir = ftp_path_join(basedir, processeddir)
                self._download(dbsession, remotedir, targetdir, regex, processeddir, mapperid, ret_log)
                with self.lock:
                    self.ftp.cwd('/')
        self.queue.put(JobDone)

    def run(self):
        ret_log = []
        ret = {'result': True, 'info': ret_log}
        process = threading.Thread(target=self.process_data, args=[ret_log])
        process.start()
        try:
            self.download(ret_log)
        except Exception as e:
            msg = 'fatal error {}, stopping job'.format(str(e))
            ret_log.append(msg)
            logging.error(msg)
            self.queue.put(JobDone)
            ret['result'] = False
        process.join()
        return ret
