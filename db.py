import pymongo
from pymongo import MongoClient
import os
import hashlib
import uuid
from datetime import datetime

# MongoDB连接配置
MONGO_URI = "mongodb+srv://3375403643:xjy1232004@heartflowcluster.xmkes.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "HeartFlowApp"

# 创建MongoDB客户端连接
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # 测试连接
    client.server_info()
    db = client[DB_NAME]
    # 用户集合
    users_collection = db["users"]
    # 聊天记录集合
    chat_history_collection = db["chat_history"]
    # 确保用户名索引是唯一的
    users_collection.create_index("username", unique=True)
    # 为聊天记录创建索引
    chat_history_collection.create_index("username")
    chat_history_collection.create_index("session_id")
except Exception as e:
    print(f"MongoDB连接错误: {e}")
    raise Exception(f"无法连接到MongoDB: {e}")
    # 不再使用内存存储


def save_verification_code(email: str, code: str):
    """存储验证码"""
    expiration = datetime.utcnow() + timedelta(minutes=5)  # 5 分钟有效期
    db.email_verifications.update_one(
        {"email": email},
        {"$set": {"code": code, "expiration": expiration}},
        upsert=True
    )


def hash_password(password):
    """
    对密码进行哈希处理
    """
    salt = uuid.uuid4().hex
    hashed_password = hashlib.sha256(salt.encode() + password.encode()).hexdigest()
    return f"{salt}${hashed_password}"

def verify_password(stored_password, provided_password):
    """
    验证密码是否匹配
    """
    salt, hashed_password = stored_password.split('$')
    calculated_hash = hashlib.sha256(salt.encode() + provided_password.encode()).hexdigest()
    return calculated_hash == hashed_password

def register_user(email, password, phone=None):
    """
    注册新用户
    """
    # 检查邮箱是否已存在
    if users_collection.find_one({"username": email}):
        return False, "该邮箱已被注册"
    
    # 创建新用户
    user = {
        "username": email,  # 保持字段名不变，但存储邮箱
        "password": hash_password(password),
        "phone": phone,     # 新增手机号字段
        "created_at": datetime.now()
    }
    
    try:
        users_collection.insert_one(user)
        return True, "注册成功"
    except Exception as e:
        return False, f"注册失败: {str(e)}"

def login_user(email, password):
    """
    用户登录验证
    """
    user = users_collection.find_one({"username": email})
    if not user:
        return False, "该邮箱未注册"
    
    if verify_password(user["password"], password):
        return True, "登录成功"
    else:
        return False, "密码错误"

def save_chat_message(username, session_id, role, content):
    """
    保存聊天消息到数据库
    
    参数:
    - username: 用户名
    - session_id: 会话ID
    - role: 消息角色 (user 或 assistant)
    - content: 消息内容
    
    返回:
    - 成功与否
    - 消息
    """
    try:
        message = {
            "username": username,
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        }
        chat_history_collection.insert_one(message)
        return True, "消息保存成功"
    except Exception as e:
        print(f"保存聊天消息失败: {e}")
        return False, f"保存失败: {str(e)}"

def get_chat_history(username, session_id=None):
    """
    获取用户的聊天历史记录
    
    参数:
    - username: 用户名
    - session_id: 会话ID (可选，如果不提供则返回所有会话)
    
    返回:
    - 聊天记录列表
    """
    # 验证username参数
    if not username or not isinstance(username, str):
        print("无效的用户名参数")
        return []
    
    # 验证当前登录用户是否与请求的用户名匹配
    import streamlit as st
    if "username" not in st.session_state or st.session_state.username != username:
        print("无权访问其他用户的聊天记录")
        return []
        
    try:
        query = {"username": username}
        if session_id:
            query["session_id"] = session_id
        
        # 按时间戳排序
        chat_history = list(chat_history_collection.find(query).sort("timestamp", 1))
        
        # 移除MongoDB的_id字段，因为它不可序列化
        for message in chat_history:
            if "_id" in message:
                del message["_id"]
        
        return chat_history
    except Exception as e:
        print(f"获取聊天历史记录失败: {e}")
        return []

def get_user_sessions(username):
    """
    获取用户的所有会话ID和最后一条消息
    
    参数:
    - username: 用户名
    
    返回:
    - 会话列表，每个会话包含ID和最后一条消息
    """
    # 验证username参数
    if not username or not isinstance(username, str):
        print("无效的用户名参数")
        return []
        
    # 验证当前登录用户是否与请求的用户名匹配
    import streamlit as st
    if "username" not in st.session_state or st.session_state.username != username:
        print("无权访问其他用户的聊天记录")
        return []
        
    try:
        # 使用聚合管道获取每个会话的最后一条消息
        pipeline = [
            {"$match": {"username": username}},
            {"$sort": {"timestamp": 1}},
            {"$group": {
                "_id": "$session_id",
                "last_message": {"$last": "$content"},
                "timestamp": {"$last": "$timestamp"},
                "messages": {"$push": {"role": "$role", "content": "$content"}}
            }},
            {"$sort": {"timestamp": -1}}
        ]
        
        sessions = list(chat_history_collection.aggregate(pipeline))
        
        # 格式化结果
        formatted_sessions = []
        for session in sessions:
            formatted_sessions.append({
                "session_id": session["_id"],
                "last_message": session["last_message"],
                "timestamp": session["timestamp"],
                "messages": session["messages"]
            })
        
        return formatted_sessions
    except Exception as e:
        print(f"获取用户会话列表失败: {e}")
        return []