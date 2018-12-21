#!/usr/bin/env python3
import os
import logging
from datetime import timedelta
from flask import Flask, jsonify, make_response
from flask_restful import Resource, Api, reqparse, abort
from flask_httpauth import HTTPBasicAuth
from celery import Celery
from celery.schedules import crontab

from .downloader import FileDownloader
from .db import FileMapper, History, session_scope
from .conf import config


logging.basicConfig(level=logging.DEBUG)
api_conf = config['api']
ftp_conf = config['ftp']
schedule_conf = config['schedule']
redis_conf = config['redis']

if 'timedelta' in schedule_conf:
    schedule = timedelta(**schedule_conf['timedelta'])
elif 'crontab' in schedule_conf:
    schedule = crontab(**schedule_conf['crontab'])

CELERYBEAT_SCHEDULE = {
    "download": {
        "task": "download",
        "schedule": schedule
    }
}

app = Flask(__name__)
app.config.update(RESTFUL_JSON=dict(ensure_ascii=False))
app.config.update(JSON_AS_ASCII=False)
app.config.update(CELERYBEAT_SCHEDULE=CELERYBEAT_SCHEDULE)

def make_celery(app):
    celery = Celery(app.import_name,
                    backend=app.config['CELERY_RESULT_BACKEND'],
                    broker=app.config['CELERY_BROKER_URL']
                    )
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery


redis_url = 'redis://:{password}@{host}:{port}/{db}'.format(**redis_conf)
app.config.update(
    CELERY_BROKER_URL=redis_url,
    CELERY_RESULT_BACKEND=redis_url)
celery = make_celery(app)
api = Api(app)
webauth = HTTPBasicAuth()
jobs_history = {}


parser = reqparse.RequestParser()
parser.add_argument('localdir', type=str, location='json')
parser.add_argument('basedir', type=str, location='json')
parser.add_argument('remotedir', type=str, location='json')
parser.add_argument('processeddir', type=str, default=None, location='json')
parser.add_argument('regex', type=str, default=None, location='json')
parser.add_argument('force_create', type=bool, default=False, location='json')


@celery.task(name="download")
def download():
    with FileDownloader(**ftp_conf) as downloader:
        ret = downloader.run()
    return ret


@webauth.get_password
def get_password(username):
    if username == api_conf['user']:
        return api_conf['password']
    return None


@webauth.error_handler
def unauthorized():
    return make_response(jsonify({'error': 'Unauthorized access'}), 401)


class DownLoader(Resource):
    @webauth.login_required
    def get(self):
        with session_scope() as session:
            mappers = session.query(FileMapper).all()
            ret = [x.to_dict() for x in mappers]
        return ret

    @webauth.login_required
    def post(self):
        args = parser.parse_args()
        keys = set(args.keys())
        full = {'localdir', 'basedir', 'remotedir', 'processeddir', 'regex', 'force_create'}
        needed = {'localdir', 'basedir', 'remotedir'}
        force_create = args.pop('force_create')
        localdir = args['localdir']
        basedir = args['basedir']

        if not keys.issubset(full) or not needed.issubset(keys):
            abort(400, error='invalid parameters')
        if not os.path.exists(localdir):
            if force_create:
                try:
                    os.mkdir(localdir)
                except:
                    abort(403, error='can not create local directory {}'.format(localdir))
            else:
                abort(403, error='there is no local directory {}'.format(localdir))

        try:
            with FileDownloader(**ftp_conf) as downloader:
                basecheck = downloader.check_dir(basedir)
            if not basecheck:
                abort(403, error='base directory not valid')
        except:
            abort(403, error="can not connect to ftp server, please check network and configuration")

        with session_scope() as session:
            check = session.query(FileMapper).filter_by(localdir=localdir, basedir=basedir, remotedir=args['remotedir']).first()
            if check:
                abort(403, error='mapping is already in database')
            else:
                try:
                    new = FileMapper(**args)
                    session.add(new)
                    return {'result': True}
                except:
                    abort(500, error='can not update record')

    @webauth.login_required
    def delete(self, id):
        with session_scope() as session:
            record = session.query(FileMapper).filter_by(id=id).first()
            if not record:
                abort(404, error='not valid id')
            session.delete(record)


class Job(Resource):
    @webauth.login_required
    def put(self):
        old_job = jobs_history.get('download')
        if not old_job or download.AsyncResult(old_job).ready():
            logging.info('starting download job')
            job = download.delay()
            jobs_history['download'] = job.task_id
            return {'job_id': job.task_id}
        else:
            abort(403, error='last download job is not finished')

    @webauth.login_required
    def get(self, taskid):
        try:
            ret = download.AsyncResult(taskid).get(timeout=0.5)
        except:
            abort(403, error='job is not finish')
        return ret


class DownloadHistory(Resource):
    def get(self):
        with session_scope() as session:
            history = session.query(History).all()
            ret = [x.to_dict() for x in history]
        return jsonify(ret)


api.add_resource(DownLoader, '/mapper', '/mapper/<int:id>')
api.add_resource(Job, '/job', '/job/<string:taskid>')
api.add_resource(DownloadHistory, '/history')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5337, debug=True)
