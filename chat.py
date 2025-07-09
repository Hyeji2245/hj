import streamlit as st
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType
from azure.ai.projects.models import ConnectionType
from azure.ai.agents.models import ListSortOrder
from azure.ai.agents.models import MessageRole
import time

# --- Azure AI Configuration ---
PROJECT_ENDPOINT = "https://user06-aifoundry.services.ai.azure.com/api/projects/user06Project"
AGENT_ID = "asst_A5Yi3VOER0jtHcBHrYxVbH3a"

# 미리보기 질문 정의
PREVIEW_QUESTIONS = [
    "F5 101",
    "G/L 계정 &에 대해 전기 기간 &이 열려 있지 않습니다.",
    "ME 027",
    "플랜트 &에 있는 자재 &에 대한 배치 &이 존재하지 않습니다.",
    "PG 002",
    "인포타입 &에 대한 유효한 레코드가 없습니다.",
    "IDoc status 51",
    "오브젝트 & & &이 사용자 &에 의해 잠겨 있습니다."
]

# --- Azure Clients Initialization ---
@st.cache_resource
def get_agents_client():
    return AgentsClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

@st.cache_resource
def get_project_client():
    return AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
    )

agents_client = get_agents_client()
project_client = get_project_client()

# --- Agent 로드 (한 번만) ---
@st.cache_resource
def get_agent(_agent_id):
    try:
        return agents_client.get_agent(agent_id=_agent_id)
    except Exception as e:
        st.error(f"Agent를 불러오는 데 실패했습니다 (ID: {_agent_id}): {e}")
        return None

agent = get_agent(AGENT_ID)

# --- 유틸리티 함수: 에이전트에게 질문하고 답변 받기 ---
def get_agent_response(question, thread_id):
    if agent is None:
        st.error("Agent가 초기화되지 않았습니다. 관리자에게 문의하세요.")
        return "죄송합니다. 현재 Agent를 사용할 수 없습니다."

    try:
        agents_client.messages.create(
            thread_id=thread_id,
            role=MessageRole.USER,
            content=question
        )
        
        run = project_client.agents.runs.create_and_process(
            thread_id=thread_id,
            agent_id=agent.id
        )

        if run.status == "failed":
            return f"죄송합니다. AI 에이전트 실행 중 오류가 발생했습니다: {run.last_error}"
        else:
            messages = agents_client.messages.list(
                thread_id=thread_id, 
                order=ListSortOrder.DESCENDING
            )
            
            agent_response = "답변을 찾을 수 없습니다."
            
            for msg in messages:
                if msg.role == MessageRole.AGENT:
                    if msg.url_citation_annotations:
                        placeholder_annotations = {
                            annotation.text: f" [출처 {annotation.url_citation.title}]({annotation.url_citation.url})"
                            for annotation in msg.url_citation_annotations
                        }
                        for message_text in msg.text_messages:
                            msg_str = message_text.text.value
                            for k, v in placeholder_annotations.items():
                                msg_str = msg_str.replace(k, v)
                            agent_response = msg_str
                    else:
                        for message_text in msg.text_messages:
                            agent_response = message_text.text.value
                    break 
            return agent_response
    except Exception as e:
        return f"오류가 발생했습니다: {e}"


# --- 세션 상태 초기화 ---
st.set_page_config(page_title="SAP 오류 지식 챗봇", layout="centered")

if "current_view" not in st.session_state:
    st.session_state.current_view = "home"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "text_input_value" not in st.session_state:
    st.session_state.text_input_value = ""
if "chat_history_list" not in st.session_state:
    st.session_state.chat_history_list = []

# --- 유틸리티 함수: 현재 채팅 세션 저장 ---
def save_current_chat_session():
    if st.session_state.messages and st.session_state.thread_id:
        session_found = False
        for i, session in enumerate(st.session_state.chat_history_list):
            if session["thread_id"] == st.session_state.thread_id:
                st.session_state.chat_history_list[i]["messages"] = st.session_state.messages.copy()
                session_found = True
                break
        
        if not session_found:
            st.session_state.chat_history_list.append({
                "thread_id": st.session_state.thread_id,
                "messages": st.session_state.messages.copy()
            })

# --- 유틸리티 함수: 채팅 세션 삭제 ---
def delete_chat_session(target_thread_id):
    # 삭제할 세션을 제외하고 새로운 리스트 생성
    new_chat_history_list = [
        session for session in st.session_state.chat_history_list 
        if session["thread_id"] != target_thread_id
    ]
    st.session_state.chat_history_list = new_chat_history_list

    # 만약 현재 활성화된 세션이 삭제된 세션이라면, 홈 뷰로 전환하고 현재 세션 초기화
    if st.session_state.thread_id == target_thread_id:
        st.session_state.messages = []
        st.session_state.thread_id = None
        st.session_state.current_view = "home"
        st.session_state.text_input_value = ""
    st.rerun()


# --- 사이드바: 채팅 기록 표시 ---
with st.sidebar:
    st.markdown("### 💬 이전 채팅 기록")
    
    # "➕ 새 채팅 시작" 버튼을 가장 위에 배치
    if st.button("➕ 새 채팅 시작", key="new_chat_sidebar_button"):
        save_current_chat_session() # 현재 활성 채팅을 저장
        st.session_state.messages = []
        st.session_state.thread_id = None # 새 스레드 생성 유도
        st.session_state.current_view = "chat"
        st.session_state.text_input_value = ""
        st.rerun()

    st.markdown("---") # 구분선
    
    if st.session_state.chat_history_list:
        # 최신 채팅이 위에 오도록 역순으로 정렬
        for i, chat_session in enumerate(reversed(st.session_state.chat_history_list)):
            original_idx = len(st.session_state.chat_history_list) - 1 - i
            first_user_message = next((msg["content"] for msg in chat_session["messages"] if msg["role"] == "user"), "새로운 채팅")
            
            # 각 세션을 위한 컨테이너 생성 (버튼과 삭제 버튼을 나란히 배치)
            col1, col2 = st.columns([0.8, 0.2]) # 채팅 제목과 삭제 버튼을 위한 열 분할

            with col1:
                if st.button(f"세션 {original_idx+1}: {first_user_message[:25]}...", key=f"load_session_{original_idx}"):
                    save_current_chat_session() # 현재 활성 채팅이 있다면 저장 (다시 로드하기 전에)
                    
                    st.session_state.messages = chat_session["messages"]
                    st.session_state.thread_id = chat_session["thread_id"]
                    st.session_state.current_view = "chat"
                    st.session_state.text_input_value = ""
                    st.rerun()
            
            with col2:
                # 삭제 버튼 추가
                if st.button("🗑️", key=f"delete_session_{original_idx}"):
                    delete_chat_session(chat_session["thread_id"]) # 삭제 함수 호출
    else:
        st.info("저장된 채팅 기록이 없습니다.")


# --- 메인 콘텐츠 영역 ---
st.markdown("<h1 style='text-align: center;'>💡 SAP 오류 지식 챗봇 </h1>", unsafe_allow_html=True)

# --- 홈 뷰 ---
if st.session_state.current_view == "home":
    st.markdown("<h4 style='text-align: center;'>SAP 오류 코드 및 관련 문서에 대해 질문해주세요.</h4>", unsafe_allow_html=True)
    st.markdown("<h5 style='text-align: center;'>아래 미리보기 질문을 선택하거나, 직접 질문을 입력해보세요.</h5>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    st.subheader("미리보기 질문:")
    
    cols = st.columns([3, 2])
    for i, q in enumerate(PREVIEW_QUESTIONS):
        with cols[i % 2]:
            if st.button(q, key=f"preview_q_{i}"):
                save_current_chat_session() # 새 채팅 시작 전 현재 채팅 저장
                st.session_state.current_view = "chat"
                st.session_state.messages = []
                st.session_state.thread_id = None
                st.session_state.initial_question = q
                st.session_state.text_input_value = ""
                st.rerun()

    st.markdown("<br><br>", unsafe_allow_html=True)

    st.subheader("직접 질문 입력:")
    
    prompt = st.text_area(
        "여기에 질문을 입력하세요...",
        value=st.session_state.text_input_value,
        height=100,
        key="home_text_area"
    )
    
    if st.button("질문 전송", key="submit_home_question"):
        if prompt:
            save_current_chat_session() # 새 채팅 시작 전 현재 채팅 저장
            st.session_state.current_view = "chat"
            st.session_state.messages = []
            st.session_state.thread_id = None
            st.session_state.initial_question = prompt
            st.session_state.text_input_value = ""
            st.rerun()


# --- 채팅 뷰 ---
elif st.session_state.current_view == "chat":
    # 챗 메시지 표시
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 미리보기/직접 입력 질문으로 들어왔을 때 초기 질문 처리
    if "initial_question" in st.session_state and st.session_state.initial_question:
        prompt_to_process = st.session_state.initial_question
        del st.session_state.initial_question

        st.session_state.messages.append({"role": "user", "content": prompt_to_process})
        with st.chat_message("user"):
            st.markdown(prompt_to_process)

        with st.spinner("AI 에이전트가 답변을 생성 중입니다..."):
            if st.session_state.thread_id is None:
                new_thread = project_client.agents.threads.create()
                st.session_state.thread_id = new_thread.id
            
            agent_response = get_agent_response(prompt_to_process, st.session_state.thread_id)
            
            st.session_state.messages.append({"role": "assistant", "content": agent_response})
            with st.chat_message("assistant"):
                st.markdown(agent_response)
        
    # 채팅 입력창
    if prompt := st.chat_input("질문 입력", key="chat_input"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("AI 에이전트가 답변을 생성 중입니다..."):
            if st.session_state.thread_id is None:
                new_thread = project_client.agents.threads.create()
                st.session_state.thread_id = new_thread.id
            
            agent_response = get_agent_response(prompt, st.session_state.thread_id)
            
            st.session_state.messages.append({"role": "assistant", "content": agent_response})
            with st.chat_message("assistant"):
                st.markdown(agent_response)

    # --- "첫 화면으로 돌아가기" 버튼을 채팅 입력창 아래에 배치 ---
    st.markdown("---") # 시각적인 구분선 추가
    if st.button("⬅️ 첫 화면으로 돌아가기", key="back_to_home_bottom"):
        save_current_chat_session() # 홈으로 돌아가기 전에 현재 채팅 저장
        st.session_state.current_view = "home"
        st.session_state.text_input_value = ""
        st.rerun()