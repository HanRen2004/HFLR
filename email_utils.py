import smtplib
import random
import string
import socket
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
import os
import re
import email

# SMTP 服务器配置
smtp_server = "smtp.qq.com"
smtp_port = 465
sender_email = "3375403643@qq.com"
sender_password = "dzudazlhxfezdcaj"

specialsre = re.compile(r'[][\\()<>@,:;".]')
escapesre = re.compile(r'[\\"]')

# 验证码存储结构
verification_codes = {}

# 配置
CODE_LENGTH = 6
CODE_EXPIRY_MINUTES = 5
MAX_ATTEMPTS = 5

def formataddr(pair, charset='utf-8'):
    name, address = pair
    address.encode('ascii')
    if name:
        try:
            name.encode('ascii')
        except UnicodeEncodeError:
            from email.charset import Charset
            charset = Charset(charset)
            encoded_name = charset.header_encode(name)
            return "%s <%s>" % (encoded_name, address)
        else:
            quotes = ''
            if specialsre.search(name):
                quotes = '"'
            name = escapesre.sub(r'\\\g<0>', name)
            return '%s%s%s <%s>' % (quotes, name, quotes, address)
    return address


def generate_verification_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

def send_verification_email(user_email):
    """
    为用户生成验证码、存储验证信息，并通过邮箱发送
    """
    code = generate_verification_code()
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=CODE_EXPIRY_MINUTES)

    # 存储验证码和状态信息
    verification_codes[user_email] = {
        "code": code,
        "expires_at": expires_at,
        "created_at": now,
        "attempts": 0
    }

    # 构造邮件内容
    msg = MIMEText(f"您的验证码是：{code}，有效期 5 分钟。", "plain", "utf-8")
    msg["From"] = formataddr(("注册系统", sender_email))
    msg["To"] = formataddr((user_email, user_email))
    msg["Subject"] = "您的注册验证码"

    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, [user_email], msg.as_string())
        server.quit()
        return True, "验证码已发送"
    except Exception as e:
        return False, f"验证码发送失败：{e}"



def verify_code(user_email, provided_code):
    """
    验证用户提供的验证码是否正确、在有效期内，且未超出最大尝试次数
    """
    record = verification_codes.get(user_email)
    if not record:
        return False, "验证码不存在或已过期"

    now = datetime.utcnow()

    if now > record["expires_at"]:
        del verification_codes[user_email]
        return False, "验证码已过期"

    if record["attempts"] >= MAX_ATTEMPTS:
        del verification_codes[user_email]
        return False, "尝试次数过多，请重新获取验证码"

    if record["code"] == provided_code:
        del verification_codes[user_email]
        return True, "验证码正确"

    # 输入错误，增加尝试次数
    record["attempts"] += 1
    remaining = MAX_ATTEMPTS - record["attempts"]
    return False, f"验证码错误，剩余尝试次数：{remaining}"
