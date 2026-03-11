import os
import threading  # 加入多線程支援，防止 LINE 重複發送請求
from flask import Flask, request, abort

# LINE SDK v3 相關模組
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

# Google GenAI SDK
from google import genai

app = Flask(__name__)

# 讀取環境變數
channel_secret = os.environ.get('LINE_CHANNEL_SECRET')
channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
gemini_api_key = os.environ.get('GEMINI_API_KEY')

# 初始化客戶端
handler = WebhookHandler(channel_secret)
client = genai.Client(api_key=gemini_api_key)
configuration = Configuration(access_token=channel_access_token)

def process_translation_and_reply(event):
    """
    此函數會在背景執行：
    1. 呼叫 Gemini 進行翻譯（強制關閉收費工具）
    2. 回覆翻譯結果給 LINE 使用者
    """
    user_text = event.message.text
    
    try:
        # 自定義翻譯 Prompt
        prompt = (
            f"請判斷以下文字的語言。\n"
            f"如果主要語言是「韓文」或「英文」，請翻譯成「繁體中文」。\n"
            f"如果主要語言是「繁體中文」，請翻譯成「韓文」。\n"
            f"如果是其他語言，也請預設翻譯成「繁體中文」。\n"
            f"注意：只需回傳翻譯結果，不要包含任何開場白或解釋。\n"
            f"內容：\n{user_text}"
        )

        # 調用 Gemini 2.5 Flash
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "tools": [],           # 【止血核心 1】強制清空工具，防止觸發高額 Google 搜尋費用
                "temperature": 0.1,    # 調低溫度，增加翻譯穩定度並減少不必要的 Token 消耗
                "max_output_tokens": 800
            }
        )
        reply_text = response.text.strip()

    except Exception as e:
        reply_text = f"抱歉，翻譯過程發生錯誤：{str(e)}"

    # 使用 LINE API 回覆訊息
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )

@app.route("/", methods=['GET'])
def home():
    return "Line Bot is Active."

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    # 【止血核心 2】立刻回傳 OK 給 LINE
    # 這樣 LINE 就會知道訊息已送達，不會因為 Gemini 跑太久而重複發送請求
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # 建立新線程在背景執行翻譯任務，主線程則立刻跳回 callback 回傳 'OK'
    task = threading.Thread(target=process_translation_and_reply, args=(event,))
    task.start()

if __name__ == "__main__":
    # Render 環境建議設定 host='0.0.0.0'
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
