import streamlit as st
import db
import time
import hmac
import hashlib
import base64
import os

def login_form():
    """
    显示登录表单
    """
    st.subheader("登录")    
    with st.form("login_form"):
        email = st.text_input("邮箱", placeholder="请输入您的邮箱")
        password = st.text_input("密码", type="password")
        submit_button = st.form_submit_button("登录")
        
        if submit_button:
            if email.strip() == "" or password.strip() == "":
                st.error("邮箱和密码不能为空")
                return False
                
            # 验证邮箱格式
            import re
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.error("请输入有效的邮箱地址")
                return False
                
            success, message = db.login_user(email, password)
            if success:
                st.success(message)
                # 设置会话状态，记录用户已登录
                st.session_state.logged_in = True
                st.session_state.username = email
                # 创建并存储登录cookie
                cookie_value = create_login_cookie(email)
                st.session_state.auth_cookie = cookie_value
                # 设置cookie到浏览器
                st.query_params.update(auth_cookie=cookie_value)
                # 初始化sessions状态并加载聊天记录
                if 'sessions' not in st.session_state:
                    st.session_state.sessions = {}
                # 获取用户的所有会话
                user_sessions = db.get_user_sessions(email)
                # 初始化或重置会话状态
                st.session_state.sessions = {}
                if user_sessions:
                    # 将数据库中的会话加载到session_state中
                    for session in user_sessions:
                        session_id = session['session_id']
                        st.session_state.sessions[session_id] = session['messages']
                    # 设置当前会话ID为最新的会话
                    st.session_state.current_session_id = user_sessions[0]['session_id']
                # 刷新页面以显示登录后的内容
                st.rerun()
                return True
            else:
                st.error(message)
                return False
    return False

def register_form():
    """
    显示注册表单
    """
    import re
    import email_utils
    
    st.subheader("注册")
    
    # 在会话状态中存储验证码状态
    if "verification_sent" not in st.session_state:
        st.session_state.verification_sent = False
    if "verification_code" not in st.session_state:
        st.session_state.verification_code = ""
    if "email_verified" not in st.session_state:
        st.session_state.email_verified = False
    
    with st.form("register_form"):
        email = st.text_input("邮箱", placeholder="请输入您的邮箱")
        
        # 邮箱验证码表单
        col1, col2 = st.columns([3, 1])
        with col1:
            verification_code = st.text_input("邮箱验证码", placeholder="请输入验证码")
        with col2:
            send_code_button = st.form_submit_button("发送验证码")
        
        # 手机号表单
        phone = st.text_input("手机号", placeholder="请输入您的手机号")
        
        # 密码表单
        password = st.text_input("密码", type="password", placeholder="请输入至少8位字符的密码")
        password_confirm = st.text_input("确认密码", type="password", placeholder="请再次输入密码")
        
        submit_button = st.form_submit_button("注册")
        
        # 处理发送验证码按钮
        if send_code_button:
            if email.strip() == "":
                st.error("请输入邮箱地址")
                return False
            
            # 验证邮箱格式
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.error("请输入有效的邮箱地址")
                return False
            
            # 生成验证码
            code = email_utils.generate_verification_code()
            # 发送验证码
            success, message = email_utils.send_verification_email(email)
            
            if success:
                st.session_state.verification_sent = True
                st.success(message)
            else:
                # 即使发送失败，也设置验证码已发送状态，允许用户继续注册流程
                st.session_state.verification_sent = True
                # 显示错误信息，但提供继续的选项
                st.warning(f"{message}。如果您在测试环境中，可以使用验证码：{code}")
                # 在开发/测试环境中显示验证码
                if os.getenv("ENVIRONMENT", "development") != "production":
                    st.info(f"测试环境验证码: {code}")
            return False
        
        # 处理注册按钮
        if submit_button:
            # 验证表单字段
            if email.strip() == "" or password.strip() == "" or phone.strip() == "":
                st.error("邮箱、密码和手机号不能为空")
                return False
            
            # 验证邮箱格式
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.error("请输入有效的邮箱地址")
                return False
            
            # 验证手机号格式
            if not re.match(r"^1[3-9]\d{9}$", phone):
                st.error("请输入有效的手机号")
                return False
            
            # 验证密码长度
            if len(password) < 8:
                st.error("密码长度不能少于8位字符")
                return False
                
            if password != password_confirm:
                st.error("两次输入的密码不一致")
                return False
            
            # 验证邮箱验证码
            if verification_code.strip() == "":
                st.error("请输入邮箱验证码")
                return False
            
            # 验证验证码是否正确
            success, message = email_utils.verify_code(email, verification_code)
            if not success:
                st.error(message)
                return False
                
            # 注册用户
            success, message = db.register_user(email, password, phone)
            if success:
                st.success(message)
                # 清除验证状态
                st.session_state.verification_sent = False
                st.session_state.verification_code = ""
                st.session_state.email_verified = False
                return True
            else:
                st.error(message)
                return False
    return False

# 密钥用于签名cookie，实际应用中应该使用环境变量存储
SECRET_KEY = "your_secret_key_here"

def create_login_cookie(username):
    """
    创建登录cookie
    """
    # 创建一个包含用户名和过期时间的字典
    expires = int(time.time()) + 7 * 24 * 60 * 60  # 7天过期
    payload = f"{username}|{expires}"
    
    # 使用HMAC-SHA256签名payload
    signature = hmac.new(
        SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # 返回签名后的cookie值
    cookie_value = f"{payload}|{signature}"
    return base64.b64encode(cookie_value.encode()).decode()

def verify_login_cookie():
    """
    验证登录cookie
    """
    # 检查cookie是否存在
    if "auth_cookie" not in st.session_state:
        # 尝试从st.query_params获取cookie
        try:
            query_params = st.query_params
            if "auth_cookie" in query_params and query_params["auth_cookie"]:
                # 确保我们获取到的是字符串而不是列表
                cookie_value = query_params["auth_cookie"]
                if isinstance(cookie_value, list) and len(cookie_value) > 0:
                    st.session_state.auth_cookie = cookie_value[0]
                else:
                    st.session_state.auth_cookie = cookie_value
            else:
                return None
        except Exception as e:
            print(f"获取查询参数错误: {e}")
            return None
    
    try:
        # 解码cookie
        cookie_value = base64.b64decode(st.session_state.auth_cookie).decode()
        payload, signature = cookie_value.rsplit("|", 1)
        username, expires = payload.split("|", 1)
        expires = int(expires)
        
        # 验证签名
        expected_signature = hmac.new(
            SECRET_KEY.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # 检查签名是否匹配且未过期
        if hmac.compare_digest(signature, expected_signature) and time.time() < expires:
            # 确保cookie保留在URL参数中，以便页面刷新后仍能保持登录状态
            if "auth_cookie" not in st.query_params:
                st.query_params.update(auth_cookie=st.session_state.auth_cookie)
            return username
    except Exception as e:
        print(f"Cookie验证错误: {e}")
    
    # 验证失败，清除cookie
    if "auth_cookie" in st.session_state:
        del st.session_state.auth_cookie
    # 清除URL中的cookie参数
    if "auth_cookie" in st.query_params:
        st.query_params.clear()
    return None

def auth_page():
    """
    认证页面，包含登录和注册选项
    """
    # 首先检查cookie是否有效
    username = verify_login_cookie()
    if username:
        # 如果cookie有效，设置会话状态
        st.session_state.logged_in = True
        st.session_state.username = username
        # 确保cookie在session_state中存在
        if "auth_cookie" not in st.session_state and "auth_cookie" in st.query_params:
            cookie_value = st.query_params["auth_cookie"]
            if isinstance(cookie_value, list) and len(cookie_value) > 0:
                st.session_state.auth_cookie = cookie_value[0]
            else:
                st.session_state.auth_cookie = cookie_value
    
    # 检查用户是否已登录
    if "logged_in" in st.session_state and st.session_state.logged_in:
        st.success(f"已登录为: {st.session_state.username}")
        if st.button("退出登录"):
            # 清除会话状态和cookie
            st.session_state.logged_in = False
            if "username" in st.session_state:
                del st.session_state.username
            if "auth_cookie" in st.session_state:
                del st.session_state.auth_cookie
            # 清除URL中的cookie参数
            st.query_params.clear()
            st.rerun()
        return True
    
    # 显示登录/注册选项卡
    tab1, tab2 = st.tabs(["登录", "注册"])
    
    with tab1:
        if login_form():
            return True
    
    with tab2:
        if register_form():
            # 注册成功后切换到登录选项卡
            st.info("注册成功，请登录")
    
    return False

def is_authenticated():
    """
    检查用户是否已认证
    """
    return "logged_in" in st.session_state and st.session_state.logged_in

def get_current_username():
    """
    获取当前登录的用户名
    """
    if is_authenticated():
        return st.session_state.username
    return None