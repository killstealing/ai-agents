from dotenv import load_dotenv
from openai import OpenAI
import json
import os
import requests
from pypdf import PdfReader
import gradio as gr


load_dotenv(override=True)


def push(content, summary=None):
    """
    发送消息到 WxPusher
    
    参数:
        content: 消息内容，支持 Markdown
        summary: 消息摘要，显示在微信通知上（可选，默认为内容前100字符）
    """
    # 你的 AppToken（从 WxPusher 官网获取）
    APP_TOKEN = os.getenv("WX_PUSH_TOKEN")  # 替换为你的 AppToken

    # 接收者的 UID（可以是一个或多个）
    UIDS = [os.getenv("WX_PUSH_UIDS")]  # 替换为你的 UID
    
    # API 地址
    url = "https://wxpusher.zjiecode.com/api/send/message"
    
    # 请求头
    headers = {
        "Content-Type": "application/json"
    }
    print(content)
    
    # 请求体
    data = {
        "appToken": APP_TOKEN,
        "content": content,
        "summary": summary if summary else content[:100],  # 摘要，会显示在微信通知上
        "contentType": 1,  # 1 表示文字消息，2 表示 HTML，3 表示 Markdown
        "topicIds": [],    # 发送给主题（群发），这里为空表示发送给个人
        "uids": UIDS,      # 发送给指定用户
        "url": "",         # 可选：附加的 URL，点击消息可以跳转
        "verifyPay": False # 是否验证付费（个人使用保持 False）
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        result = response.json()
        
        if result["code"] == 1000:
            print("消息发送成功！")
            print(f"消息ID: {result['data'][0]['messageId']}")
            return True
        else:
            print(f"消息发送失败: {result['msg']}")
            return False
            
    except Exception as e:
        print(f"请求出错: {e}")
        return False


def record_user_details(email, name="Name not provided", notes="not provided"):
    push(f"Recording {name} with email {email} and notes {notes}")
    return {"recorded": "ok"}

def record_unknown_question(question):
    push(f"Recording {question}")
    return {"recorded": "ok"}

record_user_details_json = {
    "name": "record_user_details",
    "description": "Use this tool to record that a user is interested in being in touch and provided an email address",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "The email address of this user"
            },
            "name": {
                "type": "string",
                "description": "The user's name, if they provided it"
            }
            ,
            "notes": {
                "type": "string",
                "description": "Any additional information about the conversation that's worth recording to give context"
            }
        },
        "required": ["email"],
        "additionalProperties": False
    }
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Always use this tool to record any question that couldn't be answered as you didn't know the answer",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question that couldn't be answered"
            },
        },
        "required": ["question"],
        "additionalProperties": False
    }
}

tools = [{"type": "function", "function": record_user_details_json},
        {"type": "function", "function": record_unknown_question_json}]


class Me:

    def __init__(self):
        DEEPSEEK_URL="https://api.deepseek.com/v1"
        self.openai = OpenAI(base_url=DEEPSEEK_URL,api_key=os.getenv("DEEPSEEK_API_KEY"))
        self.name = "Ed Donner"
        reader = PdfReader("me/linkedin.pdf")
        self.linkedin = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                self.linkedin += text
        with open("me/summary.txt", "r", encoding="utf-8") as f:
            self.summary = f.read()


    def handle_tool_call(self, tool_calls):
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            print(f"Tool called: {tool_name}", flush=True)
            tool = globals().get(tool_name)
            result = tool(**arguments) if tool else {}
            results.append({"role": "tool","content": json.dumps(result),"tool_call_id": tool_call.id})
        return results
    
    def system_prompt(self):
        system_prompt = f"You are acting as {self.name}. You are answering questions on {self.name}'s website, \
particularly questions related to {self.name}'s career, background, skills and experience. \
Your responsibility is to represent {self.name} for interactions on the website as faithfully as possible. \
You are given a summary of {self.name}'s background and LinkedIn profile which you can use to answer questions. \
Be professional and engaging, as if talking to a potential client or future employer who came across the website. \
If you don't know the answer to any question, use your record_unknown_question tool to record the question that you couldn't answer, even if it's about something trivial or unrelated to career. \
If the user is engaging in discussion, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool. "

        system_prompt += f"\n\n## Summary:\n{self.summary}\n\n## LinkedIn Profile:\n{self.linkedin}\n\n"
        system_prompt += f"With this context, please chat with the user, always staying in character as {self.name}."
        return system_prompt
    
    def chat(self, message, history):
        messages = [{"role": "system", "content": self.system_prompt()}] + history + [{"role": "user", "content": message}]
        done = False
        while not done:
            response = self.openai.chat.completions.create(model="deepseek-chat", messages=messages, tools=tools)
            if response.choices[0].finish_reason=="tool_calls":
                message = response.choices[0].message
                tool_calls = message.tool_calls
                results = self.handle_tool_call(tool_calls)
                messages.append(message)
                messages.extend(results)
            else:
                done = True
        return response.choices[0].message.content
    

if __name__ == "__main__":
    me = Me()
    gr.ChatInterface(me.chat, type="messages").launch()
    