import streamlit as st
from google import genai
from google.genai import types
import os  # 导入os模块读取环境变量

# --- 页面配置 ---
st.set_page_config(
    page_title="Gemini AI 采购助手",
    page_icon="🚀",
    layout="centered",
    initial_sidebar_state="expanded"
)
API_KEY = os.getenv("API_KEY")  

st.title("AI采购助手")
st.markdown("此模型可用于咨询采购价格问题或其他问题。如有条件可前往：https://gemini.google.com/ 使用谷歌官方Gemini AI")
st.caption("受免费API限制，每天询问次数有限。")
# 定义角色预设
SYSTEM_PROMPT = """You are a senior Global Strategic Sourcing and Supply Chain Expert. 
Your role is to provide users with comprehensive price analyses for products both domestically and internationally. 
This includes detailed cost comparisons across various procurement channels and delivering data-driven procurement strategies and professional recommendations."""
# --- 1. 侧边栏配置 ---
with st.sidebar:
    st.header("⚙️ 设置")
    
    # 获取 API Key
    api_key = API_KEY # 建议使用环境变量
    if not api_key:
        api_key = st.text_input("请输入 Gemini API Key", type="password", help="需要 Google AI Studio 的 API Key")
        if not api_key:
            st.warning("⚠️ 请配置 GEMINI_API_KEY 环境变量或在此输入 Key 以开始使用。")
    else:
        st.success("✅ 已检测到 API Key")

    st.divider()

    # 模型选择
    model_options = [
        "gemini-3-flash-preview", # 建议：支持多模态且速度快
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ]
    
    selected_model = st.selectbox(
        "选择模型版本", 
        model_options, 
        index=0 
    )
    
    use_custom_model = st.checkbox("手动输入模型名称")
    if use_custom_model:
        model_name = st.text_input("请输入自定义模型名称", value=selected_model)
    else:
        model_name = selected_model

    st.caption(f"当前使用模型: **{model_name}**")
    
    st.divider()

    # --- 思考功能配置 ---
    st.subheader("🧠 思考配置 (Thinking)")
    enable_thinking = st.toggle("启用思考过程", value=False, help="开启后模型将展示推理过程。仅部分模型支持。")
    
    thinking_budget_map = {
        "Low (快速)": 2048,
        "Medium (平衡)": 8192,
        "High (深度)": 16384
    }
    
    thinking_budget_val = None
    if enable_thinking:
        level_label = st.selectbox(
            "思考等级 (Thinking Budget)",
            options=list(thinking_budget_map.keys()),
            index=1,
            help="通过限制思考 Token 的数量来控制深度。"
        )
        thinking_budget_val = thinking_budget_map[level_label]
    
    st.divider()
    if st.button("🗑️ 清空对话历史"):
        st.session_state.messages = []
        st.rerun()

# --- 2. 初始化 Client ---
if api_key:
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"❌ 客户端初始化失败，请检查 API Key 是否正确。\n错误信息: {e}")
        st.stop()
else:
    st.info("👈 请在左侧侧边栏输入 API Key 以继续。")
    st.stop()

# --- 3. 管理聊天历史 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 4. 渲染历史消息 ---
for msg in st.session_state.messages:
    avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        # [新增] 渲染历史图片
        if "image" in msg and msg["image"]:
            st.image(msg["image"], caption="已上传图片", width=200)
            
        # 如果历史消息中有 thought 字段，则先渲染思考过程
        if "thought" in msg and msg["thought"]:
            with st.expander("💭 查看思考过程", expanded=False):
                st.markdown(msg["thought"])
        st.markdown(msg["content"])

# --- [新增] 图片上传组件 (放置在输入框上方) ---
with st.container():
    # 使用 expander 保持界面整洁，放在这里视觉上最接近输入框
    with st.expander("📎 上传图片 (点击展开)", expanded=False):
        uploaded_file = st.file_uploader("选择图片...", type=["jpg", "jpeg", "png", "webp"], key="chat_image_upload")

# --- 5. 处理用户输入 ---
if prompt := st.chat_input("请输入您的问题..."):
    
    # [新增] 处理图片数据
    image_data = None
    mime_type = None
    if uploaded_file:
        image_data = uploaded_file.getvalue()
        mime_type = uploaded_file.type
    
    with st.chat_message("user", avatar="🧑‍💻"):
        # [新增] 在当前对话框显示图片
        if image_data:
            st.image(image_data, caption="已上传图片", width=200)
        st.markdown(prompt)
    
    # [修改] 保存消息时包含图片信息
    user_msg_obj = {"role": "user", "content": prompt}
    if image_data:
        user_msg_obj["image"] = image_data
        user_msg_obj["mime_type"] = mime_type
        
    st.session_state.messages.append(user_msg_obj)

    with st.chat_message("assistant", avatar="🤖"):
        # 创建占位符
        thought_placeholder = st.empty() # 用于显示思考过程
        message_placeholder = st.empty() # 用于显示最终回复
        
        full_response = ""
        full_thought = ""
        
        try:
            # --- 构建历史上下文 ---
            history_contents = []
            for msg in st.session_state.messages:
                role = "user" if msg["role"] == "user" else "model"
                
                parts = []
                # [新增] 将图片添加到 parts 中
                if role == "user" and "image" in msg and msg["image"]:
                    parts.append(types.Part.from_bytes(
                        data=msg["image"],
                        mime_type=msg["mime_type"]
                    ))
                
                # 添加文本
                parts.append(types.Part.from_text(text=msg["content"]))
                
                history_contents.append(
                    types.Content(
                        role=role,
                        parts=parts
                    )
                )

            # --- 配置生成参数 ---
            if enable_thinking:
                thinking_config_args = {"include_thoughts": True}
                if thinking_budget_val:
                    thinking_config_args["thinking_budget"] = thinking_budget_val

                config = types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    thinking_config=types.ThinkingConfig(**thinking_config_args)
                )
            else:
                config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT,temperature=0.7)

            # --- 调用 API (流式) ---
            response = client.models.generate_content_stream(
                model=model_name,
                contents=history_contents,
                config=config
            )
            
            # --- 实时流式渲染 (重点修改部分) ---
            # 我们使用 expander 来包裹思考过程，初始状态设为 expanded=True 以便实时查看
            with thought_placeholder.status("🧠 正在思考...", expanded=True) as status:
                thought_container = st.empty()
                
                for chunk in response:
                    # 遍历 chunk 中的每一个 part
                    if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                        for part in chunk.candidates[0].content.parts:
                            # 1. 处理思考内容 (Thought)
                            if part.thought: 
                                thought_text = part.text # 这里才是真正的思考文本
                                full_thought += thought_text
                                thought_container.markdown(full_thought)
                            
                            # 2. 处理普通文本 (Text)
                            elif part.text:
                                full_response += part.text
                                message_placeholder.markdown(full_response + "▌")
                
                status.update(label="💭 思考完成", state="complete", expanded=False)

            # 完成后显示最终文本
            message_placeholder.markdown(full_response)
            
            # 将 AI 回复存入历史 (同时保存 thought)
            st.session_state.messages.append({
                "role": "assistant", 
                "content": full_response,
                "thought": full_thought if full_thought else None
            })
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str:
                st.error("🚫 **配额已用完 (429)**")
            elif "Extra inputs" in error_str:
                st.error("⚠️ **配置参数错误** (当前模型可能不支持图片或Thinking，请切换模型)")
            else:

                st.error(f"⚠️ 发生错误: {error_str}")
