#!/usr/bin/env python3
import os
import logging
import threading
from uuid import uuid4 as uuid

from flask import Flask, jsonify, make_response
from flask_restful import Resource, Api, reqparse, abort
from flask_httpauth import HTTPBasicAuth
from flask_apscheduler import APScheduler

from .downloader import FileDownloader
from .db import FileMapper, History, session_scope
from .conf import config


api_conf = config['api']
ftp_conf = config['ftp']
schedule_conf = config['schedule']

schedule_config = {'id': 'ftpdownload', 'func': 'api:download'}
schedule_config.update(schedule_conf)


app = Flask(__name__)
app.config.update(RESTFUL_JSON=dict(ensure_ascii=False))
app.config.update(JSON_AS_ASCII=False)


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


@webauth.get_password
def get_password(username):
    if username == api_conf['user']:
        return api_conf['password']
    return None


@webauth.error_handler
def unauthorized():
    return make_response(jsonify({'error': 'Unauthorized access'}), 401)


def download(job_id=None):
    global jobs_history
    with FileDownloader(**ftp_conf) as downloader:
        ret = downloader.run()
    if job_id:
        jobs_history[job_id] = ret
    return ret


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
        key = str(uuid())
        job = threading.Thread(target=download, args=(key,))
        job.start()
        return {'job_id': key}


    @webauth.login_required
    def get(self, taskid):
        if taskid in jobs_history:
            return jobs_history[taskid]
        else:
            abort(403, error='job is not finish')


class DownloadHistory(Resource):
    def get(self):
        with session_scope() as session:
            history = session.query(History).all()
            ret = [x.to_dict() for x in history]
        return jsonify(ret)


api.add_resource(DownLoader, '/mapper', '/mapper/<int:id>')
api.add_resource(Job, '/job', '/job/<string:taskid>')
api.add_resource(DownloadHistory, '/history')

app.config.update(JOBS=[schedule_config])
app.config.update(SCHEDULER_API_ENABLED=True)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5337, debug=True)
