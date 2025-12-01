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

load_dotenv()

st.set_page_config(page_title="AI 챗봇", layout="centered")
st.title("통합 AI 챗봇")

# Azure OpenAI 클라이언트
client = AzureOpenAI(
    azure_endpoint=os.getenv("EXER_AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("EXER_AZURE_OPENAI_API_KEY"),
    api_version="2024-05-01-preview"
)

# === 실제로 사용하는 함수들 (기존 코드 그대로) ===
def get_current_weather(location, unit=None):
    location_lower = location.lower()
    cities = {"tokyo": "Tokyo", "san francisco": "San Francisco", "paris": "Paris", "seoul": "Seoul"}

    for key in cities:
        if key in location_lower:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={key}&count=1"
            geo = requests.get(geo_url).json()
            if not geo.get("results"):
                return json.dumps({"location": location, "temperature": "unknown"})

            lat, lon = geo['results'][0]['latitude'], geo['results'][0]['longitude']
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
            data = requests.get(weather_url).json()

            return json.dumps({
                "location": cities[key],
                "temperature": data["current"]["temperature_2m"],
                "unit": "°C",
                "description": "맑음" if data["current"]["weather_code"] == 0 else "흐림/비 등"
            })
    return json.dumps({"location": location, "temperature": "unknown"})


def get_current_time(location):
    location_lower = location.lower()
    TIMEZONE_DATA = {
        "tokyo": "Asia/Tokyo",
        "san francisco": "America/Los_Angeles",
        "paris": "Europe/Paris",
        "seoul": "Asia/Seoul"
    }
    for key, tz in TIMEZONE_DATA.items():
        if key in location_lower:
            now = datetime.now(ZoneInfo(tz))
            return json.dumps({
                "location": key.capitalize(),
                "current_time": now.strftime("%Y년 %m월 %d일 %p %I:%M")
            })
    return json.dumps({"location": location, "current_time": "unknown"})


# === Assistant 한 번만 생성 (앱 시작 시 한 번만) ===
if "assistant" not in st.session_state:
    st.session_state.assistant = client.beta.assistants.create(
        name="날씨+그래프 봇",
        instructions="너는 친절한 한국어 챗봇이야. 날씨, 시간, 수식 그래프 그리기 등을 도와줘. 모르는 도시는 솔직히 모른다고 해.",
        model="gpt-4o-mini",  # 본인의 deployment name
        tools=[
            {"type": "code_interpreter"},
            {
                "type": "function",
                "function": {
                    "name": "get_current_weather",
                    "description": "주어진 도시의 현재 날씨를 반환",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "도시 이름 (영어로 변환해서 전달)"},
                            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                        },
                        "required": ["location"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "주어진 도시의 현재 시간을 반환",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "도시 이름 (영어로 변환해서 전달)"}
                        },
                        "required": ["location"]
                    }
                }
            }
        ]
    )

# === 대화 세션별 thread 관리 ===
if "thread_id" not in st.session_state:
    thread = client.beta.threads.create()
    st.session_state.thread_id = thread.id

# === 과거 대화 표시 ===
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "images" in msg:
            for img_bytes in msg["images"]:
                st.image(img_bytes, width=500)

# === 사용자 입력 ===
if prompt := st.chat_input("궁금한 거 물어보세요!"):
    # 1. 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Thread에 메시지 추가
    client.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=prompt
    )

    # 3. Run 시작
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        run = client.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=st.session_state.assistant.id
        )

        # Run 상태 polling
        while run.status in ["queued", "in_progress", "requires_action"]:
            time.sleep(0.5)
            run = client.beta.threads.runs.retrieve(
                thread_id=st.session_state.thread_id,
                run_id=run.id
            )

            # tool 호출이 필요한 경우
            if run.status == "requires_action":
                tool_outputs = []
                for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                    if tool_call.function.name == "get_current_weather":
                        args = json.loads(tool_call.function.arguments)
                        output = get_current_weather(**args)
                        tool_outputs.append({"tool_call_id": tool_call.id, "output": output})
                    elif tool_call.function.name == "get_current_time":
                        args = json.loads(tool_call.function.arguments)
                        output = get_current_time(**args)
                        tool_outputs.append({"tool_call_id": tool_call.id, "output": output})

                # tool 결과 제출
                run = client.beta.threads.runs.submit_tool_outputs(
                    thread_id=st.session_state.thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )

        # 최종 완료
        if run.status == "completed":
            messages = client.beta.threads.messages.list(thread_id=st.session_state.thread_id)
            latest_message = messages.data[0]

            response_text = ""
            image_bytes_list = []

            for block in latest_message.content:
                if block.type == "text":
                    response_text += block.text.value
                elif block.type == "image_file":
                    file_id = block.image_file.file_id
                    image_data = client.files.content(file_id).read()
                    image = Image.open(io.BytesIO(image_data))
                    buffered = io.BytesIO()
                    image.save(buffered, format="PNG")
                    image_bytes_list.append(buffered.getvalue())

            # 화면에 출력
            full_response = response_text
            message_placeholder.markdown(full_response + "▌")

            # 이미지 있으면 표시
            for img_bytes in image_bytes_list:
                st.image(img_bytes, width=500)

            # 세션에 저장
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response,
                "images": image_bytes_list
            })
