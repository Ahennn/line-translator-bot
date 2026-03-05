import os
from flask import Flask, request, abort

# 引入新版 linebot v3 的模組
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError

# 回覆訊息與 API 客戶端相關模組
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)

# Webhook 接收到的事件與訊息類型模組
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

from google import genai

app = Flask(__name__)

# 抓取你在 Dashboard 設定的環境變數
channel_secret = os.environ.get('LINE_CHANNEL_SECRET')
channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
gemini_api_key = os.environ.get('GEMINI_API_KEY')

# 設定 Webhook Handler
handler = WebhookHandler(channel_secret)

# 設定 Gemini API 客戶端
client = genai.Client(api_key=gemini_api_key)

# 新版 Configuration (用於呼叫 LINE Message API)
configuration = Configuration(access_token=channel_access_token)

@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 標頭值來驗證來源
    signature = request.headers['X-Line-Signature']
    # 取得請求內容字串
    body = request.get_data(as_text=True)
    
    try:
        # 處理 Webhook，如果成功會自動導向 handle_message
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    
    return 'OK'

# 針對文字訊息事件的綁定 (新版是 TextMessageContent)
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_text = event.message.text
    
    try:
        # 設定你的自訂翻譯邏輯 Prompt，讓 AI 自己判斷跟切換語言
        prompt = (
            f"請判斷以下文字的語言。\n"
            f"如果主要語言是「韓文」或「英文」，請翻譯成「繁體中文」。\n"
            f"如果主要語言是「繁體中文」，請翻譯成「韓文」。\n"
            f"如果是其他語言，也請預設翻譯成「繁體中文」。\n"
            f"請注意：只需直接回傳翻譯結果，不要包含任何開場白、引號或解釋說明。\n"
            f"以下是需要翻譯的文字：\n{user_text}"
        )
        
        # 呼叫 Gemini 2.0 Flash 模型
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        # 用 .strip() 去除頭尾可能自動產生的多餘空白或換行
        reply_text = response.text.strip()
    except Exception as e:
        reply_text = f"抱歉，我現在有點頭痛... (系統錯誤: {str(e)})"

    # 使用新版 v3 的方式進行訊息回覆
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
