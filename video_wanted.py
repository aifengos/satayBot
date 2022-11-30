#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import psycopg2
from datetime import datetime, timezone, timedelta
import logging
import pandas as pd
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    filters,
    CallbackContext
)

BOT_TOKEN = ''

CHAT_TIMEOUT = 60

MENUS = ['新增求片', '当前列表', '更新列表（管理媛）']
TYPES = ['Anime & 动漫', 'Documentary & 纪录片', 'Movie & 电影', 'Series & 电视剧', 'Show & 综艺']
REGIONS = ['China/Hong Kong/Macau/Taiwan', 'Japan', 'Korea', 'United States/Europe', 'Others']
STATUS = ['提交', '接受', '上架', '删除']
UPDATE_OPS = ['查看当前列表查看ID', '直接输入ID进行更新']

WANTED_DICT = dict()
RETRIED = dict()
PROGRESS = dict()

UPDATE_OPT_ID = dict()

DELETE_MESSAGE_ID = dict()

ADMIN_USERS = []

initial = True

db_host = 'localhost'
db_user = ''
db_pw = ''
db_name = ''


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def db_init():
    # conn = psycopg2.connect(dbname=db_name, host=db_host,
    #                         user=db_user, password=db_pw)
    # cur = conn.cursor()
    # cur.execute(
    #     'DROP TABLE IF EXISTS wanted_info; CREATE TABLE IF NOT EXISTS wanted_info (wanted_id text, ' +
    #     'wanted_type text, wanted_region text, wanted_title text, wanted_date text, wanted_tmdb text, ' +
    #     'user_id text, user_name text, wanted_time text, wanted_status text, update_time text);')
    # conn.commit()  # <- We MUST commit to reflect the inserted data
    # cur.close()
    # conn.close()
    conn = psycopg2.connect(dbname=db_name, host=db_host,
                            user=db_user, password=db_pw)
    cur = conn.cursor()
    video_data = get_list(False)
    video_data['ID'] = video_data['ID'].astype(int)
    max_id = video_data['ID'].max()
    dup_video_data = video_data[video_data['ID'].duplicated(keep=False)].copy()
    dup_video_data.sort_values(['ID', 'ReqTime'], inplace=True)
    prev_id = 0
    for dup_records in dup_video_data[['ID', 'Type', 'Region', 'Title', 'Date', 'TMDB', 'user_id', 'ReqTime']].values:
        if dup_records[0] == prev_id:
            max_id += 1
            update_cmd = ("UPDATE wanted_info SET wanted_id = '" + str(max_id) +
                          "'  WHERE wanted_title='" + dup_records[3] + "' AND  user_id='" + dup_records[6] +
                          "' AND wanted_time='" + dup_records[7] + "'")
            print(update_cmd)
            cur.execute(update_cmd)
            conn.commit()  # <- We MUST commit to reflect the inserted data
        else:
            prev_id = dup_records[0]
    cur.close()
    conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send message on `/start`."""
    # Get user that sent /start and log his name
    user = update.message.from_user
    logger.info("User %s started the conversation.", user.first_name)
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text='欢迎使用Texon求片机器人，所有操作请在' + str(CHAT_TIMEOUT) + 's内完成',
                                   parse_mode='HTML')
    # Tell ConversationHandler that we're in state `FIRST` now
    return ConversationHandler.END


# 求片并选择类别
async def wanted(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    """Show new choice of buttons"""
    # if initial:
    #     WANTED_DICT[user_id] = {'Type': 'Anime & 动漫', 'Region': 'Japan', 'Title': 'Helpme', 'Date': '1999',
    #                    'TMDB': 'https://www.themoviedb.org/1999'}
    #     add_wanted(update, WANTED_DICT[user_id])
    keyboard = [
            [InlineKeyboardButton(item, callback_data=item)] for item in TYPES
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('请选择你想看的<b>类别</b>', reply_markup=reply_markup, parse_mode='HTML')
    WANTED_DICT[user_id] = dict()
    RETRIED[user_id] = dict()
    DELETE_MESSAGE_ID[user_id] = dict()
    PROGRESS[user_id] = 'Type'
    return 'REGION'


# 选择区域
async def region_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    query = update.callback_query
    await query.answer()
    WANTED_DICT[user_id]['Type'] = query.data
    mes_text = '已选类别: <b>' + WANTED_DICT[user_id]['Type'] + '</b>'
    cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
    DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
    keyboard = [
            [InlineKeyboardButton(item, callback_data=item)] for item in REGIONS
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    mes_text = "请选择你想看的 动漫/纪录片/电影/电视剧/综艺 的<b>国家</b>"
    cov_mes = await query.edit_message_text(text=mes_text, reply_markup=reply_markup, parse_mode='HTML')
    DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
    return 'TITLE'


# 输入片名
async def title_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    query = update.callback_query
    await query.answer()
    WANTED_DICT[user_id]['Region'] = query.data
    await update.callback_query.edit_message_reply_markup(None)
    mes_text = '已选区域: <b>' + WANTED_DICT[user_id]['Region'] + '</b>'
    cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
    DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
    mes_text = '请输入你想看的 动漫/纪录片/电影/电视剧/综艺 的<b>名字或译名</b>'
    cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
    DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
    return 'DATE'


# 输入日期
async def date_input(update: Update, context: CallbackContext):
    user_id = update.effective_chat.id
    DELETE_MESSAGE_ID[user_id][update.message.id] = update.message.text.strip()
    if 'Title' not in WANTED_DICT[user_id]:
        WANTED_DICT[user_id]['Title'] = update.message.text.strip()
        mes_text = '已输入片名: <b>' + WANTED_DICT[user_id]['Title'] + '</b>'
        cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
        DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
    mes_text = '请输入这部 动漫/纪录片/电影/电视剧/综艺 的<b>上映年份</b>'
    cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
    DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
    return 'TMDB'


# 输入TMDB链接
async def tmdb_input(update: Update, context: CallbackContext):
    user_id = update.effective_chat.id
    text = update.message.text.strip()
    DELETE_MESSAGE_ID[user_id][update.message.id] = update.message.text
    match_date = re.search(r'\d{4}', text)
    if match_date is not None:
        video_date = match_date[0]
        if video_date.startswith('19') or video_date.startswith('20'):
            WANTED_DICT[user_id]['Date'] = video_date
            mes_text = '已输入日期: <b>' + WANTED_DICT[user_id]['Date'] + '</b>'
            cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
            DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
    if 'Date' in WANTED_DICT[user_id]:
        mes_text = '请输入这部 动漫/纪录片/电影/电视剧/综艺 的<b>TMDB链接</b>'
        cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
        DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
        return 'SUMMARY'
    else:
        if 'Date' in RETRIED[user_id]:
            mes_text = '<b>上映年份再次错误</b>，请核实'
            await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
            await clean(update, context)
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='<b>欢迎再次使用Texon求片机器人</b>', parse_mode='HTML')
            return ConversationHandler.END
        else:
            RETRIED[user_id]['Date'] = True
            mes_text = '上映年份错误，必须是<b>19或者20开头的4位数字</b>'
            cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text,
                                                     parse_mode='HTML')
            DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
            return 'TMDB'


# 结束输入
async def finish_input(update: Update, context: CallbackContext):
    user_id = update.effective_chat.id
    user_name = update.effective_chat.username
    text = update.message.text.strip()
    DELETE_MESSAGE_ID[user_id][update.message.id] = text
    if text.startswith('https://www.themoviedb.org/') or text.startswith('www.themoviedb.org/'):
        WANTED_DICT[user_id]['TMDB'] = text
    if 'TMDB' in WANTED_DICT[user_id]:
        video_id = add_wanted(update, WANTED_DICT[user_id])
        video_info = ('已收录求片信息：\n' + '\n'.join(
            [k + ': <b>' + v + '</b>' for k, v in WANTED_DICT[user_id].items()]) + '\n 管理员可能会私聊您确认相关信息')
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text=video_info, parse_mode='HTML', disable_web_page_preview=True)
        if (user_name is not None) and user_name:
            WANTED_DICT[user_id]['User'] = ('<a href="tg://user?id=' + html_format(str(user_id)) +
                                            '">@' + user_name + '</a>')
        else:
            WANTED_DICT[user_id]['User'] = ('<a href="tg://user?id=' + html_format(str(user_id)) + '">' +
                                            html_format(str(user_id)) + '</a>')

        admin_notify = ('有新的求片请求：\nReq_ID: <b>' + video_id + '</b>\n' + '\n'.join(
            [k + ': <b>' + v + '</b>' for k, v in WANTED_DICT[user_id].items()]))
        for admin_id in ADMIN_USERS:
            # if user_id != admin_id:
            await context.bot.send_message(chat_id=admin_id,
                                           text=admin_notify, parse_mode='HTML', disable_web_page_preview=True)
        await clean(update, context)
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text='<b>欢迎再次使用Texon求片机器人</b>', parse_mode='HTML')
        return ConversationHandler.END
    else:
        if 'TMDB' in RETRIED[user_id]:
            mes_text = '<b>TMDB链接再次错误</b>，请核实'
            await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
            await clean(update, context)
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='<b>欢迎再次使用Texon求片机器人</b>', parse_mode='HTML')
            return ConversationHandler.END
        else:
            RETRIED[user_id]['TMDB'] = True
            mes_text = 'TMDB链接，<b>必须是以 https://www.themoviedb.org/ 开头</b>'
            cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
            DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
            return 'SUMMARY'


async def cov_end(update: Update, context: CallbackContext):
    # print('Clean')
    # for DELETE_ID in DELETE_MESSAGE_ID:
    #     await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=DELETE_ID)
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text='<b>欢迎再次使用Texon求片机器人</b>', parse_mode='HTML')
    return ConversationHandler.END


# 查看当前求片列表
async def seesee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    list_info_data = get_list()
    if not list_info_data.empty:
        list_info_data.sort_values(['Type', 'Status', 'UpdateTime'], inplace=True)
        video_types = list_info_data['Type'].drop_duplicates().values
        video_info = list()
        for video_type in video_types:
            video_info.append('<b>' + video_type + '</b>')
            video_data = list_info_data[list_info_data['Type'] == video_type]
            wanted_records = list(video_data[['ID', 'Title', 'Status', 'user_id', 'user_name']].values)
            for wanted_record in wanted_records:
                # if (wanted_record[4] is not None) and wanted_record[4]:
                #     user_str = ('<a href="tg://user?id=' + html_format(wanted_record[3]) + '">@' +
                #                 html_format(wanted_record[4]) + '</a>')
                # else:
                #     user_str = ('<a href="tg://user?id=' + html_format(wanted_record[3]) + '">' +
                #                 html_format(wanted_record[3]) + '</a>')
                video_info.append(' - ' + html_format(wanted_record[0]) + ' ' + html_format(wanted_record[1]) +
                                  ' [' + html_format(wanted_record[2]) + ']')
        want_info = '<b>当前求片列表</b>：\n\n' + '\n'.join(video_info)
    else:
        want_info = '<b>当前没有求片请求</b>'
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=want_info, parse_mode='HTML', disable_web_page_preview=True)
    # await context.bot.send_message(chat_id=update.effective_chat.id,
    #                                text='<b>欢迎再次使用Texon求片机器人</b>', parse_mode='HTML')
    return ConversationHandler.END


# 更新求片信息并输入ID
async def update_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if ADMIN_USERS and (user_id not in ADMIN_USERS):
        await context.bot.send_message(chat_id=update.effective_chat.id, text='仅管理员可以更改状态')
        return ConversationHandler.END
    else:
        keyboard = [
            [InlineKeyboardButton(item, callback_data=item)] for item in UPDATE_OPS
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Send message with text and appended InlineKeyboard
        mes_text = '请选择要将该请求状态<b>变更</b>为'
        cov_mes = await update.message.reply_text(mes_text, reply_markup=reply_markup, parse_mode='HTML')
        DELETE_MESSAGE_ID[user_id] = {cov_mes.id: mes_text}
        UPDATE_OPT_ID[user_id] = ''
        RETRIED[user_id] = dict()
        return 'UPDATE_OPT'


async def update_opt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    query = update.callback_query
    await query.answer()
    opt_status = query.data
    if opt_status == '查看当前列表查看ID':
        update_data = get_list(False)
        info_str = format_video_list(update_data)
        if info_str:
            want_info = '<b>当前的所有求片信息如下</b>：\n\n' + info_str
            cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id,
                                                     text=want_info, parse_mode='HTML')
            DELETE_MESSAGE_ID[user_id][cov_mes.id] = want_info
        else:
            want_info = '<b>当前没有任何求片信息</b>'
            await context.bot.send_message(chat_id=update.effective_chat.id, text=want_info, parse_mode='HTML')
            await clean(update, context)
            return ConversationHandler.END
    mes_text = '请输入你想<b>更新状态</b>的<b>求片ID</b>'
    cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text, parse_mode='HTML')
    DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
    return 'INPUT_ID'


# 检查ID
async def input_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    update_id = update.message.text.strip()
    DELETE_MESSAGE_ID[user_id][update.message.id] = update_id
    update_data = get_list(False, update_id)
    current_status = list(update_data['Status'].drop_duplicates().values)
    new_status = [item for item in STATUS if item not in current_status]
    info_str = format_video_list(update_data)
    if info_str:
        want_info = '<b>' + update_id + '</b>的求片信息如下：\n\n' + info_str
        cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id,
                                                 text=want_info, parse_mode='HTML')
        DELETE_MESSAGE_ID[user_id][cov_mes.id] = want_info
        UPDATE_OPT_ID[user_id] = update_id
        keyboard = [
            [InlineKeyboardButton(item, callback_data=item)] for item in new_status
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Send message with text and appended InlineKeyboard
        mes_text = '请选择要将该请求状态<b>变更</b>为'
        cov_mes = await update.message.reply_text(mes_text, reply_markup=reply_markup, parse_mode='HTML')
        DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
        return 'CHANGE'
    else:
        if 'UPDATE' not in RETRIED[user_id]:
            mes_text = '<b>输入的ID不存在，请重新输入</b>'
            cov_mes = await context.bot.send_message(chat_id=update.effective_chat.id, text=mes_text,
                                                     parse_mode='HTML')
            DELETE_MESSAGE_ID[user_id][cov_mes.id] = mes_text
            RETRIED[user_id]['UPDATE'] = True
            UPDATE_OPT_ID[user_id] = ''
            return 'INPUT_ID'
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='<b>输入的ID再次错误</b>，请核实',
                                           parse_mode='HTML')
            await clean(update, context)
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='<b>欢迎再次使用Texon求片机器人</b>', parse_mode='HTML')
            return ConversationHandler.END


async def update_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    query = update.callback_query
    await query.answer()
    new_status = query.data
    await update.callback_query.edit_message_reply_markup(None)
    update_status(UPDATE_OPT_ID[user_id], new_status)
    update_data = get_list(False, UPDATE_OPT_ID[user_id])
    info_str = format_video_list(update_data)
    if info_str:
        want_info = ('ID:<b>' + UPDATE_OPT_ID[user_id] + '</b> 状态已被管理员变更为<b>' +
                     new_status + '</b>：\n\n' + info_str)
        req_users = list(update_data['user_id'].drop_duplicates().values)
        for req_user in req_users:
            await context.bot.send_message(chat_id=req_user, text=want_info, parse_mode='HTML',
                                           disable_web_page_preview=True)
    else:
        want_info = 'ID（<b>' + UPDATE_OPT_ID[user_id] + '</b>）已神秘消失，请核实ID信息'
    await context.bot.send_message(chat_id=update.effective_chat.id, text=want_info, parse_mode='HTML',
                                   disable_web_page_preview=True)
    await clean(update, context)
    return ConversationHandler.END


def add_wanted(update, info_dict):
    user_id = update.effective_chat.id
    user_name = update.effective_chat.username
    utc_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    curr_time = utc_dt.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    wanted_type = info_dict['Type']
    wanted_region = info_dict['Region']
    wanted_title = info_dict['Title']
    wanted_date = info_dict["Date"]
    wanted_tmdb = info_dict["TMDB"]
    wanted_data = get_list(False)
    if not wanted_data.empty:
        max_id = wanted_data['ID'].astype(int).max()
    else:
        max_id = 1000
    wanted_id = str(max_id + 1)
    wanted_status = '提交'
    conn = psycopg2.connect(dbname=db_name, host=db_host,
                            user=db_user, password=db_pw)
    cur = conn.cursor()
    postgres_insert = ('INSERT INTO wanted_info (wanted_id, wanted_type, wanted_region, wanted_title, ' +
                       'wanted_date, wanted_tmdb, user_id, user_name, wanted_time, wanted_status, update_time) ' +
                       'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)')
    record_to_insert = (wanted_id, wanted_type, wanted_region, wanted_title, wanted_date,
                        wanted_tmdb, user_id, user_name, curr_time, wanted_status, curr_time)
    cur.execute(postgres_insert, record_to_insert)
    conn.commit()  # <- We MUST commit to reflect the inserted data
    cur.close()
    conn.close()
    return wanted_id


def get_list(hide_delete=True, req_id=None):
    conn = psycopg2.connect(dbname=db_name, host=db_host,
                            user=db_user, password=db_pw)
    cur = conn.cursor()
    if req_id is None:
        query_cmd = "SELECT * FROM wanted_info"
    else:
        query_cmd = ("SELECT * FROM wanted_info WHERE wanted_id='" + str(req_id) + "'")
    cur.execute(query_cmd)
    wanted_result = cur.fetchall()
    cur.close()
    conn.close()
    if wanted_result:
        wanted_data = pd.DataFrame(wanted_result, columns=['ID', 'Type', 'Region',
                                                           'Title', 'Date', 'TMDB', 'user_id',
                                                           'user_name', 'ReqTime', 'Status', 'UpdateTime'])
        if hide_delete:
            wanted_data = wanted_data[~wanted_data['Status'].isin(['删除'])]
    else:
        wanted_data = pd.DataFrame()
    return wanted_data


def update_status(req_id, new_status):
    conn = psycopg2.connect(dbname=db_name, host=db_host,
                            user=db_user, password=db_pw)
    cur = conn.cursor()
    utc_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    curr_time = utc_dt.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    update_cmd = ("UPDATE wanted_info SET wanted_status = '" + str(new_status) +
                  "', update_time = '" + curr_time + "'  WHERE wanted_id='" + str(req_id) + "'")
    cur.execute(update_cmd)
    conn.commit()  # <- We MUST commit to reflect the inserted data
    cur.close()
    conn.close()


def format_video_list(list_info_data):
    if list_info_data.empty:
        return ''
    else:
        col_list = ['ID', 'Type', 'Region', 'Title', 'Date', 'TMDB', 'ReqTime', 'Status', 'UpdateTime']
        wanted_data = list_info_data[col_list]
        wanted_records = list(wanted_data.values)
        wanted_list = list()
        for wanted_record in wanted_records:
            wanted_strs = [col_list[index] + ': <b>' + item + '</b>' for index, item in enumerate(wanted_record)]
            wanted_info = '\n'.join(wanted_strs)
            wanted_list.append(wanted_info)
        return '\n\n'.join(wanted_list)


async def clean(update, context):
    user_id = update.effective_chat.id
    if user_id in DELETE_MESSAGE_ID:
        for DELETE_ID in DELETE_MESSAGE_ID[user_id]:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=DELETE_ID)
        del DELETE_MESSAGE_ID[user_id]
    for opt_para in [UPDATE_OPT_ID, RETRIED, WANTED_DICT]:
        if user_id in opt_para:
            del opt_para[user_id]


def html_format(input_str):
    return input_str.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


async def timeout(update, context):
    user_id = update.effective_chat.id
    timeout_text = '<b>' + str(CHAT_TIMEOUT) + 's</b>内没有完成操作，<b>请重新开始操作</b>'
    await context.bot.send_message(chat_id=user_id, text=timeout_text, parse_mode='HTML',
                                   disable_web_page_preview=True)


def main() -> None:
    if initial:
        db_init()
    """Run the bot."""
    # Create the Application and pass it your bot's token.
    application = ApplicationBuilder().token("5880927415:AAGhkrqnA52erXm7d7LYVN-kzMg2hCgXqms").build()

    start_handler = CommandHandler('start', start)
    wanted_handler = ConversationHandler(
        entry_points=[CommandHandler('wanted', wanted)],
        states={
            'Start': [MessageHandler(filters.TEXT, start)],
            'REGION': [CallbackQueryHandler(region_select)],
            'TITLE': [CallbackQueryHandler(title_input)],
            'DATE': [MessageHandler(filters.TEXT, date_input)],
            'TMDB': [MessageHandler(filters.TEXT, tmdb_input)],
            'SUMMARY': [MessageHandler(filters.TEXT, finish_input)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.TEXT | filters.COMMAND, timeout)]
        },
        fallbacks=[CommandHandler('end', cov_end)],
        conversation_timeout=CHAT_TIMEOUT
    )

    seesee_handler = CommandHandler('seesee', seesee)

    update_handler = ConversationHandler(
        entry_points=[CommandHandler('update', update_list)],
        states={
            'UPDATE_OPT': [CallbackQueryHandler(update_opt)],
            'INPUT_ID': [MessageHandler(filters.TEXT, input_id)],
            'CHANGE': [CallbackQueryHandler(update_finish)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.TEXT | filters.COMMAND, timeout)]
        },
        fallbacks=[CommandHandler('end', cov_end)],
        conversation_timeout=CHAT_TIMEOUT
    )
    application.add_handler(start_handler)
    application.add_handler(wanted_handler)
    application.add_handler(seesee_handler)
    application.add_handler(update_handler)
    # Add ConversationHandler to application that will be used for handling updates
    # Run the bot until the user presses Ctrl-C
    # application.run_polling()
    application.run_webhook(
        listen='0.0.0.0',
        port=443,
        url_path='',
        key='',
        cert='',
        webhook_url=''
    )


if __name__ == '__main__':
    main()
