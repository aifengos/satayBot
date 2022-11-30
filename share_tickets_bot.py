import re
import psycopg2
import random
import time
import logging
import pandas as pd
from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, CallbackContext, ConversationHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply

# your bot token
BOT_TOKEN = ""

# your channel ids
channel_ids = ['']

# your group ids dict
group_ids = {}

# User ids of Admin
ADMIN_USERS = []

# if initial the Database
initial = False

# PostgreSQL Connection information
db_host = ''
db_user = ''
db_pw = ''
db_name = ''

exclude_chat_type = ['group', 'supergroup', 'channel']

user_pattern = re.compile(r"@([a-zA-Z0-9_]+)")
car_pattern = re.compile(r"\b[0-9A-Z京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽赣粤青藏川宁琼]{7}\b")

pass_members = ['ChatMemberStatus.OWNER', 'ChatMemberStatus.ADMINISTRATOR', 'ChatMemberStatus.MEMBER']

def db_init():
    conn = psycopg2.connect(dbname=db_name, host=db_host,
                            user=db_user, password=db_pw)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS query_time; CREATE TABLE IF NOT EXISTS" +
                " query_time (query_uid text, last_query_time numeric, id_State boolean);")
    conn.commit()  # <- We MUST commit to reflect the inserted data
    cur.execute(
        "DROP TABLE IF EXISTS car_info; CREATE TABLE IF NOT EXISTS car_info (car_num text, car_host text, " +
        "host_uid text, create_time numeric, query_time numeric, car_State boolean);")
    conn.commit()  # <- We MUST commit to reflect the inserted data
    cur.execute("DROP TABLE IF EXISTS sub_keys; CREATE TABLE IF NOT EXISTS" +
                " sub_keys (sub_uid integer, keys text);")
    conn.commit()  # <- We MUST commit to reflect the inserted data
    cur.close()
    conn.close()


def car_num_gen():
    char0 = '京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽赣粤青藏川宁琼'
    char1 = 'ABCDEFGHJKLMNPQRSTUVWXYZ'  # 车牌号中没有I和O，可自行百度
    char2 = '0123456789ABCDEFGHJKLMNPQRSTUVWXYZ'

    id_1 = random.choice(char0)  # 车牌号第一位     省份简称
    id_2 = ''.join(random.sample(char1, 1))  # 车牌号第二位
    car_id = ''

    while True:
        id_3 = ''.join(random.sample(char2, 5))
        v = id_3.isalpha()  # 所有字符都是字母时返回 true
        if v == True:
            continue
        else:
            car_id = id_1 + id_2 + id_3
            # print car_id
            break

    return car_id


# EXPECT_NAME, EXPECT_BUTTON_CLICK = range(2)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


def check_query_time_int(uid, timeout=60, up_time=True):
    conn = psycopg2.connect(dbname=db_name, host=db_host,
                            user=db_user, password=db_pw)
    cur = conn.cursor()
    query_cmd = ("SELECT * FROM query_time WHERE query_uid='" + str(uid) + "'")
    cur.execute(query_cmd)
    query_result = cur.fetchall()
    time_stamp = float(time.time())
    if query_result:
        query_data = pd.DataFrame(query_result, columns=['query_uid', 'last_query_time', 'id_State'])
        if not query_data['id_State'].values[-1]:
            cur.close()
            conn.close()
            return False, '该用户已被封禁'
        else:
            last_query_time = query_data['last_query_time'].values[-1]

            time_int = time_stamp - float(last_query_time)
            if time_int >= timeout:
                if up_time:
                    update_cmd = ("UPDATE query_time SET last_query_time = " + str(time_stamp) +
                                  "  WHERE query_uid='" + str(uid) + "'")
                    cur.execute(update_cmd)
                    conn.commit()  # <- We MUST commit to reflect the inserted data
                cur.close()
                conn.close()
                return True, '正常访问'
            else:
                cur.close()
                conn.close()
                return False, '请求太频繁，请间隔' + str(timeout) + '秒再试'
    else:
        postgres_insert_query = 'INSERT INTO query_time (query_uid, last_query_time, id_State) VALUES (%s,%s,%s)'
        record_to_insert = (uid, time_stamp, True)
        # print(record_to_insert)
        cur.execute(postgres_insert_query, record_to_insert)
        conn.commit()  # <- We MUST commit to reflect the inserted data
        cur.close()
        conn.close()
        return True, '正常访问'


def check_sub_keys():
    conn = psycopg2.connect(dbname=db_name, host=db_host,
                            user=db_user, password=db_pw)
    cur = conn.cursor()
    query_cmd = "SELECT * FROM sub_keys"
    cur.execute(query_cmd)
    query_result = cur.fetchall()
    if query_result:
        keys_data = pd.DataFrame(query_result, columns=['sub_uid', 'keys'])
    else:
        keys_data = pd.DataFrame()
    cur.close()
    conn.close()
    return keys_data


async def check_user_member(update: Update, context: CallbackContext):
    if update.message.chat.type in exclude_chat_type:
        member_str = 'GroupMessage'
    else:
        member_str = 'MemberUser'
        chat_id = update.effective_chat.id
        for group_name in group_ids:
            check = await context.bot.getChatMember(group_ids[group_name], chat_id)
            if not check:
                member_str = 'NotMember'
            else:
                if str(check['status']) not in pass_members:
                    member_str = 'NotMember'
    print(member_str)
    return member_str


async def start(update: Update, context: CallbackContext.DEFAULT_TYPE):
    check_member = await check_user_member(update, context)
    if check_member == 'GroupMessage':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="要使用SweetShare乘车系统请私聊本机器人")
    elif check_member == 'NotMember':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="请先加入SweetShare群组和关注SweetShare频道")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="欢迎使用SweetShare乘车系统")


async def create(update: Update, context: CallbackContext.DEFAULT_TYPE):
    check_member = await check_user_member(update, context)
    if check_member == 'GroupMessage':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="要使用SweetShare乘车系统请私聊本机器人")
    elif check_member == 'NotMember':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="请先加入SweetShare群组和关注SweetShare频道")
    else:
        # print(update.effective_user.id)
        if ADMIN_USERS and (update.effective_user.id not in ADMIN_USERS):
            await context.bot.send_message(chat_id=update.effective_chat.id, text="发车请联系群主：@SweetShare_ss")
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="发车，请输入车辆信息")
            return 'Create_Input'
        # input_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), create_car_info)
        # application.add_handler(input_handler)


def cov_end(update: Update, context: CallbackContext):
    update.message.reply_text('Input End')
    return ConversationHandler.END


async def create_car_info(update: Update, context: CallbackContext):
    text = update.message.text
    text_items = text.split('\n')
    # print(text_items)
    car_info = list()
    car_host = ''
    for text_item in text_items:
        if not text_item.startswith('车牌：'):
            id_match = re.search(user_pattern, text_item)
            if id_match:
                car_host = id_match[1]
            else:
                car_info.append(text_item.strip())
    if car_host:
        if update.message.forward_from:
            host_uid = update.message.forward_from.id
        else:
            host_uid = update.effective_chat.id
        car_num = car_num_gen()
        # print(car_num)
        car_info.append('')
        # car_info.append('*车牌：*`' + str(car_num) + '`')
        car_info.append('<b>车牌：</b><code>' + str(car_num) +
                        '</code>\n上车请联系：@SweetTicketsBot')
        car_info_str = '\n'.join(car_info)
        conn = psycopg2.connect(dbname=db_name, host=db_host,
                                user=db_user, password=db_pw)
        cur = conn.cursor()
        # cur.execute('DROP TABLE car_info;')
        # conn.commit()  # <- We MUST commit to reflect the inserted data
        time_stamp = str(float(time.time()))

        exit_num = True
        while exit_num:
            query_cmd = "SELECT * FROM car_info WHERE car_num='" + car_num + "'"
            cur.execute(query_cmd)
            car_result = cur.fetchall()
            if not car_result:
                exit_num = False
        postgres_insert_query = ('INSERT INTO car_info (car_num, car_host, host_uid, create_time, ' +
                                 'query_time, car_state) VALUES (%s,%s,%s,%s,%s,%s)')
        record_to_insert = (car_num, car_host, host_uid, time_stamp, time_stamp, True)
        # print(record_to_insert)
        cur.execute(postgres_insert_query, record_to_insert)
        conn.commit()  # <- We MUST commit to reflect the inserted data
        cur.close()
        conn.close()
        if channel_ids:
            for channel_id in channel_ids:
                try:
                # check = context.bot.getChatMember(channel_id, '@SweetTicketsBot')
                # print(channel_id, '@SweetTicketsBot', check)
                    await context.bot.send_message(chat_id=channel_id, text=car_info_str, parse_mode= 'HTML')
                except:
                    print('Not Member of Channel ' + channel_id)
            await context.bot.send_message(chat_id=update.effective_chat.id, text='<b>发车成功：</b>',
                                           parse_mode='HTML')
            await context.bot.send_message(chat_id=update.effective_chat.id, text=car_info_str,
                                           parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='请设置频道来公开信息：\n' + car_info_str)
        sub_data = check_sub_keys()
        if not sub_data.empty:
            sub_keys = set(sub_data['keys'].values)
            sub_keys_reg = re.compile('|'.join(sub_keys), flags=re.IGNORECASE)
            match_keys = re.findall(sub_keys_reg, car_info_str)
            match_keys = [item.upper() for item in match_keys]
            if match_keys:
                sub_ids = list(set(sub_data[sub_data['keys'].isin(match_keys)]['sub_uid'].values))
                for sub_id in sub_ids:
                    sub_id = int(sub_id)
                    if sub_id != update.effective_chat.id:
                        await context.bot.send_message(chat_id=sub_id, text='车来了：\n' + car_info_str,
                                                       parse_mode='HTML')
    else:
        car_info_str = '发车格式不对, 请重新输入'
        await context.bot.send_message(chat_id=update.effective_chat.id, text=car_info_str)
    return ConversationHandler.END


async def ticket(update: Update, context: CallbackContext):
    check_member = await check_user_member(update, context)
    if check_member == 'GroupMessage':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="要使用SweetShare乘车系统请私聊本机器人")
    elif check_member == 'NotMember':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="请先加入SweetShare群组和关注SweetShare频道")
    else:
        if update.effective_chat.id not in ADMIN_USERS:
            pass_bool, pass_str = check_query_time_int(update.effective_chat.id, 5, False)
            if pass_bool:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="请输入或者粘贴车牌号，获取车主信息")
                return 'Ticket_Input'
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=pass_str)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="请输入或者粘贴车牌号，获取车主信息")
            return 'Ticket_Input'


async def get_ticket(update: Update, context: CallbackContext):
    text = update.message.text
    # print(len(text), text)
    match_car_num = re.search(car_pattern, text)
    if match_car_num:
        car_num = match_car_num[0]
        # print(car_num)
        conn = psycopg2.connect(dbname=db_name, host=db_host,
                                user=db_user, password=db_pw)
        cur = conn.cursor()
        query_cmd = ("SELECT * FROM car_info WHERE car_num='" + car_num + "'")
        cur.execute(query_cmd)
        car_result = cur.fetchall()
        time_stamp = str(float(time.time()))
        if car_result:
            car_data = pd.DataFrame(car_result,
                                    columns=['car_num', 'car_host', 'host_uid', 'create_time',
                                             'query_time', 'car_state'])
            opened_car_data = car_data[car_data['car_state']]
            if opened_car_data.empty:
                await context.bot.send_message(chat_id=update.effective_chat.id, text='<b>很抱歉，车已经开走了</b>',
                                               parse_mode= 'HTML')
            else:
                pass_bool, pass_str = check_query_time_int(update.effective_chat.id, 60, True)
                if pass_bool:
                    car_host = opened_car_data['car_host'].values[-1]
                    # print(car_host)
                    # print('请联系： @' + car_host)
                    update_cmd = "UPDATE Car_Info SET query_time = " + time_stamp + "  WHERE car_num='" + car_num + "'"
                    cur.execute(update_cmd)
                    conn.commit()  # <- We MUST commit to reflect the inserted data
                    await context.bot.send_message(chat_id=update.effective_chat.id,
                                                   text='<b>上车请联系： @' + car_host + '</b>', parse_mode= 'HTML')
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=pass_str)
        else:
            pass_bool, pass_str = check_query_time_int(update.effective_chat.id, 5, False)
            if pass_bool:
                await context.bot.send_message(chat_id=update.effective_chat.id, text='<b>车牌错误，请确认再发' + '</b>',
                                               parse_mode= 'HTML')
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=pass_str)
        cur.close()
        conn.close()
    else:
        pass_bool, pass_str = check_query_time_int(update.effective_chat.id, 5, False)
        if pass_bool:
            await context.bot.send_message(chat_id=update.effective_chat.id, text='<b>车牌错误，请确认再发' + '</b>',
                                           parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=pass_str)
    # return 'Finish_Input'
    return ConversationHandler.END
    # await context.bot.send_message(chat_id=update.effective_chat.id, text="上车")


async def close(update: Update, context: CallbackContext):
    check_member = await check_user_member(update, context)
    if check_member == 'GroupMessage':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="要使用SweetShare乘车系统请私聊本机器人")
    elif check_member == 'NotMember':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="请先加入SweetShare群组和关注SweetShare频道")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="车主如需关闭车门，请输入车牌")
        # get_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), get_ticket)
        # application.add_handler(get_handler)
        return 'Close_Input'
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="上车")


async def close_car(update: Update, context: CallbackContext):
    text = update.message.text
    # print(len(text), text)
    match_car_num = re.search(car_pattern, text.strip())
    if match_car_num:
        car_num = match_car_num[0]
        # print(car_num)
        conn = psycopg2.connect(dbname=db_name, host=db_host,
                                user=db_user, password=db_pw)
        cur = conn.cursor()
        query_cmd = ("SELECT * FROM car_info WHERE (car_num='" + car_num + "') AND (car_state=true)")
        cur.execute(query_cmd)
        car_result = cur.fetchall()
        if car_result:
            car_data = pd.DataFrame(car_result,
                                    columns=['car_num', 'car_host', 'host_uid', 'create_time',
                                             'query_time', 'car_state'])
            car_host = car_data['car_host'].values[-1].strip()
            host_uid = int(car_data['host_uid'].values[-1])
            user_id = int(update.effective_chat.id)
            user_name = update.effective_chat.username
            # print(user_id, host_uid, user_name, car_host)
            car_admin = [host_uid]
            car_admin.extend(ADMIN_USERS)
            # print(user_name, car_host, host_uid)
            if (user_id in car_admin) or ((user_name is not None) and (user_name == car_host)):
                # print(car_host)
                # print('请联系： @' + car_host)
                update_cmd = "UPDATE Car_Info SET car_state = " + str(False) + "  WHERE car_num='" + car_num + "'"
                cur.execute(update_cmd)
                conn.commit()  # <- We MUST commit to reflect the inserted data
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text='车门已关闭，车友已无法获取您的username')
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text='您不是该车车主，无法关闭该车车门')
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text='车牌错误，请核对再发')
        cur.close()
        conn.close()
    # return 'Finish_Input'
    return ConversationHandler.END


async def reopen(update: Update, context: CallbackContext):
    check_member = await check_user_member(update, context)
    if check_member == 'GroupMessage':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="要使用SweetShare乘车系统请私聊本机器人")
    elif check_member == 'NotMember':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="请先加入SweetShare群组和关注SweetShare频道")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="车主如需重新车门，请输入车牌")
        # get_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), get_ticket)
        # application.add_handler(get_handler)
        return 'Reopen_Input'
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="上车")


async def reopen_car(update: Update, context: CallbackContext):
    text = update.message.text
    # print(len(text), text)
    match_car_num = re.search(car_pattern, text.strip())
    if match_car_num:
        car_num = match_car_num[0]
        # print(car_num)
        conn = psycopg2.connect(dbname=db_name, host=db_host,
                                user=db_user, password=db_pw)
        cur = conn.cursor()
        query_cmd = ("SELECT * FROM car_info WHERE (car_num='" + car_num + "') AND (car_state=false)")
        cur.execute(query_cmd)
        car_result = cur.fetchall()
        if car_result:
            car_data = pd.DataFrame(car_result,
                                    columns=['car_num', 'car_host', 'host_uid', 'create_time',
                                             'query_time', 'car_state'])
            car_host = car_data['car_host'].values[-1].strip()
            host_uid = int(car_data['host_uid'].values[-1])
            user_id = int(update.effective_chat.id)
            user_name = update.effective_chat.username
            # print(user_id, host_uid, user_name, car_host)
            car_admin = [host_uid]
            car_admin.extend(ADMIN_USERS)
            # print(user_name, car_host, host_uid)
            if (user_id in car_admin) or ((user_name is not None) and (user_name == car_host)):
                # print(car_host)
                # print('请联系： @' + car_host)
                update_cmd = "UPDATE Car_Info SET car_state = " + str(True) + "  WHERE car_num='" + car_num + "'"
                cur.execute(update_cmd)
                conn.commit()  # <- We MUST commit to reflect the inserted data
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text='车门已重新打开，车友可以正常获取您的username')
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text='您不是该车车主，无法关闭该车车门')
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text='车牌错误，请核对再发')
        cur.close()
        conn.close()
    # return 'Finish_Input'
    return ConversationHandler.END


async def echo(update: Update, context: CallbackContext.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)


async def unknown(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if update.message is not None:
        print(update.message.text)
        if update.message.chat.type not in exclude_chat_type:
            check_member = await check_user_member(update, context)
            if check_member == 'NotMember':
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text="请先加入SweetShare群组和关注SweetShare频道")
            elif check_member == 'MemberUser':
                # print(update.effective_chat.id)
                # print(update.message.forward_from, update.effective_chat.id)
                if update.message.text.startswith(r'//SweetShare共享请求'):
                    if update.effective_chat.id in ADMIN_USERS:
                        match_car_num = re.search(car_pattern, update.message.text)
                        if match_car_num:
                            await context.bot.send_message(chat_id=update.effective_chat.id,
                                                           text='如格式正确，可以获取上车方式')
                            await get_ticket(update, context)
                        else:
                            await context.bot.send_message(chat_id=update.effective_chat.id,
                                                           text='如格式正确，群主可以直接发车')
                            await create_car_info(update, context)
                    else:
                        match_car_num = re.search(car_pattern, update.message.text)
                        if match_car_num:
                            await context.bot.send_message(chat_id=update.effective_chat.id,
                                                           text='如格式正确，可以直接获取上车方式')
                            await get_ticket(update, context)
                        else:
                            await context.bot.send_message(chat_id=update.effective_chat.id,
                                                           text="发车请联系群主：@SweetShare_ss")
                else:
                    match_car_num = re.search(car_pattern, update.message.text)
                    if match_car_num:
                        await context.bot.send_message(chat_id=update.effective_chat.id,
                                                       text='识别到车牌，车牌正确可以直接获取上车方式')
                        await get_ticket(update, context)
                    else:
                        await context.bot.send_message(chat_id=update.effective_chat.id, text="靓仔，你讲乜嘢?")

    # else:
    #     await context.bot.send_message(chat_id=update.effective_chat.id, text="不能在群组内使用本机器人")


async def subscribe(update: Update, context: CallbackContext):
    check_member = await check_user_member(update, context)
    if check_member == 'GroupMessage':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="要使用SweetShare乘车系统请私聊本机器人")
    elif check_member == 'NotMember':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="请先加入SweetShare群组和关注SweetShare频道")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text='请输入要订阅的关键词，以"，"或者"；"分隔')
        return 'Sub_Input'


async def subscribe_input(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    # check_chat_id = 5175617058
    text = update.message.text
    # print(len(text), text)
    if text:
        sub_keys = re.split('[，,;；]', text)
        sub_keys = list(set([item.strip().upper() for item in sub_keys]))
        conn = psycopg2.connect(dbname=db_name, host=db_host,
                                user=db_user, password=db_pw)
        cur = conn.cursor()
        delete_cmd = ("DELETE FROM sub_keys WHERE sub_uid='" + str(chat_id) + "'")
        cur.execute(delete_cmd)
        conn.commit()  # <- We MUST commit to reflect the inserted data
        if len(sub_keys) == 1:
            insert_values = "('" + str(chat_id) + "', '" + sub_keys[0] + "')"
        else:
            insert_values = "('" + str(chat_id) + "', '" + ("'), ('" + str(chat_id) + "', '").join(sub_keys) + "')"
        sub_keys_insert = 'INSERT INTO sub_keys (sub_uid, keys) VALUES ' + insert_values
        # print(sub_keys_insert)
        cur.execute(sub_keys_insert)
        conn.commit()  # <- We MUST commit to reflect the inserted data
        cur.close()
        conn.close()
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text='已订阅关键词：<b>' + '，'.join(sub_keys) + '</b>', parse_mode='HTML')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text='请输入关键词再试')
    return ConversationHandler.END


async def unsubscribe(update: Update, context: CallbackContext):
    check_member = await check_user_member(update, context)
    if check_member == 'GroupMessage':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="要使用SweetShare乘车系统请私聊本机器人")
    elif check_member == 'NotMember':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="请先加入SweetShare群组和关注SweetShare频道")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text='请输入要取消订阅的关键词，以"，"或者"；"\n如要取消所有订阅请输入All')
        return 'Unsub_Input'


async def unsubscribe_input(update: Update, context: CallbackContext):
    text = update.message.text
    # print(len(text), text)
    if text:
        sub_keys = re.split('[，,;；]', text)
        sub_keys = list(set([item.strip().upper() for item in sub_keys]))
        conn = psycopg2.connect(dbname=db_name, host=db_host,
                                user=db_user, password=db_pw)
        cur = conn.cursor()
        chat_id = update.effective_chat.id
        if len(sub_keys) == 1:
            if sub_keys[0].lower() == 'all':
                keys_values = "sub_uid='" + str(chat_id) + "'"
            else:
                keys_values = "sub_uid='" + str(chat_id) + "' AND keys='" + sub_keys[0] + "'"
        else:
            keys_values = "sub_uid='" + str(chat_id) + "' AND keys IN ('" + ("', '").join(sub_keys) + "')"
        # print(keys_values)
        sub_keys_delete = 'DELETE FROM sub_keys WHERE ' + keys_values
        # print(sub_keys_insert)
        cur.execute(sub_keys_delete)
        conn.commit()  # <- We MUST commit to reflect the inserted data

        query_cmd = ("SELECT * FROM sub_keys WHERE sub_uid='" + str(chat_id) + "'")
        cur.execute(query_cmd)
        query_result = cur.fetchall()
        cur.close()
        conn.close()
        if query_result:
            keys_data = pd.DataFrame(query_result, columns=['sub_uid', 'keys'])
            keys_values = list(keys_data['keys'].values)
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='已更新订阅，关键词：<b>' + '，'.join(keys_values) + '</b>',
                                           parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='<b>所有订阅关键词已取消</b>', parse_mode='HTML')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text='请输入关键词再试')
    return ConversationHandler.END


async def sub_list(update: Update, context: CallbackContext):
    check_member = await check_user_member(update, context)
    if check_member == 'GroupMessage':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="要使用SweetShare乘车系统请私聊本机器人")
    elif check_member == 'NotMember':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="请先加入SweetShare群组和关注SweetShare频道")
    else:
        conn = psycopg2.connect(dbname=db_name, host=db_host,
                                user=db_user, password=db_pw)
        cur = conn.cursor()
        chat_id = update.effective_chat.id
        query_cmd = ("SELECT * FROM sub_keys WHERE sub_uid='" + str(chat_id) + "'")
        cur.execute(query_cmd)
        query_result = cur.fetchall()
        if query_result:
            keys_data = pd.DataFrame(query_result, columns=['sub_uid', 'keys'])
            keys_values = list(keys_data['keys'].values)
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='已订阅关键词：<b>' + '，'.join(keys_values) + '</b>', parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text='没有订阅关键词，请使用\subscribe添加')


if __name__ == '__main__':
    if initial:
        db_init()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    start_handler = CommandHandler('start', start)
    sublist_handler = CommandHandler('sublist', sub_list)
    # create_handler = CommandHandler('create', create)
    create_handler = ConversationHandler(
        entry_points=[CommandHandler('create', create)],
        states={
            'Create_Input': [MessageHandler(filters.TEXT, create_car_info)],
            'Finish_Input': [CommandHandler('Input_Finish', cov_end)]
        },
        fallbacks=[CommandHandler('Finish_Input', cov_end)],
    )
    ticket_handler = ConversationHandler(
        entry_points=[CommandHandler('ticket', ticket)],
        states={
            'Ticket_Input': [MessageHandler(filters.TEXT, get_ticket)]
        },
        fallbacks=[CommandHandler('Finish_Input', cov_end)],
    )
    close_handler = ConversationHandler(
        entry_points=[CommandHandler('close', close)],
        states={
            'Close_Input': [MessageHandler(filters.TEXT, close_car)]
        },
        fallbacks=[CommandHandler('Finish_Input', cov_end)],
    )
    reopen_handler = ConversationHandler(
        entry_points=[CommandHandler('reopen', reopen)],
        states={
            'Reopen_Input': [MessageHandler(filters.TEXT, reopen_car)]
        },
        fallbacks=[CommandHandler('Finish_Input', cov_end)],
    )
    sub_handler = ConversationHandler(
        entry_points=[CommandHandler('setsub', subscribe)],
        states={
            'Sub_Input': [MessageHandler(filters.TEXT, subscribe_input)]
        },
        fallbacks=[CommandHandler('Finish_Input', cov_end)],
    )
    unsub_handler = ConversationHandler(
        entry_points=[CommandHandler('setunsub', unsubscribe)],
        states={
            'Unsub_Input': [MessageHandler(filters.TEXT, unsubscribe_input)]
        },
        fallbacks=[CommandHandler('Finish_Input', cov_end)],
    )
    # ticket_handler = CommandHandler('ticket', ticket)
    # close_handler = CommandHandler('close', close)
    # unknown_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    # application.add_handler(echo_handler)
    # unknown_handler = MessageHandler(filters.COMMAND, unknown)
    unknown_handler = MessageHandler(filters.TEXT, unknown)
    application.add_handler(start_handler)
    application.add_handler(create_handler)
    application.add_handler(ticket_handler)
    application.add_handler(close_handler)
    application.add_handler(reopen_handler)
    application.add_handler(sub_handler)
    application.add_handler(sublist_handler)
    application.add_handler(unsub_handler)
    application.add_handler(unknown_handler)
    # application.run_polling()
    application.run_webhook(
        listen='0.0.0.0',
        port=8443,
        # your boot url
        url_path='',
        # your Cert info
        key='',
        cert='',
        # your boot webhook_url
        webhook_url=''
    )
