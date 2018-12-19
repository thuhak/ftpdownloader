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
from db import FileMapper, History, session_scope


def ftp_path_join(base, filename):
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

    def process_data(self):
        with session_scope() as session:
            while True:
                data = self.queue.get()
                if data is JobDone:
                    logging.info('all job done')
                    break
                tmpfile, targetdir, remotefile, mtime, size, processeddir = data
                filename = os.path.basename(remotefile)
                logging.info('processing file {}'.format(tmpfile))
                checksum = calc_md5(tmpfile)
                if not checksum:
                    logging.error('can not check {} md5sum'.format(filename))
                    continue
                samerecord = session.query(History).filter_by(size=size, md5sum=checksum).first()
                newrecord = History(filename=filename, size=size, mtime=mtime, md5sum=checksum)
                if samerecord:
                    logging.warning('{} was processed before, the old name is {}'.format(filename, samerecord.filename))
                    session.add(newrecord)
                    session.commit()
                else:
                    targetfile = os.path.join(targetdir, filename)
                    logging.info('prepare move {} to {}'.format(filename, targetdir))
                    try:
                        shutil.move(tmpfile, targetfile)
                        if processeddir:
                            processed_file = ftp_path_join(processeddir, filename)
                            self.ftp.rename(remotefile, processed_file)
                        session.add(newrecord)
                        session.commit()
                    except:
                        logging.error('can not move {} to {}'.format(tmpfile, targetfile))
                        continue


    def _download_file(self, dbsession, targetdir, remotefile, mtime, size, processeddir):
        filename = os.path.basename(remotefile)
        current_time = datetime.utcnow()
        if (current_time - mtime).seconds < 180:
            logging.info('{} was uploaded within 3 minute, perhaps still uploading'.format(filename))
            return
        record = dbsession.query(History).filter_by(filename=filename, mtime=mtime, size=size).first()
        if record is None:
            tmpfile = NamedTemporaryFile(delete=False)
            # try:
            self.ftp.retrbinary('RETR ' + filename, tmpfile.write)
            tmpfile.close()
            data = (tmpfile.name, targetdir, remotefile, mtime, size, processeddir)
            self.queue.put(data)
            # except Exception as e:
            #     logging.error('can not download file {}'.format(filename))
        else:
            logging.info('{} was processed before'.format(filename))

    def _download(self, dbsession, remotedir, targetdir, regex=None, processeddir=None):
        pwd = self.ftp.pwd()
        self.ftp.cwd(remotedir)
        currentdir = list(self.ftp.mlsd())
        for i in currentdir:
            name = i[0]
            prop = i[1]
            if prop['type'] == 'dir':
                return self._download(dbsession, name, targetdir, regex)
            elif prop['type'] == 'file':
                remotepath = ftp_path_join(pwd, name)
                if regex:
                    m = re.match(regex, name)
                    if not m:
                        logging.debug('{} does not match regex {}, pass it'.format(name, regex))
                        continue
                mtime = datetime.strptime(prop['modify'], '%Y%m%d%H%M%S')
                size = int(prop['size'])
                self._download_file(dbsession, targetdir, remotepath, mtime, size, processeddir)
        self.ftp.cwd('..')

    def download(self):
        self.ftp.cwd('/')
        with session_scope() as dbsession:
            jobs = dbsession.query(FileMapper).all()
            for job in jobs:
                targetdir = job.localdir
                if not os.path.exists(targetdir):
                    logging.error('local directory {} does not exist'.format(targetdir))
                    continue
                basedir = ftp_path_join('/', job.basedir)
                remotedir = job.remotedir
                processeddir = job.processeddir
                if not processeddir and self.default_processed:
                    processeddir = remotedir + self.default_processed
                regex = job.regex
                if not regex:
                    regex = self.default_regex
                try:
                    self.ftp.cwd(basedir)
                except:
                    logging.error('there is no base directory {}'.format(basedir))
                    continue
                l = self.ftp.nlst()
                if remotedir not in l:
                    logging.info('creating directory {}'.format(remotedir))
                    self.ftp.mkd(remotedir)
                    continue
                if processeddir and processeddir not in l:
                    logging.info('creating directory {}'.format(processeddir))
                    self.ftp.mkd(processeddir)
                if processeddir:
                    processeddir = ftp_path_join(basedir, processeddir)
                self._download(dbsession, remotedir, targetdir, regex, processeddir)
                self.ftp.cwd('/')
        self.queue.put(JobDone)

    def run(self):
        process = threading.Thread(target=self.process_data)
        process.start()
        # try:
        self.download()
        # except Exception as e:
        #     logging.error('fatal error {}, stopping job'.format(str(e)))
        #     self.queue.put(JobDone)
        process.join()
