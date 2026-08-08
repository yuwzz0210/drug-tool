# -*- coding: utf-8 -*-
"""定时调度：生成每日 09:00 / 15:00 的 crontab 条目（规格 5.1）。"""
from config import CRON_TIMES


def build_cron_lines(command, times=CRON_TIMES):
    return ["{} {}".format(t, command) for t in times]


def daily_commands(project_dir, python="python"):
    cmd = "cd {} && {} main.py crawl --source nmpa".format(project_dir, python)
    return build_cron_lines(cmd)
