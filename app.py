# -*- coding: utf-8 -*-
import json
import os
import time
import urllib2
import re
from threading import Lock

import feedparser
from flask import Flask
from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy

feed_list = ['http://oabt004.com/index/rss?type=magnet']
aria2_url = 'http://souji.iok.la:6800/jsonrpc'
token = 'huangsheng'
tv_list = []

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = 'hard to guess string'
app.config['SQLALCHEMY_DATABASE_URI'] = \
    'sqlite:///' + os.path.join(basedir, 'data.sqlite')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class Rss(db.Model):
    __tablename__ = 't_rss'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(2048))
    link = db.Column(db.String(2048))
    description = db.Column(db.String(2048))
    create_time = db.Column(db.String(10))

    def __repr__(self):
        return '<Rss %r>' % self.title


class Config(object):
    SCHEDULER_API_ENABLED = True


scheduler = APScheduler()
app.config.from_object(Config())
scheduler.init_app(app)
scheduler.start()

lock = Lock()


@app.route('/')
def hello_world():
    api_list = 'api_list:' \
               '</br>{' \
               '</br>/tv/&lt;tv_name&gt;/add' \
               '</br>/tv/&lt;index&gt;/delete' \
               '</br>/tv/list' \
               '</br>}'
    return api_list


@app.route('/tv/<tv_name>/add')
def add_tv_list(tv_name):
    lock.acquire()
    tv_list.append(tv_name)
    lock.release()
    return str(tv_list)


@app.route('/tv/<index>/delete')
def delete_tv_list(index):
    lock.acquire()
    tv_list.remove(tv_list[int(index) - 1])
    lock.release()
    return str(tv_list)


@app.route('/tv/list')
def list_tv():
    return str(tv_list)


def filter_file(title):
    if (not re.match(".*([S,s][0-9]+)?[E,e][0-9]+.*", title)) and (not re.match(".*[E,e][P,p][0-9]+.*", title)) \
            and (not re.match(".*第[一,二,三,四,五,六,七,八,九,十,0-9]+季.*", title)):
        return True
    flag = False
    lock.acquire()
    for tv in tv_list:
        if title.__contains__(tv):
            flag = True
            break
    lock.release()
    return flag


def read_rss(url):
    rss_list = []
    fp = feedparser.parse(url)
    for e in fp.entries:
        if filter_file(e.title):
            rss = Rss()
            rss.title = e.title
            rss.link = e.links[0].href
            rss.description = e.description
            rss.create_time = str(int(time.time()))
            rss_list.append(rss)
    return rss_list


def rss_add(rss):
    session = db.session
    session.add(rss)
    session.commit()
    session.close()


def rss_all():
    session = db.session
    rss_list = session.query(Rss).all()
    session.close()
    return rss_list


def get_mag(link):
    return link[:60]


def is_exist(rss, db_rss_list):
    for db_rss in db_rss_list:
        if get_mag(rss.link).__eq__(get_mag(db_rss.link)) or rss.title.__eq__(db_rss.title):
            return True
    return False


def call_aria_task(link):
    json_req = json.dumps({'jsonrpc': '2.0', 'id': 'qwer',
                           'method': 'aria2.addUri',
                           'params': ["token:" + token, [link]]})
    urllib2.urlopen(aria2_url, json_req)


def batch_add(rss_list):
    db_rss_list = rss_all()
    for rss in rss_list:
        if not is_exist(rss, db_rss_list):
            try:
                link = rss.link
                rss_add(rss)
                call_aria_task(link)
            except Exception as e:
                print(e)


def rss_task():
    for url in feed_list:
        rss_list = read_rss(url)
        batch_add(rss_list)


@scheduler.task('cron', id='do_rss_task', minute='1')
def run_rss_task():
    print("execute the job,current time=" + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())))
    rss_task()


def rss_delete(rss):
    session = db.session
    session.delete(rss)
    session.commit()
    session.close()


def clear_db_task():
    db_rss_list = rss_all()
    current_time = int(time.time())
    for rss in db_rss_list:
        if (current_time - int(rss.create_time)) / 604800 >= 1:
            rss_delete(rss)


@scheduler.task('cron', id='do_clear_db_task', day_of_week='mon', hour='1', minute='30')
def do_clear_db_task():
    print("execute the job,current time=" + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())))
    clear_db_task()
