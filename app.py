import streamlit as st
import os
import json
import time
import requests
from openai import AzureOpenAI
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from datetime import datetime
from PIL import Image
import io
import uuid

load_dotenv()

# ==================== 페이지 설정 ====================
st.set_page_config(
    page_title="Agent Guru",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 커스텀 CSS ====================
# 브라우저 테마 감지 및 강제 모드 지원
mode_css = """
    .main-header {
        text-align: center;
        padding: 2rem 0;
        font-size: 3rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
        /* 라이트 모드: 어두운 보라색 (명확하게 보이도록) */
        color: #667eea !important;
        background: none !important;
        -webkit-text-fill-color: #667eea !important;
    }
    /* 다크 모드용 밝은 보라색 */
    @media (prefers-color-scheme: dark) {
        .main-header {
            color: #a78bfa !important;
            background: none !important;
            -webkit-text-fill-color: #a78bfa !important;
        }
    }
    .subtitle {
        text-align: center;
        font-size: 1.2rem;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
    }
    /* 새 채팅 버튼 고정 크기 */
    button[key="new_chat_btn"] {
        width: 120px !important;
        min-width: 120px !important;
        max-width: 120px !important;
        white-space: nowrap !important;
    }
    /* 기본 스타일 (라이트 모드) */
    .feature-box {
        background-color: #f8f9fa;
        color: #000000;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        border-left: 4px solid #667eea;
    }
    .feature-box h4, .feature-box p {
        color: #000000;
    }
    .info-box {
        background-color: #e3f2fd;
        color: #000000;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #2196f3;
    }
    .info-box h3, .info-box p {
        color: #000000;
    }
    .subtitle {
        color: #666;
    }
    .help-section {
        background-color: #fff3e0;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #ff9800;
    }
    /* 다크 모드 (브라우저 기본 테마) - 강제 클래스가 없을 때만 적용 */
    @media (prefers-color-scheme: dark) {
        .feature-box:not(.force-light):not(.force-dark) {
            background-color: #1e1e1e !important;
            color: #ffffff !important;
        }
        .feature-box:not(.force-light):not(.force-dark) h4, 
        .feature-box:not(.force-light):not(.force-dark) p {
            color: #ffffff !important;
        }
        .info-box:not(.force-light):not(.force-dark) {
            background-color: #1e1e1e !important;
            color: #ffffff !important;
        }
        .info-box:not(.force-light):not(.force-dark) h3, 
        .info-box:not(.force-light):not(.force-dark) p {
            color: #ffffff !important;
        }
        .subtitle:not(.force-light):not(.force-dark) {
            color: #ffffff !important;
        }
    }
    /* 강제 라이트 모드 */
    .force-light {
        background-color: #f8f9fa !important;
        color: #000000 !important;
    }
    .force-light h3, .force-light h4, .force-light p {
        color: #000000 !important;
    }
    /* 강제 다크 모드 */
    .force-dark {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
    }
    .force-dark h3, .force-dark h4, .force-dark p {
        color: #ffffff !important;
    }
"""

st.markdown(f"<style>{mode_css}</style>", unsafe_allow_html=True)

# ==================== 헤더 ====================
st.markdown('<h1 class="main-header">🤖 Agent Guru</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI Agent 전문 지식 챗봇 - 학습부터 코드 생성까지</p>', unsafe_allow_html=True)

# ==================== 클라이언트 설정 ====================
client = AzureOpenAI(
    azure_endpoint=os.getenv("EXER_AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("EXER_AZURE_OPENAI_API_KEY"),
    api_version="2024-05-01-preview"
)

# ==================== 함수 정의 (날씨, 시간) ====================
def get_current_weather(location, unit=None):
    location_lower = location.lower()
    cities = {"tokyo": "Tokyo", "san francisco": "San Francisco", "paris": "Paris", "seoul": "Seoul", "london": "London"}
    for key in cities:
        if key in location_lower:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={key}&count=1"
            geo = requests.get(geo_url).json()
            if not geo.get("results"):
                return json.dumps({"location": location, "temperature": "unknown"})
            lat, lon = geo['results'][0]['latitude'], geo['results'][0]['longitude']
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
            data = requests.get(weather_url).json()
            desc = "맑음" if data["current"]["weather_code"] == 0 else "구름" if data["current"]["weather_code"] < 10 else "비/눈"
            return json.dumps({
                "location": cities[key],
                "temperature": data["current"]["temperature_2m"],
                "unit": "°C",
                "description": desc
            })
    return json.dumps({"location": location, "temperature": "unknown"})

def get_current_time(location):
    location_lower = location.lower()
    TIMEZONE_DATA = {
        "tokyo": "Asia/Tokyo", "seoul": "Asia/Seoul", "san francisco": "America/Los_Angeles",
        "paris": "Europe/Paris", "london": "Europe/London", "new york": "America/New_York"
    }
    for key, tz in TIMEZONE_DATA.items():
        if key in location_lower:
            now = datetime.now(ZoneInfo(tz))
            return json.dumps({
                "location": key.title(),
                "current_time": now.strftime("%Y년 %m월 %d일 %A %p %I:%M")
            })
    return json.dumps({"location": location, "current_time": "unknown"})

# ==================== 사이드바: 설정 + 채팅 기록 ====================
with st.sidebar:
    st.markdown("## ⚙️ 설정")
    
    with st.expander("📊 응답 매개변수 조절", expanded=True):
        temperature = st.slider(
            "Temperature (창의성)",
            0.0, 1.0, 0.7, 0.05,
            help="값이 높을수록 창의적이고 다양하게 응답합니다. 낮을수록 일관되고 정확하게 응답합니다."
        )
        top_p = st.slider(
            "Top P (다양성)",
            0.0, 1.0, 0.95, 0.05,
            help="응답의 다양성을 조절합니다. 높을수록 더 다양한 표현을 사용합니다."
        )
    
    st.divider()
    
    st.markdown("## 💬 대화 관리")

    # Local Storage에서 채팅 기록 불러오기
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = {}
    
    if "save_mode" not in st.session_state:
        st.session_state.save_mode = False

    chat_titles = list(st.session_state.chat_history.keys())
    
    if chat_titles:
        st.markdown("### 📚 저장된 대화")
        selected_chat = st.radio(
            "불러올 대화 선택",
            ["새 채팅 시작"] + chat_titles,
            index=0,
            label_visibility="collapsed"
        )
        
        if selected_chat != "새 채팅 시작":
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📂 불러오기", key="load_chat"):
                    st.session_state.messages = st.session_state.chat_history[selected_chat]["messages"].copy()
                    st.session_state.thread_id = st.session_state.chat_history[selected_chat]["thread_id"]
                    st.success(f"'{selected_chat}' 대화가 불러와졌습니다!")
                    st.rerun()
            with col2:
                if st.button("🗑️ 삭제", key="delete_chat"):
                    del st.session_state.chat_history[selected_chat]
                    st.success("삭제되었습니다!")
                    st.rerun()
    else:
        st.info("💡 저장된 대화가 없습니다. 대화를 시작하고 저장해보세요!")
        selected_chat = "새 채팅 시작"
    
    st.divider()
    
    # 저장 모드 토글
    if not st.session_state.save_mode:
        if st.button("💾 현재 대화 저장", use_container_width=True):
            st.session_state.save_mode = True
            st.rerun()
    else:
        st.markdown("### 💾 대화 저장")
        default_title = f"대화 {len(chat_titles)+1}"
        title = st.text_input("대화 제목 입력", value=default_title, key="save_title_input")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ 저장", type="primary", use_container_width=True):
                if title and title.strip():
                    # 메시지가 있을 때만 저장
                    if "messages" in st.session_state and len(st.session_state.messages) > 0:
                        st.session_state.chat_history[title] = {
                            "messages": st.session_state.messages.copy(),
                            "thread_id": st.session_state.thread_id
                        }
                        st.session_state.save_mode = False
                        st.success("저장되었습니다!")
                        st.rerun()
                    else:
                        st.warning("저장할 대화가 없습니다.")
                else:
                    st.warning("제목을 입력해주세요.")
        with col2:
            if st.button("❌ 취소", use_container_width=True):
                st.session_state.save_mode = False
                st.rerun()
    
    st.divider()
    
    # 도움말 섹션
    with st.expander("❓ 도움말", expanded=False):
        st.markdown("""
        ### 🎯 주요 기능
        
        **1. RAG (검색 증강 생성)**
        - AI Agent 관련 PDF 문서를 벡터 DB에 저장
        - 정확한 전문 지식 제공
        
        **2. Code Interpreter**
        - 수식 그래프 실시간 생성
        - 코드 실행 및 시각화
        
        **3. 자연스러운 대화**
        - 한국어로 친절하게 응답
        - AI Agent 개념을 쉽게 설명
        
        ### 💡 사용 팁
        
        - **Temperature**: 창의적인 응답이 필요하면 높게, 정확한 답변이 필요하면 낮게 설정
        - **Top P**: 다양한 표현을 원하면 높게 설정
        - 대화는 브라우저 Local Storage에 저장됩니다
        - 그래프나 코드가 필요한 질문을 하면 자동으로 생성됩니다
        """)
    
    with st.expander("📝 예시 질문", expanded=False):
        st.markdown("""
        - "AI Agent란 무엇인가요?"
        - "AI Agent의 주요 구성 요소를 설명해주세요"
        - "간단한 AI Agent 코드 예제를 보여주세요"
        - "y = x^2 그래프를 그려주세요"
        - "LangChain을 사용한 Agent 구현 방법을 알려주세요"
        """)

# ==================== 새 채팅 버튼 (우측 상단) ====================
col1, col2 = st.columns([10, 1])
with col2:
    if st.button("✨ 새 채팅", key="new_chat_btn"):
        st.session_state.messages = []
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
        st.rerun()

# ==================== Assistant 생성 (최초 1회) ====================
if "assistant" not in st.session_state:
    st.session_state.assistant = client.beta.assistants.create(
        name="Agent Guru",
        instructions="""너는 'Agent Guru'라는 AI Agent 전문 챗봇이야. 
        한국어로 친절하고 이해하기 쉽게 대답해야 해.
        AI Agent 관련 정보들을 단계별로 설명하고, 필요하면 코드 예제도 제공해줘.
        Code Interpreter를 활용해서 그래프나 시각화가 필요한 경우 자동으로 생성해줘.
        초보자도 이해할 수 있도록 전문 용어를 쉽게 풀어서 설명해줘.""",
        model="gpt-4o-mini",
        temperature=temperature,
        top_p=top_p,
        tools=[
            {"type": "code_interpreter"},
            {"type": "function", "function": {
                "name": "get_current_weather",
                "description": "도시의 현재 날씨 반환",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "영어 도시명"},
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                    },
                    "required": ["location"]
                }
            }},
            {"type": "function", "function": {
                "name": "get_current_time",
                "description": "도시의 현재 시간 반환",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "영어 도시명"}
                    },
                    "required": ["location"]
                }
            }}
        ],
        tool_resources={
            "code_interpreter": {}
        }
    )

# ==================== Thread 초기화 ====================
if "thread_id" not in st.session_state:
    thread = client.beta.threads.create()
    st.session_state.thread_id = thread.id

if "messages" not in st.session_state:
    st.session_state.messages = []

# ==================== 테마 클래스 결정 ====================
# 브라우저 테마를 따르므로 클래스 없음
theme_class = ''

# ==================== 초기 환영 메시지 ====================
if len(st.session_state.messages) == 0:
    st.markdown(f"""
    <div class="info-box {theme_class}">
        <h3>👋 Agent Guru에 오신 것을 환영합니다!</h3>
        <p>이 챗봇은 AI Agent에 대한 전문 지식을 제공하고, 코드 생성부터 그래프 시각화까지 도와드립니다.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 💡 시작하기")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="feature-box {theme_class}">
            <h4>📚 전문 지식</h4>
            <p>RAG를 통한 정확한 AI Agent 정보 제공</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="feature-box {theme_class}">
            <h4>📊 시각화</h4>
            <p>Code Interpreter로 그래프와 차트 생성</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="feature-box {theme_class}">
            <h4>💻 코드 생성</h4>
            <p>실제 사용 가능한 AI Agent 코드 제공</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.markdown("### 🎯 예시 질문")
    example_questions = [
        "AI Agent란 무엇인가요?",
        "AI Agent의 주요 구성 요소를 설명해주세요",
        "간단한 AI Agent 코드 예제를 보여주세요",
        "y = x^2 그래프를 그려주세요"
    ]
    
    cols = st.columns(2)
    for idx, question in enumerate(example_questions):
        with cols[idx % 2]:
            if st.button(f"💬 {question}", key=f"example_{idx}", use_container_width=True):
                # 예시 질문을 세션 상태에 저장하고 처리
                st.session_state.pending_question = question
                st.rerun()

# ==================== 예시 질문 처리 ====================
if "pending_question" in st.session_state:
    prompt = st.session_state.pending_question
    del st.session_state.pending_question
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    client.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=prompt
    )

    with st.chat_message("assistant"):
        with st.spinner("🤔 생각 중..."):
            placeholder = st.empty()
            full_response = ""
            image_list = []

            run = client.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=st.session_state.assistant.id,
                temperature=temperature,
                top_p=top_p
            )

            while run.status in ["queued", "in_progress", "requires_action"]:
                time.sleep(0.7)
                run = client.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)

                if run.status == "requires_action":
                    tool_outputs = []
                    for tool in run.required_action.submit_tool_outputs.tool_calls:
                        args = json.loads(tool.function.arguments)
                        if tool.function.name == "get_current_weather":
                            output = get_current_weather(**args)
                        elif tool.function.name == "get_current_time":
                            output = get_current_time(**args)
                        else:
                            output = json.dumps({"error": "unknown function"})
                        tool_outputs.append({"tool_call_id": tool.id, "output": output})

                    run = client.beta.threads.runs.submit_tool_outputs(
                        thread_id=st.session_state.thread_id,
                        run_id=run.id,
                        tool_outputs=tool_outputs
                    )

            if run.status == "completed":
                msgs = client.beta.threads.messages.list(thread_id=st.session_state.thread_id)
                latest = msgs.data[0]

                for block in latest.content:
                    if block.type == "text":
                        full_response += block.text.value
                    elif block.type == "image_file":
                        data = client.files.content(block.image_file.file_id).read()
                        img = Image.open(io.BytesIO(data))
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        image_list.append(buf.getvalue())

                placeholder.markdown(full_response)
                for img in image_list:
                    st.image(img, width=600)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "images": image_list
                })

# ==================== 과거 메시지 출력 ====================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "images" in msg:
            for img in msg["images"]:
                st.image(img, width=600)

# ==================== 사용자 입력 ====================
if prompt := st.chat_input("AI Agent에 대해 무엇이 궁금하신가요? (예: AI Agent란 무엇인가요?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    client.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=prompt
    )

    with st.chat_message("assistant"):
        with st.spinner("🤔 생각 중..."):
            placeholder = st.empty()
            full_response = ""
            image_list = []

            run = client.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=st.session_state.assistant.id,
                temperature=temperature,
                top_p=top_p
            )

            while run.status in ["queued", "in_progress", "requires_action"]:
                time.sleep(0.7)
                run = client.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)

                if run.status == "requires_action":
                    tool_outputs = []
                    for tool in run.required_action.submit_tool_outputs.tool_calls:
                        args = json.loads(tool.function.arguments)
                        if tool.function.name == "get_current_weather":
                            output = get_current_weather(**args)
                        elif tool.function.name == "get_current_time":
                            output = get_current_time(**args)
                        else:
                            output = json.dumps({"error": "unknown function"})
                        tool_outputs.append({"tool_call_id": tool.id, "output": output})

                    run = client.beta.threads.runs.submit_tool_outputs(
                        thread_id=st.session_state.thread_id,
                        run_id=run.id,
                        tool_outputs=tool_outputs
                    )

            if run.status == "completed":
                msgs = client.beta.threads.messages.list(thread_id=st.session_state.thread_id)
                latest = msgs.data[0]

                for block in latest.content:
                    if block.type == "text":
                        full_response += block.text.value
                    elif block.type == "image_file":
                        data = client.files.content(block.image_file.file_id).read()
                        img = Image.open(io.BytesIO(data))
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        image_list.append(buf.getvalue())

                placeholder.markdown(full_response)
                for img in image_list:
                    st.image(img, width=600)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "images": image_list
                })
