import streamlit as st
import requests
import uuid
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory
from langchain_core.tools import BaseTool  # 添加 BaseTool 导入
from langchain.agents import Tool  # 保留 Tool 导入
from langchain_community.llms.tongyi import Tongyi
import os
from langchain.agents import initialize_agent, AgentType
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from flask import Flask, request, jsonify
from flask_cors import CORS
import base64
import threading
from langchain.schema import AIMessage
from datetime import datetime, timedelta
from typing import Any, Optional
import auth  # 导入认证模块
import db  # 导入数据库模块
# 定义全局字符串，用于保存用户当前的情感信息
current_user_emotion = ""


# ==================== ChatBot类 ====================
class ChatBot:
    def __init__(self):
        os.environ["DASHSCOPE_API_KEY"] = os.getenv("DASHSCOPE_API_KEY", "sk-38a6f574d6c6483eae5c32998a16822a")
        os.environ["DASHSCOPE_API_BASE"] = os.getenv("DASHSCOPE_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")

        self.llm = ChatOpenAI(
            model="qwen-max",
            temperature=0.8,
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        self.llm_e = ChatOpenAI(
            model="qwen-max",
            temperature=0.8,
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        self.llm_chat = ChatOpenAI(
            model="qwen-max-latest",
            temperature=0.8,
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        # 初始化工具（移除 @tool，使用 Tool 对象）
        self.bocha_tool = Tool(
            name="Bocha Web Search",
            func=self.bocha_websearch_tool,
            description="使用Bocha Web Search API进行搜索互联网网页，输入应为搜索查询字符串，输出将返回搜索结果的详细信息。包括网页标题、网页URL",
        )

        self.emotion_tool = EmotionAnalysisTool(llm_instance=self.llm_e)

        self.memory_dict = {}

        self.agent_prompt = """
        作为一个高情商的对话伙伴，对于用户提出的任何问题，你都能够提供既得体又关切的回答。现在，请针对以下问题展现你的高情商回应："${question}"，并确保在回复中充分考虑到对方的情绪状态和潜在需求。注意：对于用户提出的每一个问题，你都应该在文末加上你的搜索结果
        注意结合用户当前具体的心理状况，你可以使用emotion_tool
        """

        self.prompt_template = """
        作为一个高情商的对话伙伴，对于用户提出的任何问题，你都能够提供既得体又关切的回答。现在，请针对以下问题展现你的高情商回应："${question}"，并确保在回复中充分考虑到对方的情绪状态和潜在需求。注意：对于用户提出的每一个问题，你都应该在文末加上你的搜索结果
        """

        self.prompt = PromptTemplate(
            input_variables=["question"],
            template=self.prompt_template
        )

        self.chain = LLMChain(llm=self.llm_chat, prompt=self.prompt)

    def get_memory(self, session_id):
        if session_id not in self.memory_dict:
            self.memory_dict[session_id] = ConversationBufferMemory(memory_key="chat_history")
        return self.memory_dict[session_id]

    def load_memory_from_db(self, session_id, username):
        memory = self.get_memory(session_id)
        memory.chat_memory.messages = []
        user_sessions = db.get_user_sessions(username)
        for session in user_sessions:
            if session["session_id"] == session_id:
                for msg in session["messages"]:
                    if msg["role"] == "user":
                        memory.chat_memory.add_user_message(msg["content"])
                    elif msg["role"] == "assistant":
                        memory.chat_memory.add_ai_message(msg["content"])
                break
        return memory

    def get_agent(self, memory):
        return initialize_agent(
            tools=[self.bocha_tool, self.emotion_tool],
            llm=self.llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            agent_kwargs={"agent_prompt": self.agent_prompt, "memory": memory}
        )

    @staticmethod
    def bocha_websearch_tool(query: str, count: int = 20) -> str:
        """使用Bocha Web Search API进行网页搜索"""
        url = 'https://api.bochaai.com/v1/web-search'
        headers = {
            'Authorization': f'Bearer sk-6012a020f72d4c26ae5ad415300c94f9',
            'Content-Type': 'application/json'
        }
        data = {
            "query": query,
            "freshness": "noLimit",
            "summary": True,
            "count": count
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            try:
                json_response = response.json()
                if json_response["code"] == 200 and json_response.get("data"):
                    webpages = json_response["data"]["webPages"]["value"]
                    if not webpages:
                        return "未找到相关结果."
                    formatted_results = ""
                    for idx, page in enumerate(webpages, start=1):
                        formatted_results += (
                            f"引用：{idx}\n"
                            f"标题：{page['name']}\n"
                            f"URL: {page['url']}\n"
                            f"摘要：{page['summary']}\n"
                            f"网站名称：{page['siteName']}\n"
                            f"网站图标：{page['siteIcon']}\n"
                            f"发布时间：{page['dateLastCrawled']}\n\n"
                        )
                    return formatted_results.strip()
                else:
                    return f"搜索失败，原因：{json_response.get('message', '未知错误')}"
            except Exception as e:
                return f"处理搜索结果失败，原因是：{str(e)}\n原始响应：{response.text}"
        else:
            return f"搜索API请求失败，状态码：{response.status_code}, 错误信息：{response.text}"

    def generate_session_topic(self, user_question, assistant_response):
        """根据用户第一条消息和助手回复生成会话主题（15字以内）"""
        prompt = f"""
        根据以下对话生成一个15字以内的会话主题：
        用户问题：{user_question}
        助手回复：{assistant_response}
        输出格式：直接返回主题字符串，不含多余说明。
        """
        topic = self.llm(prompt).content.strip()  # 提取 content 并调用 strip()
        if len(topic) > 15:
            topic = topic[:15]
        return topic


    def process_message(self, user_question, session_id, username):
        # 加载用户会话的内存
        memory = self.load_memory_from_db(session_id, username)

        # 获取当前情绪（由 YOLO 分析得到，或者默认值）
        global current_user_emotion

        # 获取情感信息，提取出情感状态
        emotion_info = current_user_emotion.split("分析时间: ")[0].strip()
        print(emotion_info)

        # 根据用户提问和当前情感信息生成提示词
        prompt = f"""
        作为一个高情商的对话伙伴，对于用户提出的任何问题，你都能够提供既得体又关切的回答。
        用户问题是：{user_question}
        当前情感信息是：{emotion_info} ,请时刻地在每一个回答中都调用你的emotion_tool
        请基于这些信息给出一个回答，务必关注用户的情绪状态并做出适当回应。
        """

        # 使用agent执行情感处理与用户问题回应
        agent = self.get_agent(memory)
        response = agent.run(user_question)

        # 添加聊天记录到内存
        memory.chat_memory.add_user_message(user_question)
        memory.chat_memory.add_ai_message(response)

        return response


# ==================== EmotionAnalysisTool类 ====================
class EmotionAnalysisTool(BaseTool):
    name: str = "emotion_analysis"
    description: str = "分析用户最近一次提供的图片中的情感状态，并给出回答建议"
    llm: ChatOpenAI

    def __init__(self, llm_instance: ChatOpenAI, **data: Any):
        data['llm'] = llm_instance
        super().__init__(**data)

    def _run(self, user_id: str) -> str:
        global current_user_emotion

        # 如果没有情感数据，要求用户提供情感分析图片
        if not current_user_emotion:
            return "未找到您的情感分析记录，请先提供一张图片进行分析。"

        try:
            # 从全局变量中解析情感信息
            parts = current_user_emotion.split("分析时间: ")
            emotion_info = parts[0].strip()
            timestamp_str = parts[1].split("。")[0].strip()
            analysis_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()

            # # 判断是否情绪数据过期（例如超过10秒）
            # if now - analysis_time > timedelta(seconds=10):
            #     current_user_emotion = ""  # 数据过期，清空
            #     return "情感记录已过期，请重新上传图片。"

            # 构建情感分析回应的提示
            eprompt = f"根据以下情感分析结果为用户提供回应建议：\n{emotion_info} 分析时间: {timestamp_str}"

            # 生成情感回应
            eresponse_suggestion = self.llm(eprompt)
            return eresponse_suggestion
        except Exception as e:
            print(f"Error parsing current_user_emotion: {e}")
            return "未能正确解析情感分析结果，请稍后再试或重新进行情感分析。"

    async def _arun(self, user_id: str) -> str:
        raise NotImplementedError("此工具不支持异步操作")



# ==================== YOLO预测函数 ====================
def call_yolo_predict(image_path, username):
    global current_user_emotion
    abs_image_path = os.path.abspath(image_path)
    url = "http://127.0.0.1:5003/predict"

    with open(abs_image_path, 'rb') as img:
        response = requests.post(url, files={'image': img})
        if response.status_code == 200:
            result = response.json()
            emotion_str = result.get('result', '未检测到情绪')
            analysis_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 保存YOLO分析结果，附带时间戳
            current_user_emotion = f"{emotion_str} 分析时间: {analysis_time} 用户: {username}"
            return result
        else:
            print("Error:", response.status_code, response.text)
            return None


# ==================== Flask后端 ====================
app = Flask(__name__)
CORS(app)
UPLOAD_FOLDER = "screenshots"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


@app.route('/upload_screenshot', methods=['POST'])
def upload_screenshot():
    data = request.json
    if not data or 'image' not in data:
        return jsonify({'error': 'No image data provided'}), 400
    image_data = data['image'].split(",")[1]
    image_bytes = base64.b64decode(image_data)
    current_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"screenshot_{current_time_str}.jpg"
    file_path = os.path.join(UPLOAD_FOLDER, file_name)
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    result = call_yolo_predict(file_path)
    if result is not None:
        global current_user_emotion
        current_user_emotion = result
        # print("预测结果:", current_user_emotion)
    return jsonify({'message': 'Screenshot saved successfully', 'file': file_path}), 200


def run_flask():
    app.run(port=5001)


# ==================== Streamlit前端 ====================
def main():
    st.set_page_config(page_title="心语星", page_icon="3")
    if not auth.auth_page():
        st.stop()

    st.markdown("""
        <style>
            .css-17gblp5 img { display: none; }
            .user-message {
                background-color: #ccffcc; color: black; border-radius: 10px; padding: 10px;
                margin-left: auto; text-align: right; max-width: 70%; display: inline-block; clear: both;
            }
            .bot-message {
                background-color: white; color: black; border-radius: 10px; padding: 10px;
                margin-right: auto; max-width: 70%; display: inline-block; clear: both;
            }
        </style>
    """, unsafe_allow_html=True)

    st.title("心语星")

    if 'chatbot' not in st.session_state:
        st.session_state.chatbot = ChatBot()

    if 'sessions' not in st.session_state:
        st.session_state.sessions = {}
        if "username" in st.session_state:
            try:
                user_sessions = db.get_user_sessions(st.session_state.username)
                for session in user_sessions:
                    session_id = session["session_id"]
                    st.session_state.sessions[session_id] = session["messages"]
            except Exception as e:
                st.warning(f"加载会话失败: {e}")

    if 'current_session_id' not in st.session_state or st.session_state.current_session_id not in st.session_state.sessions:
        new_session_id = str(uuid.uuid4())
        st.session_state.sessions[new_session_id] = []
        st.session_state.current_session_id = new_session_id
        # if "username" in st.session_state:
        #     st.info(f"创建临时会话: {new_session_id[:8]}")

    html_content = """
    <div>
        <button id="toggleCameraBtn" style="width: 100%; margin-bottom: 10px;">开启摄像头</button>
        <div id="video-container" style="width: 100%; height: 150px; display:none;">
            <video id="video" autoplay playsinline style="width: 100%; height: 100%;"></video>
        </div>
    </div>
    <script>
        const video = document.getElementById('video');
        const videoContainer = document.getElementById('video-container');
        const toggleCameraBtn = document.getElementById('toggleCameraBtn');
        let streamStarted = false;
        let intervalId;
        async function startCamera() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 200, height: 150 } });
                video.srcObject = stream;
                streamStarted = true;
                videoContainer.style.display = 'block';
                toggleCameraBtn.innerText = '关闭摄像头';
                intervalId = setInterval(() => captureAndSendFrame(), 5000);
            } catch (err) { console.error("Error accessing the camera: ", err); }
        }
        function stopCamera() {
            if (streamStarted && video.srcObject) {
                clearInterval(intervalId);
                const tracks = video.srcObject.getTracks();
                tracks.forEach(track => track.stop());
                video.srcObject = null;
                streamStarted = false;
                videoContainer.style.display = 'none';
                toggleCameraBtn.innerText = '开启摄像头';
            }
        }
        function captureAndSendFrame() {
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const dataURL = canvas.toDataURL('image/jpeg');
            fetch('http://localhost:5001/upload_screenshot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: dataURL })
            }).then(response => response.json())
              .then(data => console.log('Success:', data))
              .catch((error) => console.error('Error:', error));
        }
        toggleCameraBtn.addEventListener('click', () => {
            if (!streamStarted) { startCamera(); } else { stopCamera(); }
        });
    </script>
    """

    def create_new_session():
        new_session_id = str(uuid.uuid4())
        st.session_state.sessions[new_session_id] = []
        st.session_state.current_session_id = new_session_id
        # if "username" in st.session_state:
        #     st.info(f"创建临时会话: {new_session_id[:8]}")

    def select_session(session_id):
        if session_id in st.session_state.sessions:
            st.session_state.current_session_id = session_id
        else:
            st.warning(f"会话 {session_id[:8]} 不存在，创建新会话")
            create_new_session()

    with st.sidebar:
        st.header("会话管理")
        if st.button("➕ 新建对话"):
            create_new_session()
        # search_query = st.text_input("搜索会话...")
        st.subheader("会话列表")
        user_sessions = {}
        if "username" in st.session_state:
            try:
                db_sessions = db.get_user_sessions(st.session_state.username)
                for session in db_sessions:
                    user_sessions[session["session_id"]] = session
            except Exception as e:
                st.warning(f"无法加载会话列表: {e}")

        for session_id, session_data in st.session_state.sessions.items():
            # 兼容旧数据结构
            if isinstance(session_data, list):
                messages = session_data
                title = "新会话"
            else:
                messages = session_data.get("messages", [])
                title = session_data.get("title", "新会话")

            timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            last_message = title  # 默认用会话标题作为显示内容

            if session_id in user_sessions:
                db_timestamp = user_sessions[session_id]["timestamp"]
                if isinstance(db_timestamp, datetime):
                    timestamp = db_timestamp.strftime("%Y/%m/%d %H:%M:%S")
                last_message = user_sessions[session_id]["last_message"][:20] + "..." \
                    if len(user_sessions[session_id]["last_message"]) > 20 \
                    else user_sessions[session_id]["last_message"]
            elif messages:
                # 自动生成会话主题，如果是“新会话”
                if title == "新会话" and len(messages) >= 2:
                    user_msg = messages[0]["content"]
                    bot_msg = messages[1]["content"]
                    topic = chatbot.generate_session_topic(user_msg, bot_msg)
                    # 更新标题
                    st.session_state.sessions[session_id]["title"] = topic
                    title = topic
                last_message = title  # 始终优先展示“主题”

            if st.button(f"{session_id[:15]} - {timestamp}", key=f"select_{session_id}"):
                select_session(session_id)

        st.markdown("---")
        st.write("摄像头功能")
        st.components.v1.html(html_content, height=200)

    if st.session_state.current_session_id not in st.session_state.sessions:
        create_new_session()
    current_messages = st.session_state.sessions[st.session_state.current_session_id]

    for message in current_messages:
        if message["role"] == "user":
            st.markdown(f'<div class="user-message">{message["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="bot-message">{message["content"]}</div>', unsafe_allow_html=True)

    if user_question := st.chat_input("请输入你的问题"):
        current_session_id = st.session_state.current_session_id

        if not st.session_state.sessions[current_session_id]:
            st.session_state.sessions[current_session_id].append({"role": "user", "content": user_question})
            with st.chat_message("user"):
                st.markdown(user_question)

            with st.spinner("🧠 小助手思考中..."):
                response = st.session_state.chatbot.process_message(user_question, current_session_id,
                                                                    st.session_state.username)
            st.session_state.sessions[current_session_id].append({"role": "assistant", "content": response})
            with st.chat_message("assistant"):
                st.markdown(response)

            topic = st.session_state.chatbot.generate_session_topic(user_question, response)
            old_session_id = current_session_id
            st.session_state.sessions[topic] = st.session_state.sessions.pop(old_session_id)
            st.session_state.current_session_id = topic

            if "username" in st.session_state:
                db.save_chat_message(st.session_state.username, topic, "user", user_question)
                db.save_chat_message(st.session_state.username, topic, "assistant", response)

        else:
            st.session_state.sessions[current_session_id].append({"role": "user", "content": user_question})
            with st.chat_message("user"):
                st.markdown(user_question)

            if "username" in st.session_state:
                db.save_chat_message(st.session_state.username, current_session_id, "user", user_question)

            with st.spinner("🧠 您的助手思考中..."):
                response = st.session_state.chatbot.process_message(user_question, current_session_id,
                                                                    st.session_state.username)
            st.session_state.sessions[current_session_id].append({"role": "assistant", "content": response})
            with st.chat_message("assistant"):
                st.markdown(response)

            if "username" in st.session_state:
                db.save_chat_message(st.session_state.username, current_session_id, "assistant", response)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    main()