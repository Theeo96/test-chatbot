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
st.set_page_config(page_title="통합 AI 챗봇", layout="wide")
st.title("통합 AI 챗봇 (RAG + 그래프 + 날씨 + 시간)")

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
    st.header("설정")
    temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.05)
    top_p = st.slider("Top P", 0.0, 1.0, 0.95, 0.05)

    st.divider()
    st.header("이전 대화 기록")

    # Local Storage에서 채팅 기록 불러오기
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = {}

    chat_titles = list(st.session_state.chat_history.keys())
    selected_chat = st.radio("불러올 대화 선택", ["새 채팅 시작"] + chat_titles, index=0)

    if selected_chat != "새 채팅 시작":
        if st.button("이 대화 불러오기"):
            st.session_state.messages = st.session_state.chat_history[selected_chat]["messages"]
            st.session_state.thread_id = st.session_state.chat_history[selected_chat]["thread_id"]
            st.success(f"'{selected_chat}' 대화가 불러와졌습니다!")
            st.experimental_rerun()

    if st.button("현재 대화 저장"):
        title = st.text_input("대화 제목 입력", value=f"대화 {len(chat_titles)+1}")
        if st.button("저장 확인"):
            st.session_state.chat_history[title] = {
                "messages": st.session_state.messages.copy(),
                "thread_id": st.session_state.thread_id
            }
            st.success("저장되었습니다!")

# ==================== 새 채팅 버튼 (우측 상단) ====================
col1, col2 = st.columns([6, 1])
with col2:
    if st.button("새 채팅"):
        st.session_state.messages = []
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
        st.experimental_rerun()

# ==================== Assistant 생성 (최초 1회) ====================
if "assistant" not in st.session_state:
    st.session_state.assistant = client.beta.assistants.create(
        name="통합 AI 어시스턴트",
        instructions="너는 한국어로 친절하게 대답하는 AI야. AI Agent 관련 정보들을 알아듣기 쉬운 설명과 함께 제공해줘.",
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
        tool_resources={},
        extra_body={
            "data_sources": [{
                "type": "azure_search",
                "parameters": {
                    "endpoint": os.getenv("AZURE_SEARCH_ENDPOINT"),
                    "index_name": "ai-agent-rag",
                    "semantic_configuration": "ai-agent-rag-semantic-configuration",
                    "query_type": "vector_semantic_hybrid",
                    "authentication": {
                        "type": "api_key",
                        "key": os.getenv("AZURE_SEARCH_API_KEY")
                    },
                    "embedding_dependency": {
                        "type": "deployment_name",
                        "deployment_name": "text-embedding-ada-002"
                    },
                    "top_n_documents": 5,
                    "in_scope": True,
                    "strictness": 3
                }
            }]
        }
    )

# ==================== Thread 초기화 ====================
if "thread_id" not in st.session_state:
    thread = client.beta.threads.create()
    st.session_state.thread_id = thread.id

if "messages" not in st.session_state:
    st.session_state.messages = []

# ==================== 과거 메시지 출력 ====================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "images" in msg:
            for img in msg["images"]:
                st.image(img, width=600)

# ==================== 사용자 입력 ====================
if prompt := st.chat_input("무엇이 궁금하신가요? (예: ai agent에 대한 전반적인 소개)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    client.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=prompt
    )

    with st.chat_message("assistant"):
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
